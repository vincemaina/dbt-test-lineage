"""dbt-test-lineage: propagate dbt test guarantees (not_null / unique) through column lineage.

Consumes the dbt-column-lineage engine's fact-only IR and renders verdicts: where a declared test's
guarantee is contradicted, missing, or redundant. See docs/architecture.md.
"""

__version__ = "0.1.0"
