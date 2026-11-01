import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
from Crypto.Cipher import AES
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from aeslab import SBOX, HW, cpa, score_key, hypotheses, load_dataset, wilson, shift_traces
from capture_random_keys import checked_capture


class LabTests(unittest.TestCase):
    def test_aes_known_answer(self):
        self.assertEqual(AES.new(bytes(range(16)),AES.MODE_ECB).encrypt(bytes.fromhex('00112233445566778899aabbccddeeff')).hex(),'69c4e0d86a7b0430d8cdb78070b4c55a')
        self.assertEqual(len(set(SBOX)),256)
        self.assertEqual(int(SBOX[0x53]),0xed)

    def test_cpa_independent_pearson_and_recovery(self):
        rng=np.random.default_rng(923);p=rng.integers(0,256,(700,16),dtype=np.uint8);key=rng.integers(0,256,16,dtype=np.uint8)
        w=HW[SBOX[p^key]]+rng.normal(0,.2,(700,16))
        s,peaks,diag=cpa(w,p);r=score_key(s,peaks,key,diag)
        self.assertTrue(r['full_key_recovery'])
        h=hypotheses(p,0,'sbox_hw')[:,int(key[0])]
        self.assertAlmostEqual(s[0,key[0]],abs(np.corrcoef(h,w[:,0])[0,1]),places=12)
        self.assertNotIn('key',inspect.signature(cpa).parameters)
        s2,_,_=cpa(w,p);np.testing.assert_array_equal(s,s2)
        perm=cpa(w,rng.permutation(p));self.assertFalse(score_key(*perm[:2],key,perm[2])['full_key_recovery'])

    def test_degenerate_and_ties(self):
        p=np.zeros((10,16),dtype=np.uint8);s,peaks,d=cpa(np.ones((10,3)),p)
        r=score_key(s,peaks,np.zeros(16,dtype=np.uint8),d)
        self.assertFalse(r['valid']);self.assertFalse(r['full_key_recovery'])
        rng=np.random.default_rng(2);p=rng.integers(0,256,(500,16),dtype=np.uint8)
        s,peaks,d=cpa(HW[p],p,'xor_hw');r=score_key(s,peaks,np.zeros(16,dtype=np.uint8),d)
        self.assertEqual(r['correct_bytes'],0);self.assertEqual(r['bytes'][0]['rank_worst'],2)
        with self.assertRaises(ValueError):cpa(np.full((500,3),np.nan),p)

    def test_loader_correspondence_and_shape(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'d.npz';key=np.zeros(16,dtype=np.uint8);pt=np.zeros((3,16),dtype=np.uint8)
            ct=np.tile(np.frombuffer(AES.new(key.tobytes(),AES.MODE_ECB).encrypt(bytes(16)),dtype=np.uint8),(3,1))
            np.savez(path,waves=np.zeros((3,4)),plaintexts=pt,ciphertexts=ct,key=key)
            self.assertEqual(load_dataset(path)['waves'].shape,(3,4))
            ct[1,0]^=1;np.savez(path,waves=np.zeros((3,4)),plaintexts=pt,ciphertexts=ct,key=key)
            with self.assertRaises(ValueError):load_dataset(path)
            np.savez(path,waves=np.zeros((3,4)))
            with self.assertRaises(ValueError):load_dataset(path)

    def test_intervals_and_shift(self):
        lo,hi=wilson(5,5);self.assertAlmostEqual(lo,.5655175352);self.assertAlmostEqual(hi,1)
        with self.assertRaises(ValueError):wilson(0,0)
        np.testing.assert_array_equal(shift_traces(np.array([[1,2,3,4]]),[1]),[[1,1,2,3]])

    def test_capture_validation(self):
        class FakeCW:
            def capture_trace(self,*args,**kwargs):
                self.always=kwargs['always_send_key'];return self.trace
        class Trace:pass
        cw=FakeCW();cw.trace=Trace();cw.trace.wave=np.ones(4);cw.trace.textin=bytes(16)
        cw.trace.textout=AES.new(bytes(16),AES.MODE_ECB).encrypt(bytes(16))
        checked_capture(cw,None,None,bytes(16),bytes(16),4);self.assertTrue(cw.always)
        cw.trace.textout=bytes(16)
        with self.assertRaises(ValueError):checked_capture(cw,None,None,bytes(16),bytes(16),4)
        cw.trace=None
        with self.assertRaises(TimeoutError):checked_capture(cw,None,None,bytes(16),bytes(16),4)

    def test_aggregate_denominators_and_duplicate_rejection(self):
        from analyze_aes import aggregate
        from aeslab import digest
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/'reports';out.mkdir()
            key=np.zeros(16,dtype=np.uint8);pt=np.zeros((3,16),dtype=np.uint8)
            ct=np.tile(np.frombuffer(AES.new(bytes(16),AES.MODE_ECB).encrypt(bytes(16)),dtype=np.uint8),(3,1))
            np.savez(root/'trial.npz',waves=np.ones((3,4)),plaintexts=pt,ciphertexts=ct,key=key)
            h=digest(root/'trial.npz')
            (root/'protocol.json').write_text(json.dumps({'requested_trials':3}))
            (root/'trial-00.json').write_text(json.dumps({'trial_id':'a','outcome':'COMPLETE','sha256':h,'dataset':'trial.npz'}))
            (root/'trial-01.json').write_text(json.dumps({'trial_id':'b','outcome':'FAILED'}))
            report={'sha256':h,'prefixes':[{'traces':3,'full_key_recovery':True,'valid':True,'correct_bytes':16,'bytes':[{'rank_worst':1}]*16}]}
            aggregate([report],root,out,[3])
            row=json.loads((out/'independent-trials.json').read_text())['rows'][0]
            self.assertEqual((row['planned_trials'],row['attempted_trials'],row['analyzed_trials'],row['missing_or_failed']),(3,2,1,2))
            self.assertAlmostEqual(row['conservative_successes_per_planned'],1/3)
            with self.assertRaises(ValueError):aggregate([report,report],root,out,[3])

    def test_alignment_relative_range(self):
        from check_alignment import align
        rng=np.random.default_rng(15);base=rng.normal(size=200)
        w=shift_traces(np.tile(base,(3,1)),[-8,0,8]);a,offsets=align(w,16)
        self.assertEqual(offsets,[0,-8,-16])
        np.testing.assert_array_equal(a[:,24:-24],np.tile(a[0,24:-24],(3,1)))


if __name__=='__main__':unittest.main()
