"""yaml2duckdb: liest YAML-Profile und lädt CSV-Daten typisiert in DuckDB + Parquet."""
from __future__ import annotations

from pathlib import Path

import duckdb
import yaml
from rich.console import Console

console = Console()


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _col_cast_expr(col: dict) -> str:
    """Baut einen CAST-Ausdruck für eine Spalte aus dem YAML-Profil."""
    name = col["name"]
    dtype = col["duckdb_type"]
    # Spalten mit Umlauten in Anführungszeichen
    quoted = f'"{name}"' if any(c in name for c in "äöüÄÖÜß") else name
    return f"CAST({quoted} AS {dtype}) AS {quoted}"


def load_profile(
    yaml_path: Path,
    db_path: Path | None = None,
    parquet_dir: Path | None = None,
) -> None:
    """Lädt eine YAML-Profildatei und erstellt Tabelle in DuckDB und/oder Parquet."""
    profile = _load_yaml(yaml_path)
    table   = profile["table"]
    source  = Path(profile["source"])

    if not source.exists():
        console.print(f"  [red]CSV nicht gefunden:[/red] {source}")
        return

    # Cast-Ausdrücke aus YAML-Spaltendefinitionen — stellt korrekte Typen sicher
    # (v.a. DOUBLE → DECIMAL für Geldbeträge)
    casts   = ", ".join(_col_cast_expr(c) for c in profile["columns"])
    src_pos = source.as_posix()
    select  = (
        f"SELECT {casts} "
        f"FROM read_csv_auto('{src_pos}', nullstr='')"
    )

    con = duckdb.connect(str(db_path)) if db_path else duckdb.connect()

    # DuckDB-Tabelle anlegen
    con.execute(f"DROP TABLE IF EXISTS {table}")
    con.execute(f"CREATE TABLE {table} AS {select}")
    row_count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    console.print(f"  [green]✓[/green] {table:30s} {row_count:>7,} Zeilen  →  DuckDB")

    # Parquet schreiben
    if parquet_dir:
        parquet_dir.mkdir(parents=True, exist_ok=True)
        dst = (parquet_dir / f"{table}.parquet").as_posix()
        con.execute(f"COPY (SELECT * FROM {table}) TO '{dst}' (FORMAT PARQUET)")
        console.print(f"  {'':32s}             →  {dst}")

    con.close()


def load_directory(
    profiles_dir: Path,
    db_path: Path | None = None,
    parquet_dir: Path | None = None,
) -> None:
    """Lädt alle YAML-Profile in einem Verzeichnis."""
    yamls = sorted(profiles_dir.glob("*.yaml"))
    if not yamls:
        console.print(f"[red]Keine YAML-Dateien in {profiles_dir}[/red]")
        return

    for yp in yamls:
        load_profile(yp, db_path=db_path, parquet_dir=parquet_dir)
