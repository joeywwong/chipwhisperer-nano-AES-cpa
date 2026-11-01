"""Check installed Analyzer against exact prefix sizes; preserve legacy behavior."""
import argparse
from pathlib import Path
import tempfile
import warnings
import numpy as np
from aeslab import load_dataset, cpa, score_key, write_json


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('dataset',type=Path)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--counts',default='10,20,30,40,100')
    p.add_argument('--legacy',action='store_true');args=p.parse_args()
    import chipwhisperer as cw
    import chipwhisperer.analyzer as cwa
    d=load_dataset(args.dataset);rows=[]
    with tempfile.TemporaryDirectory() as temp:
        proj=cw.create_project(str(Path(temp)/'check.cwp'))
        try:
            for w,pt,ct in zip(d['waves'],d['plaintexts'],d['ciphertexts']):
                proj.traces.append(cw.Trace(w,bytearray(pt),bytearray(ct),bytearray(d['key'])))
            for n in map(int,args.counts.split(',')):
                for mode in (['exact','legacy'] if args.legacy else ['exact']):
                    end=n-1 if mode=='exact' else n
                    attack=cwa.cpa(proj,cwa.leakage_models.sbox_output);attack.trace_range=[0,end]
                    with warnings.catch_warnings(record=True) as captured:
                        warnings.simplefilter('always');result=attack.run(update_interval=25)
                    guesses=[int(g) for g in result.key_guess()]
                    actual=min(end+1,len(d['waves']))
                    s,pk,di=cpa(d['waves'][:actual],d['plaintexts'][:actual])
                    own=score_key(s,pk,d['key'],di)
                    row={'mode':mode,'label_count':n,'requested_inclusive_end':end,'available_prefix':actual,
                         'cw_correct':int(sum(g==k for g,k in zip(guesses,d['key']))),
                         'numpy_correct_unique':own['correct_bytes'],'cw_guesses':guesses,
                         'all_guesses_agree':guesses==[b['guess'] for b in own['bytes']],
                         'warnings':sorted(set(str(w.message) for w in captured))}
                    rows.append(row);print(row,flush=True)
                    del attack
        finally:proj.close(save=False)
    write_json(args.out,{'chipwhisperer':cw.__version__,'dataset':args.dataset.name,'rows':rows})


if __name__=='__main__':main()
