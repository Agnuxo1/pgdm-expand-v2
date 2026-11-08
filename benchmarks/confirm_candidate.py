# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
"""Counterbalanced confirmation against a separately archived control engine.

Run inside the PG16 benchmark container with /work/control, /work/solution and
/work/upstream. The official input/recipes and timing rule are unchanged.
"""
import argparse
import json
import subprocess
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('rows', type=int)
ap.add_argument('unused', nargs='?', default='')
ap.add_argument('reps', type=int, nargs='?', default=3)
ap.add_argument('--candidate-config', default='{"bound_chunk_joins":false}')
args = ap.parse_args()
config = json.loads(args.candidate_config)
root = Path('/work')
out = Path('/results') / f'r{args.rows}'
out.mkdir(parents=True, exist_ok=True)
subprocess.run(['bash', str(root/'bench/ensure_data.sh'), str(args.rows)], check=True)
original_reference = out/'verify_baseline_rep1.json'
control_reference = out/'verify_confirm_control_rep1.json'
for rep in range(1,args.reps+1):
    order = ('control','candidate') if rep % 2 else ('candidate','control')
    for arm in order:
        tag = f'confirm_{arm}_rep{rep}'
        result_path = out/f'{tag}.json'
        if result_path.exists():
            raise SystemExit(f'Refusing to overwrite existing result: {result_path}')
        print(json.dumps({'event':'start','rows':args.rows,'pair':rep,'arm':arm}), flush=True)
        subprocess.run(['bash',str(root/'bench/reset.sh')], check=True, stdout=subprocess.DEVNULL)
        app = root/('control' if arm=='control' else 'solution')
        command = ['python3',str(root/'bench/harness.py'),'--app-dir',str(app),
                   '--tag',tag,'--out',str(out),'--recipes',str(root/'upstream/SQL files')]
        if arm == 'candidate':
            command += ['--env','PDM_EXPAND_V2_CONFIG='+json.dumps(config,separators=(',',':'))]
        subprocess.run(command, check=True)
        verification = out/f'verify_{tag}.json'
        reference = original_reference if original_reference.exists() else control_reference
        command = ['python3',str(root/'bench/verify.py'),'--out',str(verification)]
        if reference.exists():
            command += ['--expect',str(reference)]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        check = json.loads(verification.read_text())
        assert check['ok'] and check['versions_ok'] and all(check['counters_ok'].values()), check
        if arm=='candidate':
            assert check.get('natural_match') is True, check
        print(json.dumps({'event':'verified','rows':args.rows,'pair':rep,'arm':arm,
                          'natural_match':check.get('natural_match')}), flush=True)
print(json.dumps({'event':'confirmation_complete','rows':args.rows,'pairs':args.reps}), flush=True)
