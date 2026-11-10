import sys
from typing import List, Tuple

try:
    import trino
except ImportError:
    trino = None


def get_trino_connection(host: str = "localhost", port: int = 8080, user: str = "admin", http_scheme: str = "http", request_timeout: int = 3600, password: str = "", verify_ssl: bool = True):
    """Establish and return a Trino connection."""
    if trino is None:
        raise ImportError("The 'trino' Python package is not installed. Install it with: pip install trino")
    kwargs = dict(
        host=host,
        port=port,
        user=user,
        http_scheme=http_scheme,
        request_timeout=request_timeout,  # default 1-hour cap for long queries, overrideable for fast probes
        verify=verify_ssl,
    )
    if password:
        kwargs["auth"] = trino.auth.BasicAuthentication(user, password)
    return trino.dbapi.connect(**kwargs)


def test_trino_connection(host: str, port: int, user: str, http_scheme: str = "http", timeout: int = 5, password: str = "", verify_ssl: bool = True) -> Tuple[bool, str]:
    """Test Trino connectivity with a lightweight query and fast failover timeout."""
    try:
        conn = get_trino_connection(host=host, port=port, user=user, http_scheme=http_scheme, request_timeout=timeout, password=password, verify_ssl=verify_ssl)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        return True, "Connection successful"
    except Exception as e:
        return False, str(e)


def fetch_trino_catalogs(host: str, port: int, user: str, http_scheme: str = "http", timeout: int = 8, password: str = "", verify_ssl: bool = True) -> Tuple[bool, List[str], str]:
    """Run SHOW CATALOGS to retrieve all active catalogs in Trino with quick timeout."""
    try:
        conn = get_trino_connection(host=host, port=port, user=user, http_scheme=http_scheme, request_timeout=timeout, password=password, verify_ssl=verify_ssl)
        cursor = conn.cursor()
        cursor.execute("SHOW CATALOGS")
        rows = cursor.fetchall()
        catalogs = [r[0] for r in rows if r[0] not in ("system",)]
        cursor.close()
        conn.close()
        return True, catalogs, "Catalogs fetched successfully"
    except Exception as e:
        return False, ["postgres", "oracle"], str(e)


def fetch_schemas(catalog: str, host: str, port: int, user: str, http_scheme: str = "http", password: str = "", verify_ssl: bool = True) -> List[str]:
    """Fetch schemas from a given catalog."""
    try:
        conn = get_trino_connection(host=host, port=port, user=user, http_scheme=http_scheme, password=password, verify_ssl=verify_ssl)
        cursor = conn.cursor()
        cursor.execute(f"SHOW SCHEMAS FROM {catalog}")
        rows = cursor.fetchall()
        schemas = [r[0] for r in rows if r[0] not in ("information_schema",)]
        cursor.close()
        conn.close()
        return schemas
    except Exception:
        return ["curated", "rdm", "historical"]
