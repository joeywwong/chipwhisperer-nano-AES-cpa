"""Measured-data CPA, within-dataset prefixes and offline nuisance comparison."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from aeslab import load_dataset, cpa, score_key, digest, write_json, wilson, shift_traces


def analyze(path, out, counts):
    d = load_dataset(path)
    w, p, key = d['waves'], d['plaintexts'], d['key']
    fig, axes = plt.subplots(2, 1, figsize=(10, 6))
    axes[0].plot(w[0], label='Trace 1', alpha=.7); axes[0].plot(w[1], label='Trace 2', alpha=.7)
    axes[0].set(ylabel='ADC relative units', title='MEASURED archive: '+path.name); axes[0].legend()
    axes[1].plot(w.std(axis=0)); axes[1].set(xlabel='Sample index', ylabel='Across-trace standard deviation')
    fig.tight_layout(); fig.savefig(out/(path.stem+'-waves.png'), dpi=150); plt.close(fig)
    records = []
    for n in counts:
        if n > len(w): continue
        s, peaks, diag = cpa(w[:n], p[:n])
        records.append({'traces': n, **score_key(s, peaks, key, diag)})
    comparisons = []
    rng = np.random.default_rng(1701)
    shifts = rng.integers(-8, 9, len(w))
    shifted = shift_traces(w, shifts)
    # A fixed trace-0 template and +/-8 search; no key or score chooses shifts.
    template = shifted[0] - shifted[0].mean()
    aligned = []
    for trace in shifted:
        candidates = shift_traces(np.repeat(trace[None, :], 17, axis=0), np.arange(-8, 9))
        centered = candidates - candidates.mean(axis=1, keepdims=True)
        similarities = centered @ template / np.maximum(np.linalg.norm(centered, axis=1), 1e-30)
        aligned.append(candidates[similarities.argmax()])
    for label, waves, labels, model, status in [
        ('sbox_hw', w, p, 'sbox_hw', 'MEASURED; offline reanalysis'),
        ('xor_hw', w, p, 'xor_hw', 'MEASURED; alternative model with complementary ties'),
        ('sbox_hd', w, p, 'sbox_hd', 'MEASURED; alternative overwrite-transition model'),
        ('permuted_labels', w, rng.permutation(p), 'sbox_hw', 'CONTROL; permuted measured labels'),
        ('noise_only', rng.normal(size=w.shape), p, 'sbox_hw', 'SIMULATED negative control'),
        ('shifted', shifted, p, 'sbox_hw', 'SIMULATED timing shifts on measured waves; not firmware'),
        ('aligned', np.asarray(aligned), p, 'sbox_hw', 'SIMULATED shifts, key-independent template alignment')]:
        s, peaks, diag = cpa(waves, labels, model)
        comparisons.append({'variant': label, 'status': status, **score_key(s, peaks, key, diag)})
    report = {'dataset': path.name, 'sha256': digest(path), 'shape': list(w.shape),
              'ciphertexts_verified': len(w), 'metadata': d['metadata'],
              'prefix_scope': 'within-dataset prefixes; dependent observations',
              'prefixes': records, 'comparisons': comparisons,
              'analysis': {'score': 'max absolute Pearson correlation over all samples',
                           'tie_tolerance': 1e-12, 'rng_seed': 1701, 'shift_range': [-8, 8],
                           'alignment': 'trace 0 template, full window, +/-8 edge-padded shifts',
                           'selection': 'exploratory models; no security claim or minimum trace estimate'}}
    write_json(out/(path.stem+'.json'), report)
    with (out/(path.stem+'-bytes.csv')).open('x', newline='') as f:
        rows = [dict(traces=r['traces'], **b) for r in records for b in r['bytes']]
        fields = sorted(set().union(*(r.keys() for r in rows)))
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    fig, ax = plt.subplots(figsize=(8,4))
    ax.plot([r['traces'] for r in records], [r['correct_bytes'] for r in records], 'o-')
    ax.set(xlabel='Traces in acquisition prefix', ylabel='Uniquely recovered bytes / 16', ylim=(0,17),
           title='MEASURED AES: within-dataset prefix CPA\n'+path.name)
    ax.grid(alpha=.25); fig.tight_layout(); fig.savefig(out/(path.stem+'-prefix.png'), dpi=150); plt.close(fig)
    fig, ax = plt.subplots(figsize=(9,4))
    ax.bar([c['variant'] for c in comparisons], [c['correct_bytes'] for c in comparisons])
    ax.set(ylabel='Uniquely recovered bytes / 16', ylim=(0,17),
           title='Exploratory models and controls; shifts/noise are SIMULATED\n'+path.name)
    ax.tick_params(axis='x', rotation=25); fig.tight_layout(); fig.savefig(out/(path.stem+'-comparison.png'), dpi=150); plt.close(fig)
    print(path.name, [(r['traces'],r['correct_bytes']) for r in records], flush=True)
    return report


def aggregate(reports, manifest_dir, out, counts):
    manifests = [json.loads(p.read_text()) for p in sorted(manifest_dir.glob('trial-*.json'))]
    protocol = json.loads((manifest_dir/'protocol.json').read_text())
    # Require unique captures, keys, and IDs, not copies/prefixes of one acquisition.
    if len({r['sha256'] for r in reports}) != len(reports): raise ValueError('Duplicate datasets')
    ids = [m['trial_id'] for m in manifests]
    if len(set(ids)) != len(ids): raise ValueError('Duplicate trial identifiers')
    matched = {m.get('sha256') for m in manifests if m['outcome']=='COMPLETE'}
    if {r['sha256'] for r in reports} != matched: raise ValueError('Reports do not match complete trial manifest')
    keys = [load_dataset(manifest_dir/m['dataset'])['key'].tobytes() for m in manifests if m['outcome']=='COMPLETE']
    if len(set(keys)) != len(keys): raise ValueError('Repeated keys in random-key trial group')
    rows=[]
    for n in counts:
        runs=[r for report in reports for r in report['prefixes'] if r['traces']==n]
        successes=sum(r['full_key_recovery'] for r in runs)
        planned=protocol['requested_trials']; completed=len(runs)
        valid=[b['rank_worst'] for r in runs for b in r['bytes'] if b['rank_worst'] is not None]
        rows.append({'traces':n,'planned_trials':planned,'attempted_trials':len(manifests),
                     'analyzed_trials':completed,'missing_or_failed':planned-completed,'full_key_successes':successes,
                     'success_rate_completed':successes/completed if completed else None,
                     'wilson95_completed':wilson(successes,completed) if completed else None,
                     'conservative_successes_per_planned':successes/planned,
                     'mean_per_byte_accuracy':sum(r['correct_bytes'] for r in runs)/(16*completed) if completed else None,
                     'mean_rank_worst':float(np.mean(valid)) if valid else None,
                     'sd_rank_worst':float(np.std(valid,ddof=1)) if len(valid)>1 else None,
                     'invalid_runs':sum(not r['valid'] for r in runs)})
    write_json(out/'independent-trials.json', {'scope':'fresh keys/acquisitions, same device/visit; prefixes dependent across n; Wilson assumes independent Bernoulli trials', 'rows':rows})
    with (out/'independent-trials.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    usable=[r for r in rows if r['analyzed_trials']]
    if usable:
        x=np.array([r['traces'] for r in usable]);y=np.array([r['success_rate_completed'] for r in usable])
        ci=np.array([r['wilson95_completed'] for r in usable])
        fig,ax=plt.subplots(figsize=(8,4));ax.errorbar(x,y,yerr=np.stack([y-ci[:,0],ci[:,1]-y]),fmt='o-',capsize=4)
        ax.set(xlabel='Traces per independent acquisition (nested prefixes)',ylabel='Full-key success fraction',ylim=(-.05,1.05),title='MEASURED random-key AES; Wilson 95% intervals\nSame device and visit; denominators in CSV')
        ax.grid(alpha=.25);fig.tight_layout();fig.savefig(out/'independent-trials.png',dpi=150);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('datasets',nargs='+',type=Path);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--manifest-dir',type=Path);p.add_argument('--counts',default='10,20,30,40,50,60,80,100')
    args=p.parse_args();counts=[int(x) for x in args.counts.split(',')]
    if not counts or any(n<3 for n in counts):p.error('Counts must be >=3')
    if len({p.stem for p in args.datasets})!=len(args.datasets):p.error('Dataset stems must be unique')
    args.out.mkdir(parents=True,exist_ok=False)
    reports=[analyze(path,args.out,counts) for path in args.datasets]
    if args.manifest_dir:aggregate(reports,args.manifest_dir,args.out,counts)


if __name__=='__main__':main()
