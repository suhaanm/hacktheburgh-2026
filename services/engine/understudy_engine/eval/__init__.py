"""Evaluation harness (ANA-15, EVL-1, SEC-12, VIS-6): `uv run --package understudy-agent python -m understudy_engine.eval`.

Assembles evals/report.json (what the Evidence page renders) and evals/report.md from the owning tracks' code.
"""
from .assemble import build_report, deterministic_view, dumps
from .schema import errors as schema_errors
from .schema import load_schema, validate

__all__ = ["build_report", "deterministic_view", "dumps", "schema_errors", "load_schema", "validate"]
