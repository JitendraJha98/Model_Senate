"""Evaluation harness — proves the Council beats single models, self-consistency, and
naive councils, with reproducible accuracy / calibration / cost / latency metrics.

Entry point: `python -m backend.eval.run`. All scoring is offline and deterministic;
CI drives it with fake adapters (no network).
"""
