"""DuckDB-Schnittstelle: lädt Parquet-Views und führt SQL aus."""
import threading
from pathlib import Path

import duckdb
import pandas as pd

PARQUET_DIR = Path(__file__).parent.parent / "data" / "parquet"
TABLES = ["kontakte", "gewerke", "artikel", "projekte", "einkaufspositionen"]

_con: duckdb.DuckDBPyConnection | None = None
_lock = threading.Lock()


def _connect() -> duckdb.DuckDBPyConnection:
    global _con
    if _con is not None:
        return _con
    _con = duckdb.connect()
    missing = []
    for table in TABLES:
        path = PARQUET_DIR / f"{table}.parquet"
        if path.exists():
            _con.execute(
                f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM read_parquet('{path.as_posix()}')"
            )
        else:
            missing.append(table)
    if missing:
        raise FileNotFoundError(
            f"Parquet-Dateien fehlen: {missing}. Bitte 'pllm init' ausführen."
        )
    return _con


def execute(sql: str) -> tuple[pd.DataFrame | None, str | None]:
    """Führt SQL aus. Gibt (DataFrame, None) oder (None, Fehlermeldung) zurück."""
    try:
        with _lock:
            con = _connect()
            df = con.execute(sql).df()
        return df, None
    except FileNotFoundError as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)


def reset() -> None:
    """Trennt und verwirft die bestehende Verbindung (z.B. nach Parquet-Neugenerierung)."""
    global _con
    if _con is not None:
        try:
            _con.close()
        except Exception:
            pass
        _con = None
