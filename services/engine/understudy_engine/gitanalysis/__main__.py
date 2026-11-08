"""``uv run --package understudy-agent python -m understudy_engine.gitanalysis [--fast]`` prints the git evaluation as JSON."""
from __future__ import annotations

import argparse
import json

from .evaluate import evaluate_git


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate the git analysis layer on generated repositories (no network, no model needed).")
    ap.add_argument("--fast", action="store_true", help="3 replicates, fewer bootstrap draws")
    args = ap.parse_args()
    print(json.dumps(evaluate_git(fast=args.fast), indent=1))


if __name__ == "__main__":
    main()
