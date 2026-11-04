# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Reuse: preserve applicable notices and cite the original author.

"""Darwin-Cage autotuner for the PGDM Expand v2 configuration.

Darwin-Cage (F. Angulo de Lafuente) is a chaos-driven evolutionary algorithm:
a logistic map x_{t+1} = r x_t (1 - x_t), r = 3.99 (positive Lyapunov exponent)
modulates the tournament size k = max(2, floor(k_base (0.5 + c_t))) and the
mutation strength sigma = sigma_base (0.2 + 1.5 c_t) at every generation, so the
search alternates between exploitation and exploration without stagnating.

Here the genome is a discrete configuration of the expansion engine (workers,
chunk size, session GUCs).  Fitness is the official MEASURED PROCESSING TOTAL of a
full Expand run on a database produced by the unmodified official generator;
runs whose output does not match the reference digest are rejected (fitness inf).

Usage (inside the benchmark container, see benchmarks/):
  python3 tools/darwin_cage_tuner.py --evaluate "bash benchmarks/eval_config.sh" \
      --generations 4 --population 6 --seed 7 --out tuning.json
The evaluate command receives the candidate as PDM_EXPAND_V2_CONFIG (JSON) and must
print one JSON line with "measured_processing_total_s" and "valid" (bool).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import shlex
import subprocess
import time

SPACE = {
    "workers_per_core": [0.5, 0.75, 1.0, 1.5, 2.0],
    "global_parallel": [0, 2, 4],
    "chunk_rows": [10000, 25000, 50000, 100000, 200000],
    "source_mode": ["plain", "detoast"],
    "work_mem": ["4MB", "16MB", "64MB", "256MB"],
    "jit": ["on", "off"],
    "synchronous_commit": ["on", "off"],
    "enable_hashjoin": ["on", "off"],
}
GENES = list(SPACE)


def decode(genome: dict) -> dict:
    return {
        "workers": "auto",
        "workers_per_core": genome["workers_per_core"],
        "global_parallel": genome["global_parallel"],
        "chunk_rows": genome["chunk_rows"],
        "source_mode": genome["source_mode"],
        "session_gucs": {
            "work_mem": genome["work_mem"],
            "jit": genome["jit"],
            "synchronous_commit": genome["synchronous_commit"],
            "enable_hashjoin": genome["enable_hashjoin"],
        },
        "global_gucs": {"work_mem": genome["work_mem"], "jit": genome["jit"]},
    }


def key(genome: dict) -> str:
    return json.dumps({g: genome[g] for g in GENES}, sort_keys=True)


class Chaos:
    """Logistic map in the chaotic regime (Darwin-Cage chaos engine)."""

    def __init__(self, r: float = 3.99, x0: float = 0.4123):
        self.r = r
        self.x = x0

    def next(self) -> float:
        self.x = self.r * self.x * (1.0 - self.x)
        return self.x


def mutate(genome: dict, sigma: float, rng: random.Random) -> dict:
    child = dict(genome)
    for gene in GENES:
        values = SPACE[gene]
        if rng.random() < min(0.9, 0.25 + sigma):
            index = values.index(child[gene])
            step = int(round(rng.gauss(0.0, max(0.5, sigma * len(values)))))
            if step == 0:
                step = rng.choice((-1, 1))
            child[gene] = values[max(0, min(len(values) - 1, index + step))]
    return child


def crossover(a: dict, b: dict, c_t: float, rng: random.Random) -> dict:
    # Chaos-blended uniform crossover: c_t biases inheritance towards parent a.
    return {g: (a[g] if rng.random() < 0.5 + 0.4 * (c_t - 0.5) else b[g]) for g in GENES}


def tournament(population, fitness, k: int, rng: random.Random) -> dict:
    contenders = rng.sample(population, min(k, len(population)))
    return min(contenders, key=lambda g: fitness[key(g)])


def evaluate(command: str, genome: dict, log: list, timeout: int) -> float:
    env = dict(os.environ)
    env["PDM_EXPAND_V2_CONFIG"] = json.dumps(decode(genome), sort_keys=True)
    started = time.time()
    try:
        proc = subprocess.run(shlex.split(command), env=env, capture_output=True, text=True, timeout=timeout)
        lines = [line for line in proc.stdout.splitlines() if line.strip().startswith("{")]
        result = json.loads(lines[-1]) if lines else {}
    except Exception as exc:  # recorded, scored as invalid
        result = {"error": str(exc)}
    value = float(result.get("measured_processing_total_s") or math.inf)
    if not result.get("valid"):
        value = math.inf
    log.append({"genome": genome, "fitness": value, "result": result, "eval_wall_s": time.time() - started})
    print(json.dumps({"eval": len(log), "fitness": value, "genome": genome}), flush=True)
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluate", required=True)
    ap.add_argument("--generations", type=int, default=4)
    ap.add_argument("--population", type=int, default=6)
    ap.add_argument("--k-base", type=int, default=3)
    ap.add_argument("--sigma-base", type=float, default=0.35)
    ap.add_argument("--r", type=float, default=3.99)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--seed-config", action="append", default=[],
                    help="JSON genome inserted in the initial population (e.g. the hand-tuned control)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    chaos = Chaos(args.r)
    population = [json.loads(item) for item in args.seed_config]
    while len(population) < args.population:
        population.append({g: rng.choice(SPACE[g]) for g in GENES})
    fitness: dict[str, float] = {}
    log: list = []
    history = []
    for generation in range(args.generations):
        for genome in population:
            if key(genome) not in fitness:
                fitness[key(genome)] = evaluate(args.evaluate, genome, log, args.timeout)
        ranked = sorted(population, key=lambda g: fitness[key(g)])
        c_t = chaos.next()
        k = max(2, int(math.floor(args.k_base * (0.5 + c_t))))
        sigma = args.sigma_base * (0.2 + 1.5 * c_t)
        history.append({"generation": generation, "chaos": c_t, "tournament_k": k, "sigma": sigma,
                        "best": ranked[0], "best_fitness": fitness[key(ranked[0])]})
        print(json.dumps(history[-1]), flush=True)
        if generation == args.generations - 1:
            break
        children = [ranked[0]]  # elitism
        attempts = 0
        while len(children) < args.population and attempts < 200:
            attempts += 1
            a = tournament(population, fitness, k, rng)
            b = tournament(population, fitness, k, rng)
            child = mutate(crossover(a, b, chaos.next(), rng), sigma, rng)
            if all(key(child) != key(c) for c in children):
                children.append(child)
        population = children
    best = min(fitness, key=fitness.get)
    out = {"best_genome": json.loads(best), "best_config": decode(json.loads(best)),
           "best_fitness": fitness[best], "history": history, "evaluations": log,
           "params": vars(args)}
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({"best": json.loads(best), "fitness": fitness[best]}))


if __name__ == "__main__":
    main()
