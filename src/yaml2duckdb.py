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
    """Quoted SQL-Identifier sicher für DuckDB."""
    escaped = str(name).replace('"', '""')
    return f'"{escaped}"'


def _sql_str(value: str) -> str:
    """Escaped SQL-String-Literal."""
    return "'" + str(value).replace("'", "''") + "'"


def _col_cast_expr(col: dict) -> str:
    """Baut einen CAST/STRPTIME-Ausdruck für eine Spalte.
    Bei date_format im Profil wird STRPTIME verwendet."""
    q     = _quote(col["name"])
    dtype = col["duckdb_type"].upper()
    fmt   = col.get("date_format")

    if fmt and dtype in ("DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE"):
        if dtype == "DATE":
            return f"STRPTIME({q}, {_sql_str(fmt)})::DATE AS {q}"
        else:
            return f"STRPTIME({q}, {_sql_str(fmt)}) AS {q}"

    return f"CAST({q} AS {col['duckdb_type']}) AS {q}"


def _sort_profiles_by_fk_dependencies(profiles: list[dict]) -> list[dict]:
    """
    Sortiert Profile anhand semantischer FK-Kandidaten.

    Wichtig:
    Es werden KEINE physischen FK-Constraints erzeugt.
    Die Sortierung dient nur einer nachvollziehbaren Lade-/Debug-Reihenfolge.
    """
    by_table = {p["table"]: p for p in profiles}

    deps = {
        p["table"]: {
            col["fk_candidate"]
            for col in p.get("columns", [])
            if col.get("fk_candidate") in by_table
            and col.get("fk_candidate") != p["table"]
        }
        for p in profiles
    }

    result: list[dict] = []
    temporary: set[str] = set()
    permanent: set[str] = set()

    def visit(table: str) -> None:
        if table in permanent:
            return

        if table in temporary:
            raise ValueError(f"Zyklische FK-Abhängigkeit erkannt bei Tabelle: {table}")

        temporary.add(table)

        for dep in sorted(deps[table]):
            visit(dep)

        temporary.remove(table)
        permanent.add(table)
        result.append(by_table[table])

    for table in sorted(by_table):
        visit(table)

    return result


def _build_create_table(profile: dict) -> str:
    """
    Baut CREATE TABLE ohne Constraints.

    PK/FK bleiben semantisch im YAML.
    DuckDB wird hier bewusst als Analytics-Layer verwendet.
    """
    table = profile["table"]
    parts = []

    for col in profile.get("columns", []):
        name = col["name"]
        dtype = col["duckdb_type"]
        parts.append(f"  {_quote(name)} {dtype}")

    return f"CREATE TABLE {_quote(table)} (\n" + ",\n".join(parts) + "\n);"


def _load_single(
    profile: dict,
    con: duckdb.DuckDBPyConnection,
    parquet_dir: Path | None,
) -> None:
    """Lädt ein einzelnes Profil in die bereits geöffnete Verbindung."""
    table = profile["table"]
    source = Path(profile["source"])

    if not source.exists():
        console.print(f"  [red]CSV nicht gefunden:[/red] {source}")
        return

    columns = profile.get("columns", [])

    if not columns:
        console.print(f"  [yellow]⚠[/yellow] {table}: keine Spalten im Profil gefunden")
        return

    casts = ", ".join(_col_cast_expr(c) for c in columns)
    src   = _sql_str(source.as_posix())

    # Spalten mit date_format müssen als VARCHAR eingelesen werden,
    # damit STRPTIME ein VARCHAR bekommt und nicht ein bereits (falsch) geparstes DATE.
    date_fmt_cols = {c["name"] for c in columns if c.get("date_format")}
    if date_fmt_cols:
        types_kvs = ", ".join(f"'{n}': 'VARCHAR'" for n in date_fmt_cols)
        read_expr = f"read_csv_auto({src}, nullstr='', types={{{types_kvs}}})"
    else:
        read_expr = f"read_csv_auto({src}, nullstr='')"

    select = f"SELECT {casts} FROM {read_expr}"
    ddl = _build_create_table(profile)

    con.execute(ddl)
    con.execute(f"INSERT INTO {_quote(table)} {select}")

    row_count = con.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()[0]
    console.print(f"  [green]✓[/green] {table:30s} {row_count:>7,} Zeilen  →  DuckDB")

    # Sentinel-Werte auf NULL setzen (null_values aus Profil)
    for col in columns:
        for nv in col.get("null_values", []):
            con.execute(
                f"UPDATE {_quote(table)} SET {_quote(col['name'])} = NULL "
                f"WHERE {_quote(col['name'])} = {_sql_str(nv)}"
            )

    if parquet_dir:
        parquet_dir.mkdir(parents=True, exist_ok=True)
        dst = (parquet_dir / f"{table}.parquet").as_posix()

        con.execute(
            f"COPY (SELECT * FROM {_quote(table)}) "
            f"TO {_sql_str(dst)} (FORMAT PARQUET)"
        )

        console.print(f"  {'':32s}             →  {dst}")


def load_profile(
    yaml_path: Path,
    db_path: Path | None = None,
    parquet_dir: Path | None = None,
) -> None:
    """Lädt eine einzelne YAML-Profildatei in DuckDB und/oder Parquet."""
    profile = _load_yaml(yaml_path)

    if not profile or not profile.get("table"):
        console.print(f"[red]Ungültiges Profil:[/red] {yaml_path}")
        return

    con = duckdb.connect(str(db_path)) if db_path else duckdb.connect()

    try:
        con.execute(f"DROP TABLE IF EXISTS {_quote(profile['table'])}")
        _load_single(profile, con, parquet_dir)
    finally:
        con.close()


def load_directory(
    profiles_dir: Path,
    db_path: Path | None = None,
    parquet_dir: Path | None = None,
) -> None:
    """Lädt alle YAML-Profile aus einem Verzeichnis."""
    yamls = sorted(profiles_dir.glob("*.yaml"))

    if not yamls:
        console.print(f"[red]Keine YAML-Dateien in {profiles_dir}[/red]")
        return

    all_profiles: list[dict] = []

    for y in yamls:
        profile = _load_yaml(y)
        if profile and profile.get("table"):
            all_profiles.append(profile)

    all_profiles = _sort_profiles_by_fk_dependencies(all_profiles)

    console.print(
        "[dim]Ladereihenfolge:[/dim] "
        + " → ".join(p["table"] for p in all_profiles)
    )

    con = duckdb.connect(str(db_path)) if db_path else duckdb.connect()

    try:
        # Ohne physische FKs wäre die Reihenfolge beim DROP egal,
        # reversed bleibt aber sauber und zukunftssicher.
        for profile in reversed(all_profiles):
            con.execute(f"DROP TABLE IF EXISTS {_quote(profile['table'])}")

        for profile in all_profiles:
            _load_single(profile, con, parquet_dir)

    finally:
        con.close()