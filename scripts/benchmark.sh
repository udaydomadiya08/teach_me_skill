#!/usr/bin/env bash
set -euo pipefail

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

echo "==> Running baseline latency and footprint benchmark..."
python -m teach_a_skill benchmark

echo "==> Running Phase 2 recorder stress & performance benchmark..."
python -m teach_a_skill benchmark recorder

echo "==> Running Phase 3 teaching layer stress & footprint benchmark..."
python -m teach_a_skill benchmark teach

echo "==> Running Phase 14 security & platform benchmark..."
python -m teach_a_skill security audit --quiet

echo "==> Running Phase 15 production validation & benchmarks..."
python scripts/verify_phase15_production.py

