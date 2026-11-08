# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
"""Evaluate prospectively fixed paired criteria; retain exploratory data separately."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import statistics

ap=argparse.ArgumentParser()
ap.add_argument('results',type=Path)
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--reference-3m',type=Path,required=True)
args=ap.parse_args()
sizes=[]
for rows in (1000000,3000000):
    root=args.results/f'r{rows}'
    arms={}
    for arm in ('control','candidate'):
        runs=[]
        for rep in (1,2,3):
            path=root/f'confirm_{arm}_rep{rep}.json'
            verify=root/f'verify_confirm_{arm}_rep{rep}.json'
            d=json.loads(path.read_text()); v=json.loads(verify.read_text())
            assert d['status']=='ok' and d['measured_processing_total_s']>0, path
            assert v['ok'] and v['versions_ok'] and all(v['counters_ok'].values()), verify
            if arm=='candidate': assert v['natural_match'] is True,verify
            runs.append(d)
        times=[r['measured_processing_total_s'] for r in runs]
        arms[arm]={'n':len(times),'times_s':times,'mean_s':statistics.mean(times),
                   'sd_s':statistics.stdev(times),
                   'max_pg_pss_bytes':max(r['peak_pg_pss_bytes'] for r in runs),
                   'max_total_pss_bytes':max(r['peak_total_pss_bytes'] for r in runs),
                   'max_temp_bytes':max(r['temp_bytes_written'] for r in runs)}
    ratios=[a/b for a,b in zip(arms['control']['times_s'],arms['candidate']['times_s'])]
    logs=[math.log(r) for r in ratios]
    mean=statistics.mean(logs); g=math.exp(mean)
    # Analytic two-sided 95% t quantile, df=2.
    q=.95; tcrit=math.sqrt(2*q*q/(1-q*q))
    half=tcrit*statistics.stdev(logs)/math.sqrt(3)
    resources=(arms['candidate']['max_pg_pss_bytes']<=1.10*arms['control']['max_pg_pss_bytes']
               and arms['candidate']['max_total_pss_bytes']<=1.10*arms['control']['max_total_pss_bytes']
               and arms['candidate']['max_temp_bytes']<=arms['control']['max_temp_bytes'])
    sizes.append({'rows':rows,'arms':arms,'paired_speedups':ratios,'geometric_speedup':g,
                  'geometric_speedup_t95_ci':[math.exp(mean-half),math.exp(mean+half)],
                  'resource_criterion':resources,
                  'improvement_criterion':g>=1.10 and min(ratios)>1,
                  'no_regression_criterion':g>=.98 and min(ratios)>=.95})
reference=json.loads(args.reference_3m.read_text())['natural']
reference_matches=[]
for arm in ('control','candidate'):
    for rep in (1,2,3):
        path=args.results/'r3000000'/f'verify_confirm_{arm}_rep{rep}.json'
        reference_matches.append(json.loads(path.read_text())['natural']==reference)
accepted=(any(s['improvement_criterion'] for s in sizes)
          and all(s['no_regression_criterion'] and s['resource_criterion'] for s in sizes)
          and all(reference_matches))
output={'accepted_per_preregistered_performance_criteria':accepted,
        'sizes':sizes,'archived_original_3m_reference_match':all(reference_matches),
        'reference_sha256':hashlib.sha256(args.reference_3m.read_bytes()).hexdigest(),
        'uncertainty':'n=3 pairs per size; t intervals assume approximately normal log ratios. Local results only.'}
args.out.write_text(json.dumps(output,indent=2),encoding='utf-8')
print(json.dumps(output))
raise SystemExit(0 if accepted else 1)
