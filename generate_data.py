#!/usr/bin/env python3
"""Generate and reconcile every synthetic dataset.

Usage:
    python generate_data.py                 # writes data/ and runs checks
    python generate_data.py --output data  # explicit output directory
"""
from __future__ import annotations

import argparse
from pathlib import Path

from src.config import load_config
from src.data_generator import SyntheticDataGenerator, write_datasets
from src.reconciliation import print_reconciliation, reconcile, write_reconciliation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config", help="Configuration directory")
    parser.add_argument("--output", default="data", help="Generated CSV directory")
    args = parser.parse_args()

    config = load_config(args.config)
    generator = SyntheticDataGenerator(config)
    datasets = generator.generate()
    Path(args.output).mkdir(parents=True, exist_ok=True)
    write_datasets(datasets, args.output)
    checks = reconcile(datasets, config)
    write_reconciliation(checks, args.output)
    print_reconciliation(checks)
    print(f"\nWrote {len(datasets)} CSV datasets + assumptions.xlsx to {Path(args.output).resolve()}")
    if not checks["status"].eq("PASS").all():
        print("Generation failed reconciliation; inspect data/reconciliation_checks.csv")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
