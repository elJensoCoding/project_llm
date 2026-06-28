"""Konvertiert CSV-Dateien nach Parquet via DuckDB (einfach, ohne Typisierung)."""
from pathlib import Path

import duckdb


def convert_all() -> None:
    from . import config
    csv_dir     = config.csv_dir()
    parquet_dir = config.parquet_dir()

    parquet_dir.mkdir(parents=True, exist_ok=True)
    csv_files = sorted(csv_dir.glob("*.csv"))
    if not csv_files:
        print(f"  FEHLER: Keine CSV-Dateien in {csv_dir} — bitte zuerst 'pllm generate' ausführen")
        return

    con = duckdb.connect()
    print(f"Konvertiere CSV → Parquet  ({csv_dir} → {parquet_dir})")
    for src in csv_files:
        dst = parquet_dir / f"{src.stem}.parquet"
        con.execute(
            f"COPY (SELECT * FROM read_csv_auto('{src.as_posix()}', nullstr='')) "
            f"TO '{dst.as_posix()}' (FORMAT PARQUET)"
        )
        count = con.execute(f"SELECT COUNT(*) FROM '{dst.as_posix()}'").fetchone()[0]
        print(f"  {dst.name}: {count} Zeilen")
    con.close()
    print("Fertig!")
