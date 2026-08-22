"""Analysis of match-integrity signals.

Reads marts and nothing else. If a column is missing here, the fix is a dbt
model in ``warehouse/``, never a reach back to ``data/parquet/`` or the raw JSON.
"""
