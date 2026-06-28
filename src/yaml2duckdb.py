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


def _quote(name: str) -> str:
    """Quoted einen Spaltennamen wenn nötig (Umlaute, Leerzeichen, Sonderzeichen)."""
    needs_quoting = any(c in name for c in "äöüÄÖÜß -./") or name[0].isdigit()
    return f'"{name}"' if needs_quoting else name


def _col_cast_expr(col: dict) -> str:
    """Baut einen CAST-Ausdruck für eine Spalte — stellt korrekte Typen sicher."""
    q = _quote(col["name"])
    return f"CAST({q} AS {col['duckdb_type']}) AS {q}"


def _find_pk(profiles: list[dict], table_name: str) -> str | None:
    """Findet den wahrscheinlichsten PK einer Tabelle (höchste Unique-Rate unter Identifiers)."""
    for p in profiles:
        if p["table"] == table_name:
            row_count = max(p.get("row_count", 1), 1)
            best_col, best_ratio = None, 0.0
            for col in p["columns"]:
                if col.get("semantic_hint") == "identifier":
                    ratio = col.get("unique_count", 0) / row_count
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_col = col["name"]
            return best_col
    return None


def _build_create_with_fks(profile: dict, all_profiles: list[dict]) -> str:
    """Baut CREATE TABLE DDL inkl. FK REFERENCES (von DuckDB geparst, nicht enforced)."""
    table = profile["table"]
    parts = []
    for col in profile["columns"]:
        name     = col["name"]
        dtype    = col["duckdb_type"]
        not_null = "" if col.get("nullable") else " NOT NULL"
        fk_ref   = ""
        if col.get("fk_candidate"):
            pk = _find_pk(all_profiles, col["fk_candidate"])
            if pk:
                fk_ref = f" REFERENCES {col['fk_candidate']}({pk})"
        parts.append(f"  {name} {dtype}{not_null}{fk_ref}")
    return f"CREATE TABLE {table} (\n" + ",\n".join(parts) + "\n);"


def _load_single(
    profile: dict,
    all_profiles: list[dict],
    con: duckdb.DuckDBPyConnection,
    parquet_dir: Path | None,
) -> None:
    """Lädt ein einzelnes Profil in die bereits geöffnete Verbindung."""
    table  = profile["table"]
    source = Path(profile["source"])

    if not source.exists():
        console.print(f"  [red]CSV nicht gefunden:[/red] {source}")
        return

    casts  = ", ".join(_col_cast_expr(c) for c in profile["columns"])
    select = f"SELECT {casts} FROM read_csv_auto('{source.as_posix()}', nullstr='')"
    ddl    = _build_create_with_fks(profile, all_profiles)

    con.execute(f"DROP TABLE IF EXISTS {table}")
    con.execute(ddl)
    con.execute(f"INSERT INTO {table} {select}")

    row_count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    console.print(f"  [green]✓[/green] {table:30s} {row_count:>7,} Zeilen  →  DuckDB")

    if parquet_dir:
        parquet_dir.mkdir(parents=True, exist_ok=True)
        dst = (parquet_dir / f"{table}.parquet").as_posix()
        con.execute(f"COPY (SELECT * FROM {table}) TO '{dst}' (FORMAT PARQUET)")
        console.print(f"  {'':32s}             →  {dst}")


def load_profile(
    yaml_path: Path,
    db_path: Path | None = None,
    parquet_dir: Path | None = None,
    all_profiles: list[dict] | None = None,
) -> None:
    """Lädt eine einzelne YAML-Profildatei in DuckDB und/oder Parquet."""
    profile      = _load_yaml(yaml_path)
    all_profiles = all_profiles or [profile]
    con          = duckdb.connect(str(db_path)) if db_path else duckdb.connect()
    _load_single(profile, all_profiles, con, parquet_dir)
    con.close()


def load_directory(
    profiles_dir: Path,
    db_path: Path | None = None,
    parquet_dir: Path | None = None,
) -> None:
    """Lädt alle YAML-Profile — FK REFERENCES werden tabellenübergreifend aufgelöst."""
    yamls = [y for y in sorted(profiles_dir.glob("*.yaml"))]
    if not yamls:
        console.print(f"[red]Keine YAML-Dateien in {profiles_dir}[/red]")
        return

    # Alle Profile einlesen damit FK-Auflösung tabellenübergreifend funktioniert
    all_profiles = [_load_yaml(y) for y in yamls if _load_yaml(y).get("table")]

    con = duckdb.connect(str(db_path)) if db_path else duckdb.connect()
    for profile in all_profiles:
        _load_single(profile, all_profiles, con, parquet_dir)
    con.close()
