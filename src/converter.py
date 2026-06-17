"""Konvertiert CSV-Dateien nach Parquet via DuckDB."""
from pathlib import Path

import duckdb

CSV_DIR = Path(__file__).parent.parent / "data" / "csv"
PARQUET_DIR = Path(__file__).parent.parent / "data" / "parquet"

TABLES = ["kontakte", "gewerke", "artikel", "projekte", "einkaufspositionen"]


def convert_all() -> None:
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    print("Konvertiere CSV nach Parquet...")
    for table in TABLES:
        src = CSV_DIR / f"{table}.csv"
        dst = PARQUET_DIR / f"{table}.parquet"
        if not src.exists():
            print(f"  FEHLER: {src} nicht gefunden — bitte zuerst 'pllm generate' ausführen")
            continue
        con.execute(
            f"COPY (SELECT * FROM read_csv_auto('{src.as_posix()}', nullstr='')) "
            f"TO '{dst.as_posix()}' (FORMAT PARQUET)"
        )
        count = con.execute(f"SELECT COUNT(*) FROM '{dst.as_posix()}'").fetchone()[0]
        print(f"  {dst.name}: {count} Zeilen")
    con.close()
    print("Fertig!")
