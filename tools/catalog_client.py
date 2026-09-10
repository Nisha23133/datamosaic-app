"""
Wraps Google Cloud Dataplex (Knowledge Catalog) API calls.
Every other module talks to the catalog through here — nothing else
should import google.cloud.dataplex_v1 directly.
"""

from google.cloud import dataplex_v1
import re
import config


def _catalog_client():
    return dataplex_v1.CatalogServiceClient()


def list_all_entries(page_size: int = 100) -> list[dict]:
    """
    Fetch all catalog entries in one broad call, rather than doing a
    fresh narrow search per uploaded attribute. Used to build a
    reusable embedding cache (see tools/catalog_cache.py) since your
    catalog is small enough (a handful of tables) that recomputing
    this per-attribute is wasted, slow, repeated work.
    """
    return search_catalog(query="*", page_size=page_size)


def get_table_entry_metadata(dataset: str, table_name: str) -> dict:
    """
    Targeted lookup of a SPECIFIC table's Dataplex catalog entry.
    Returns description, domain, and owner.
    """
    client = _catalog_client()
    entry_name = (
        f"projects/{config.PROJECT_ID}/locations/{config.LOCATION}"
        f"/entryGroups/@bigquery/entries/bigquery.googleapis.com/projects/"
        f"{config.PROJECT_ID}/datasets/{dataset}/tables/{table_name}"
    )
    result = {"description": "", "domain": "Unassigned", "owner": "Platform Team", "found": False}
    try:
        entry = client.get_entry(name=entry_name)
        result["description"] = entry.entry_source.description or ""
        result["found"] = True

        # Best-effort extraction from aspects
        for aspect_key, aspect in entry.aspects.items():
            key_lower = aspect_key.lower()
            data = dict(aspect.data) if aspect.data is not None else {}
            if "domain" in key_lower and data.get("displayName"):
                result["domain"] = data["displayName"]
            if ("contact" in key_lower or "owner" in key_lower) and data.get("identities"):
                identities = data["identities"]
                if isinstance(identities, list) and identities:
                    result["owner"] = identities[0].get("id", result["owner"])
    except Exception:
        pass

    # If domain is unassigned, map common curated/known datasets to appropriate enterprise domains
    if result["domain"] == "Unassigned":
        name_lower = table_name.lower()
        if "customer" in name_lower or "user" in name_lower:
            result["domain"] = "Customer"
        elif "order" in name_lower or "sales" in name_lower or "product" in name_lower:
            result["domain"] = "Sales"
        elif "ticket" in name_lower or "support" in name_lower:
            result["domain"] = "Customer Support"
        elif dataset == config.CURATED_DATASET:
            result["domain"] = "Enterprise Curated"
        elif dataset == config.ECOMMERCE_DATASET:
            result["domain"] = "Sales & Operations"

    return result


def list_columns_for_matching() -> list[dict]:
    """
    Returns clean {table_name, column_name, data_type} entries pulled
    directly from BigQuery's INFORMATION_SCHEMA — used to build the
    matching cache.
    """
    from google.cloud import bigquery
    client = bigquery.Client(project=config.PROJECT_ID)

    datasets_to_scan = [config.CURATED_DATASET, config.ECOMMERCE_DATASET, config.SUPPORT_DATASET]
    results = []

    for dataset in datasets_to_scan:
        query = f"""
            SELECT table_name, column_name, data_type
            FROM `{config.PROJECT_ID}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
        """
        try:
            for row in client.query(query).result():
                results.append({
                    "table_name": row.table_name,
                    "column_name": row.column_name,
                    "data_type": row.data_type,
                    "dataset": dataset,
                })
        except Exception:
            continue

    return results


def _parse_bq_table_from_resource_name(full_resource_name: str) -> tuple:
    """Extracts (dataset, table) from a Dataplex bigquery-table resource name."""
    match = re.search(r"datasets/([^/]+)/tables/([^/]+)", full_resource_name)
    if match:
        return match.group(1), match.group(2)
    return None, None


def list_data_products_with_governance() -> list[dict]:
    """
    Returns every real data product (BigQuery table) with its domain
    and owner, for the sidebar's grouped view.
    Also merges any approved data product requests from the governance store.
    """
    from google.cloud import bigquery
    bq_client = bigquery.Client(project=config.PROJECT_ID)

    # 1. Fetch approved requests from the data_product_requests table for governance metadata
    approved_map = {}
    try:
        req_query = f"""
            SELECT product_name, domain, requested_by, business_justification, table_full_name
            FROM `{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.REQUESTS_TABLE}`
            WHERE status = 'APPROVED'
        """
        for row in bq_client.query(req_query).result():
            approved_map[row.product_name.lower()] = {
                "domain": row.domain,
                "owner": row.requested_by,
                "description": row.business_justification,
            }
    except Exception:
        pass

    # 2. Query BigQuery datasets directly to ensure all real data products are listed
    datasets = [config.CURATED_DATASET, config.ECOMMERCE_DATASET, config.SUPPORT_DATASET]
    ignored_tables = {"recommendation_feedback", "learned_aliases", "data_product_requests"}
    products = []

    for dataset in datasets:
        try:
            tables = list(bq_client.list_tables(f"{config.PROJECT_ID}.{dataset}"))
            for t in tables:
                tbl_id = t.table_id
                if tbl_id in ignored_tables:
                    continue

                meta = get_table_entry_metadata(dataset, tbl_id)
                # Check if this table was registered/approved via request workflow
                if tbl_id.lower() in approved_map:
                    appr = approved_map[tbl_id.lower()]
                    domain = appr["domain"] or meta["domain"]
                    owner = appr["owner"] or meta["owner"]
                    desc = appr["description"] or meta["description"]
                else:
                    domain = meta["domain"]
                    owner = meta["owner"]
                    desc = meta["description"]

                products.append({
                    "name": tbl_id,
                    "dataset": dataset,
                    "domain": domain,
                    "owner": owner,
                    "description": desc,
                })
        except Exception:
            continue

    return products


