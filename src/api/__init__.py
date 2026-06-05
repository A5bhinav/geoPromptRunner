"""Thin FastAPI wrapper around the existing GEO audit pipeline.

This package is the only new backend code the UI introduces. It parses uploaded
CSVs (``src.prompts.csv_loader``), calls the existing pipeline functions
(``run_query_set``, the engine adapters, metrics, the judge), and reports
progress — it does not reimplement any of them.
"""

from __future__ import annotations

__all__: list[str] = []
