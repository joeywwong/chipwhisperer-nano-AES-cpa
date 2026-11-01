"""Offline AES laboratory analysis. Inference never accepts a reference key."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from Crypto.Cipher import AES

# FIPS 197 Table 4, indexed by the untransformed byte.
SBOX = np.frombuffer(bytes.fromhex(
    '637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0'
    'b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275'
    '09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf'
    'd0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2'
    'cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb'
    'e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08'
    'ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e'
    'e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16'), dtype=np.uint8)
HW = np.array([i.bit_count() for i in range(256)], dtype=float)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def load_dataset(path):
    with np.load(path, allow_pickle=False) as z:
        d = {k: z[k].copy() for k in z.files}
    for k in ('waves', 'plaintexts', 'ciphertexts', 'key'):
        if k not in d:
            raise ValueError('Missing field: ' + k)
    w = d['waves']
    if w.ndim != 2 or min(w.shape) < 2 or w.dtype.kind not in 'fi' or not np.isfinite(w).all():
        raise ValueError('Expected finite numeric N-by-T waves, N,T >= 2')
    for k, shape in [('plaintexts', (len(w), 16)), ('ciphertexts', (len(w), 16)), ('key', (16,))]:
        if d[k].shape != shape or d[k].dtype != np.uint8:
            raise ValueError(f'{k}: expected uint8 {shape}')
    cipher = AES.new(d['key'].tobytes(), AES.MODE_ECB)
    for i, (p, c) in enumerate(zip(d['plaintexts'], d['ciphertexts'])):
        if cipher.encrypt(p.tobytes()) != c.tobytes():
            raise ValueError(f'Ciphertext mismatch at trace {i}')
    d['metadata'] = json.loads(str(d['metadata'])) if 'metadata' in d else {'provenance': 'legacy notebook; acquisition settings/date/firmware hash not archived'}
    return d


def hypotheses(plaintexts, byte, model):
    x = plaintexts[:, byte, None] ^ np.arange(256, dtype=np.uint8)[None, :]
    if model == 'sbox_hw':
        return HW[SBOX[x]]
    if model == 'xor_hw':
        return HW[x]
    if model == 'sbox_hd':
        return HW[x ^ SBOX[x]]
    raise ValueError('Unknown leakage model')


def cpa(waves, plaintexts, model='sbox_hw'):
    w = np.asarray(waves, dtype=float)
    p = np.asarray(plaintexts)
    if w.ndim != 2 or min(w.shape) < 2 or p.shape != (len(w), 16) or p.dtype != np.uint8 or not np.isfinite(w).all():
        raise ValueError('Invalid CPA inputs')
    wc = w - w.mean(axis=0)
    wn = np.linalg.norm(wc, axis=0)
    valid_w = wn > 0
    scores, peaks, diagnostics = [], [], []
    for b in range(16):
        h = hypotheses(p, b, model)
        h -= h.mean(axis=0)
        hn = np.linalg.norm(h, axis=0)
        valid_h = hn > 0
        den = hn[:, None] * wn[None, :]
        corr = np.full((256, w.shape[1]), np.nan)
        np.divide(h.T @ wc, den, out=corr, where=den > 0)
        usable = valid_h[:, None] & valid_w[None, :]
        absolute = np.where(usable, np.abs(corr), -np.inf)
        peak = absolute.argmax(axis=1)
        score = absolute[np.arange(256), peak]
        scores.append(score)
        peaks.append(peak)
        diagnostics.append({'zero_variance_hypotheses': int((~valid_h).sum()), 'zero_variance_samples': int((~valid_w).sum())})
    return np.array(scores), np.array(peaks), diagnostics


def score_key(scores, peaks, key, diagnostics):
    rows = []
    for b, s in enumerate(scores):
        k = int(key[b]); valid = np.isfinite(s)
        if not valid.any() or not valid[k]:
            rows.append({'byte': b, 'guess': None, 'rank_best': None, 'rank_worst': None,
                         'correct': False, 'true_correlation': None, 'status': 'INVALID', **diagnostics[b]})
            continue
        g = int(s.argmax())
        # Tolerance preserves equivalent hypotheses; never break a tie using the key.
        ties = np.isclose(s, s[k], atol=1e-12, rtol=0)
        best = int(np.sum((s > s[k]) & ~ties)) + 1
        worst = best + int(ties.sum()) - 1
        unique = np.isclose(s, s[g], atol=1e-12, rtol=0).sum() == 1
        rows.append({'byte': b, 'guess': g, 'rank_best': best, 'rank_worst': worst,
                     'correct': bool(unique and g == k), 'true_correlation': float(s[k]),
                     'winning_correlation': float(s[g]), 'peak_sample': int(peaks[b, g]),
                     'status': 'VALID', **diagnostics[b]})
    return {'bytes': rows, 'correct_bytes': sum(x['correct'] for x in rows),
            'full_key_recovery': all(x['correct'] for x in rows),
            'valid': all(x['status'] == 'VALID' for x in rows),
            'guessed_key': ''.join('??' if x['guess'] is None else f"{x['guess']:02x}" for x in rows)}


def wilson(successes, trials, z=1.959963984540054):
    if trials < 1 or not 0 <= successes <= trials:
        raise ValueError('Invalid binomial denominator')
    p = successes / trials; den = 1 + z*z/trials
    center = (p + z*z/(2*trials))/den
    radius = z * math.sqrt(p*(1-p)/trials + z*z/(4*trials*trials))/den
    return [max(0., center-radius), min(1., center+radius)]


def shift_traces(waves, shifts):
    """Offline timing-nuisance transform, with edge padding, never circular wrap."""
    if len(shifts) != len(waves) or np.max(np.abs(shifts)) >= waves.shape[1]:
        raise ValueError('Invalid shifts')
    t = np.arange(waves.shape[1])
    return np.stack([w[np.clip(t-int(s), 0, len(w)-1)] for w, s in zip(waves, shifts)])
