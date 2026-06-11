"""Isolation & determinism verification probes (docs/isolation-determinism-plan.md).

Live, evidence-producing checks that every engine is tested fresh:

- ``canary`` — Test A: memory-probe canary, proves statelessness empirically.
- ``determinism`` — Test D: K-repeat baseline, quantifies normal noise per engine.
- ``shuffle`` — Test C: order-shuffle, shows no cross-query leakage.

The payload assertions (Test B) live in ``tests/test_isolation.py``; payload
logging (Test E) lives in ``src/engines/payload_log.py``.
"""
