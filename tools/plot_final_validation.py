# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
"""Render the retained paired measurements; no simulated or fitted results."""
from pathlib import Path
import argparse
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ap=argparse.ArgumentParser()
ap.add_argument('evaluation',type=Path)
ap.add_argument('--out',type=Path,required=True)
args=ap.parse_args()
data=json.loads(args.evaluation.read_text())
sizes=data['sizes']
assert len(sizes)==2 and all(s['arms']['candidate']['n']==3 for s in sizes)
args.out.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                     'axes.spines.right':False,'svg.fonttype':'none'})
fig,axes=plt.subplots(1,2,figsize=(10.8,5.3))
colors={'control':'#778493','candidate':'#087e8b'}
for ax in axes:
    ax.set_axisbelow(True)
    ax.grid(axis='y',alpha=.2)
for index,arm in enumerate(('control','candidate')):
    positions=[i+(-.18 if index==0 else .18) for i in range(2)]
    times=[s['arms'][arm]['mean_s'] for s in sizes]
    sd=[s['arms'][arm]['sd_s'] for s in sizes]
    memory=[s['arms'][arm]['max_pg_pss_bytes']/2**20 for s in sizes]
    label='Approved control' if arm=='control' else 'Candidate'
    bars=axes[0].bar(positions,times,.33,yerr=sd,capsize=4,label=label,color=colors[arm])
    axes[0].bar_label(bars,labels=[f'{v:.2f}' for v in times],padding=5,fontsize=9)
    bars=axes[1].bar(positions,memory,.33,label=label,color=colors[arm])
    axes[1].bar_label(bars,labels=[f'{v:.1f}' for v in memory],padding=4,fontsize=9)
for ax in axes:
    ax.set_xticks([0,1],['1 million rows','3 million rows'])
    ax.set_ylim(0,ax.get_ylim()[1]*1.15)
axes[0].set_ylabel('MEASURED PROCESSING TOTAL (seconds)')
axes[0].set_title('Mean processing time ± sample SD')
axes[1].set_ylabel('Maximum sampled PostgreSQL PSS (MiB)')
axes[1].set_title('Memory across three runs per arm')
handles,labels=axes[0].get_legend_handles_labels()
fig.legend(handles,labels,loc='upper center',ncol=2,bbox_to_anchor=(.5,.94),frameon=False)
fig.suptitle('PGDM Expand — paired local validation',fontsize=15,y=.995)
max_temp=max(s['arms'][arm]['max_temp_bytes'] for s in sizes for arm in ('control','candidate'))
fig.text(.5,.04,f'PostgreSQL 16 · 4 vCPU · 6 GiB · n=3 per arm and size · maximum recorded temp_bytes delta: {max_temp:,} B',ha='center',fontsize=9)
fig.text(.5,.005,'Francisco Angulo de Lafuente · ORCID 0009-0001-1634-7063',ha='center',fontsize=8)
fig.tight_layout(rect=(0,.08,1,.88))
metadata={'Creator':'Francisco Angulo de Lafuente; ORCID 0009-0001-1634-7063',
          'Description':'Measured local benchmarks; bars show retained observations, not an official competition score.'}
fig.savefig(args.out/'validation-20261108.png',dpi=200,metadata=metadata)
fig.savefig(args.out/'validation-20261108.svg',metadata=metadata)
(args.out/'validation-20261108.plot.json').write_text(json.dumps({
    'input_sha256':hashlib.sha256(args.evaluation.read_bytes()).hexdigest(),
    'matplotlib':matplotlib.__version__,'source':'tools/plot_final_validation.py',
    'author':'Francisco Angulo de Lafuente','orcid':'https://orcid.org/0009-0001-1634-7063'},indent=2),encoding='utf-8')
print(json.dumps({'png':str(args.out/'validation-20261108.png'),'svg':str(args.out/'validation-20261108.svg')}))
