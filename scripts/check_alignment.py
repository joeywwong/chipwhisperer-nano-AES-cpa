"""Offline timing nuisance follow-up; no new hardware countermeasure."""
import argparse
from pathlib import Path
import numpy as np
from aeslab import load_dataset,cpa,score_key,shift_traces,write_json,digest


def align(waves,radius):
    template=waves[0]-waves[0].mean();out=[];offsets=[]
    # Differences between two injected shifts in [-J,J] can reach 2J.
    for w in waves:
        choices=np.arange(-radius,radius+1)
        candidates=shift_traces(np.repeat(w[None,:],len(choices),axis=0),choices)
        centered=candidates-candidates.mean(axis=1,keepdims=True)
        score=centered@template/np.maximum(np.linalg.norm(centered,axis=1),1e-30)
        index=int(score.argmax());out.append(candidates[index]);offsets.append(int(choices[index]))
    return np.asarray(out),offsets


def plot_followup(rows,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,4))
    ax.bar([r['dataset'] for r in rows],[r['correct_bytes'] for r in rows])
    ax.set(ylim=(0,17),ylabel='Uniquely recovered bytes / 16',
           title='SIMULATED timing shifts on measured AES\nFull relative-shift alignment search (+/-16 samples)')
    fig.tight_layout();fig.savefig(path,dpi=150);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('datasets',nargs='+',type=Path);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();rows=[]
    for path in args.datasets:
        d=load_dataset(path);rng=np.random.default_rng(1701);shifts=rng.integers(-8,9,len(d['waves']))
        changed=shift_traces(d['waves'],shifts);aligned,offsets=align(changed,16)
        s,pk,diag=cpa(aligned,d['plaintexts']);r=score_key(s,pk,d['key'],diag)
        rows.append({'dataset':path.name,'sha256':digest(path),'status':'SIMULATED timing shifts on measured data',
                     'search_radius':16,'offsets':offsets,**r})
        print(path.name,r['correct_bytes'],flush=True)
    write_json(args.out,{'protocol':'follow-up correction: +/-16 covers relative shifts; full-waveform trace-0 template; no key used in alignment; exploratory, not held-out validation','rows':rows})
    plot_followup(rows,args.out.with_suffix('.png'))


if __name__=='__main__':main()