def search_data_products(query: str, page_size: int = 10) -> list[dict]:
    """
    Search for actual data products (BigQuery tables only) — filters out
    domains, entry groups, and other non-product catalog objects that a
    raw search_catalog() call returns. Each result includes its real
    column list, pulled directly from BigQuery rather than relying on
    Dataplex schema aspects (which aren't reliably populated).
    """
    raw_results = search_catalog(query, page_size=page_size)
    if raw_results and "error" in raw_results[0]:
        return raw_results

    from google.cloud import bigquery
    bq_client = bigquery.Client(project=config.PROJECT_ID)

    products = []
    for entry in raw_results:
        if "bigquery-table" not in entry.get("entry_type", ""):
            continue  # skip domains, entry groups, etc.

        dataset, table = _parse_bq_table_from_resource_name(entry.get("full_resource_name", ""))
        fields = []
        if dataset and table:
            try:
                col_query = f"""
                    SELECT column_name, data_type
                    FROM `{config.PROJECT_ID}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
                    WHERE table_name = '{table}'
                """
                fields = [{"name": r.column_name, "type": r.data_type} for r in bq_client.query(col_query).result()]
            except Exception:
                pass

        products.append({
            "name": entry["name"],
            "description": entry.get("description", ""),
            "fields": fields,
        })

    return products


def search_catalog(query: str, page_size: int = 10) -> list[dict]:
    """
    Search Knowledge Catalog entries (tables, views) by natural-language query.
    Returns a list of dicts: name, entry_type, description, domain.
    """
    client = _catalog_client()
    scope = f"projects/{config.PROJECT_ID}/locations/global"

    request = dataplex_v1.SearchEntriesRequest(
        name=scope,
        query=query,
        page_size=page_size,
    )

    results = []
    try:
        for item in client.search_entries(request=request):
            entry = item.dataplex_entry
            results.append({
                "name": entry.entry_source.display_name or entry.name,
                "full_resource_name": entry.name,
                "description": entry.entry_source.description or "",
                "entry_type": entry.entry_type,
            })
    except Exception as e:
        # Surface a clean error rather than a raw stack trace to the agent layer
        return [{"error": str(e)}]

    return results


def get_entry_schema(entry_name: str) -> list[dict]:
    """
    Fetch column-level schema (name, type) for a given catalog entry.
    entry_name is the full resource name returned by search_catalog.
    """
    client = _catalog_client()
    entry = client.get_entry(name=entry_name, view=dataplex_v1.EntryView.FULL)

    columns = []
    for aspect_key, aspect in entry.aspects.items():
        if "schema" in aspect_key.lower():
            fields = aspect.data.get("fields", [])
            for f in fields:
                columns.append({
                    "name": f.get("name"),
                    "type": f.get("type"),
                    "description": f.get("description", ""),
                })
    return columns


def create_data_domain(display_name: str, domain_id: str, description: str, owner_email: str) -> dict:
    """
    Create a new governance Data Domain in Knowledge Catalog.
    Safe to call even if it already exists — caller should check first.
    """
    client = dataplex_v1.DataTaxonomyServiceClient()
    parent = f"projects/{config.PROJECT_ID}/locations/{config.LOCATION}"

    # NOTE: Data Domain creation currently requires the Console UI or the
    # Dataplex Universal Catalog REST API's dataDomains resource, which is
    # newer than the stable dataplex_v1 client surface used here. This
    # function is a placeholder that documents the intended call shape —
    # replace the body with a REST call via `requests` + an access token
    # if the client library in requirements.txt doesn't yet expose it.
    return {
        "status": "not_implemented_in_client_library",
        "note": "Create domains manually in console, or call the REST API directly.",
        "requested": {"display_name": display_name, "domain_id": domain_id},
    }


def register_data_product(
    table_full_name: str,
    domain: str,
    owner_email: str,
    description: str,
) -> dict:
    """
    Register a BigQuery table as a governed Data Product.
    table_full_name format: project.dataset.table
    """
    # Same caveat as create_data_domain — Data Product resources are part
    # of the newer Knowledge Catalog surface. This wraps the call shape so
    # agents/recommendation_agent.py has a stable function to call; swap
    # the body for the real REST/Client call once available in your
    # installed library version.
    return {
        "status": "pending_implementation",
        "table": table_full_name,
        "domain": domain,
        "owner": owner_email,
        "description": description,
    }
