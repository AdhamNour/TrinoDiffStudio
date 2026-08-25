import sys
from typing import List, Tuple, Optional

try:
    import trino
except ImportError:
    trino = None


def get_trino_connection(host: str = "localhost", port: int = 8080, user: str = "admin", http_scheme: str = "http", request_timeout: int = 3600):
    """Establish and return a Trino connection."""
    if trino is None:
        raise ImportError("The 'trino' Python package is not installed. Install it with: pip install trino")
    return trino.dbapi.connect(
        host=host,
        port=port,
        user=user,
        http_scheme=http_scheme,
        request_timeout=request_timeout,  # default 1-hour cap for long queries, overrideable for fast probes
    )


def test_trino_connection(host: str, port: int, user: str, http_scheme: str = "http", timeout: int = 5) -> Tuple[bool, str]:
    """Test Trino connectivity with a lightweight query and fast failover timeout."""
    try:
        conn = get_trino_connection(host=host, port=port, user=user, http_scheme=http_scheme, request_timeout=timeout)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        return True, "Connection successful"
    except Exception as e:
        return False, str(e)


def fetch_trino_catalogs(host: str, port: int, user: str, http_scheme: str = "http", timeout: int = 8) -> Tuple[bool, List[str], str]:
    """Run SHOW CATALOGS to retrieve all active catalogs in Trino with quick timeout."""
    try:
        conn = get_trino_connection(host=host, port=port, user=user, http_scheme=http_scheme, request_timeout=timeout)
        cursor = conn.cursor()
        cursor.execute("SHOW CATALOGS")
        rows = cursor.fetchall()
        catalogs = [r[0] for r in rows if r[0] not in ("system",)]
        cursor.close()
        conn.close()
        return True, catalogs, "Catalogs fetched successfully"
    except Exception as e:
        return False, ["postgres", "oracle"], str(e)


def fetch_schemas(catalog: str, host: str, port: int, user: str, http_scheme: str = "http") -> List[str]:
    """Fetch schemas from a given catalog."""
    try:
        conn = get_trino_connection(host=host, port=port, user=user, http_scheme=http_scheme)
        cursor = conn.cursor()
        cursor.execute(f"SHOW SCHEMAS FROM {catalog}")
        rows = cursor.fetchall()
        schemas = [r[0] for r in rows if r[0] not in ("information_schema",)]
        cursor.close()
        conn.close()
        return schemas
    except Exception:
        return ["curated", "rdm"]


def fetch_columns_for_table(
    table_name: str,
    catalog: str,
    schemas: List[str],
    host: str,
    port: int,
    user: str,
    http_scheme: str = "http",
    exclude_cols: List[str] = None,
    exclude_suffix: str = None,
    id_columns: List[str] = None,
) -> Tuple[Optional[str], List[dict]]:
    """Query information_schema to find columns and resolved schema for table with early exclusion filtering."""
    id_set = {ic.strip().lower() for ic in (id_columns or []) if ic and ic.strip()}
    excluded_set = {c.strip().lower() for c in (exclude_cols or []) if c and c.strip()}
    suf_lower = exclude_suffix.strip().lower() if exclude_suffix and exclude_suffix.strip() else None

    def _filter_cols(raw_cols):
        if not excluded_set and not suf_lower:
            return raw_cols
        filtered = []
        for c in raw_cols:
            cname = c["name"].lower()
            if cname in id_set:
                filtered.append(c)
                continue
            if cname in excluded_set:
                continue
            if suf_lower and cname.endswith(suf_lower):
                continue
            filtered.append(c)
        return filtered

    try:
        conn = get_trino_connection(host=host, port=port, user=user, http_scheme=http_scheme)
        cursor = conn.cursor()
        for sch in schemas:
            sql = (
                f"SELECT column_name, data_type "
                f"FROM {catalog}.information_schema.columns "
                f"WHERE table_schema = '{sch}' "
                f"  AND table_name = '{table_name}' "
                f"ORDER BY ordinal_position"
            )
            cursor.execute(sql)
            rows = cursor.fetchall()
            if rows:
                cols = [{"name": r[0], "data_type": r[1].lower()} for r in rows]
                cursor.close()
                conn.close()
                return sch, _filter_cols(cols)
        cursor.close()
        conn.close()
    except Exception:
        pass
    return None, []
