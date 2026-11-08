#!/bin/bash
# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
python3 /work/bench/confirm_candidate.py "$@"
