"""
Caches real BigQuery columns + embeddings in memory, computed once
(lazily, on first use). Each column is enriched with its table's
business description from Dataplex — fetched via ONE targeted lookup
per table (not a broad catalog search), so matching is both clean
(no dataset/domain/system-entry noise) and carries real business
context where it exists.

Cache is process-lifetime only (resets when the server restarts).
Call invalidate_cache() after creating a new data product so it shows
up in matching without a full restart.
"""

import threading
from tools.catalog_client import list_columns_for_matching, get_table_entry_metadata
from tools.embeddings import get_embedding, build_attribute_text

_cache = []
_lock = threading.Lock()
_built = False


def get_catalog_embeddings():
    """
    Returns [{table_name, column_name, dataset, data_type,
    table_description, embedding}, ...] — one entry per real BigQuery
    column, built once per server run.
    """
    global _built
    if _built:
        return _cache

    with _lock:
        if _built:
            return _cache

        columns = list_columns_for_matching()

        # Fetch each table's business description ONCE, not once per
        # column — a targeted lookup, not a broad search.
        table_descriptions = {}
        for col in columns:
            table_key = (col["dataset"], col["table_name"])
            if table_key not in table_descriptions:
                meta = get_table_entry_metadata(col["dataset"], col["table_name"])
                table_descriptions[table_key] = meta.get("description", "")

        for col in columns:
            table_key = (col["dataset"], col["table_name"])
            table_desc = table_descriptions.get(table_key, "")

            context = f"column in table {col['table_name']}, type {col['data_type']}"
            if table_desc:
                context += f". Table description: {table_desc}"

            text = build_attribute_text(col["column_name"], [], context)
            _cache.append({
                **col,
                "table_description": table_desc,
                "embedding": get_embedding(text),
            })

        _built = True

    return _cache


def invalidate_cache():
    """Call this after registering a new data product so it shows up in matching."""
    global _built
    with _lock:
        _cache.clear()
        _built = False
