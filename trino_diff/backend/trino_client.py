import sys
from typing import List, Tuple, Optional

try:
    import trino
except ImportError:
    trino = None


def get_trino_connection(host: str = "localhost", port: int = 8080, user: str = "admin", http_scheme: str = "http"):
    """Establish and return a Trino connection."""
    if trino is None:
        raise ImportError("The 'trino' Python package is not installed. Install it with: pip install trino")
    return trino.dbapi.connect(
        host=host,
        port=port,
        user=user,
        http_scheme=http_scheme,
        request_timeout=3600,  # 1-hour cap; raises instead of hanging if the pod dies mid-query
    )


def test_trino_connection(host: str, port: int, user: str, http_scheme: str = "http") -> Tuple[bool, str]:
    """Test Trino connectivity with a lightweight query."""
    try:
        conn = get_trino_connection(host=host, port=port, user=user, http_scheme=http_scheme)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        return True, "Connection successful"
    except Exception as e:
        return False, str(e)


def fetch_trino_catalogs(host: str, port: int, user: str, http_scheme: str = "http") -> Tuple[bool, List[str], str]:
    """Run SHOW CATALOGS to retrieve all active catalogs in Trino."""
    try:
        conn = get_trino_connection(host=host, port=port, user=user, http_scheme=http_scheme)
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
    http_scheme: str = "http"
) -> Tuple[Optional[str], List[dict]]:
    """Query information_schema to find columns and resolved schema for table."""
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
                return sch, cols
        cursor.close()
        conn.close()
    except Exception:
        pass
    return None, []
