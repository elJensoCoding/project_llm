"""DuckDB-Schnittstelle: lädt Parquet-Views und führt SQL aus."""
import threading
from pathlib import Path

import duckdb
import pandas as pd

from . import config

_con: duckdb.DuckDBPyConnection | None = None
_lock = threading.Lock()


def _connect() -> duckdb.DuckDBPyConnection:
    global _con
    if _con is not None:
        return _con

    db = config.db_path()
    if db:
        # Persistente DuckDB — Tabellen bereits vorhanden
        _con = duckdb.connect(db)
    else:
        # In-memory + Parquet-Views
        _con = duckdb.connect()
        parquet_dir = config.parquet_dir()
        parquet_files = sorted(parquet_dir.glob("*.parquet"))
        if not parquet_files:
            raise FileNotFoundError(
                f"Keine Parquet-Dateien in {parquet_dir}. Bitte 'pllm init' ausführen."
            )
        for path in parquet_files:
            _con.execute(
                f"CREATE OR REPLACE VIEW {path.stem} AS "
                f"SELECT * FROM read_parquet('{path.as_posix()}')"
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
