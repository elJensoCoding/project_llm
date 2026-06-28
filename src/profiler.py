"""CSV-Profiler: analysiert CSV-Dateien und leitet DuckDB-Schema + YAML ab."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import yaml
from rich.console import Console
from rich.table import Table

console = Console()

_DATE_KEYWORDS = {"datum", "date", "termin", "zeit", "time", "monat", "jahr"}
_ID_SUFFIXES   = ("_id", "_nr", "_key", "_pk", "nummer")
_ID_EXACT      = {"id", "nr", "nummer"}

_SEMANTIC_STYLE = {
    "identifier": "dim",
    "date":       "yellow",
    "measure":    "green",
    "dimension":  "cyan",
    "attribute":  "",
}


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _semantic_hint(name: str, dtype: str, unique_count: int, row_count: int) -> str:
    lower = name.lower()
    if lower in _ID_EXACT or any(lower.endswith(s) for s in _ID_SUFFIXES):
        return "identifier"
    if (dtype.upper() in ("DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE")
            or any(kw in lower for kw in _DATE_KEYWORDS)):
        return "date"
    if dtype.upper() in ("INTEGER", "BIGINT", "HUGEINT", "SMALLINT") or dtype.upper().startswith("DECIMAL"):
        return "measure"
    if unique_count <= 50:
        return "dimension"
    return "attribute"


def _normalise_type(dtype: str) -> str:
    """Normalisiert DuckDB-Typnamen auf kanonische Schreibweise."""
    dtype = str(dtype).upper().strip()
    # Präzisions-Angaben erhalten (DECIMAL(10,2), VARCHAR(255) etc.)
    base = dtype.split("(")[0].strip()
    mapping = {
        "INT32":        "INTEGER",
        "INT64":        "BIGINT",
        "INT16":        "SMALLINT",
        "INT8":         "TINYINT",
        "FLOAT32":      "DECIMAL",
        "FLOAT64":      "DECIMAL",
        "FLOAT":        "DECIMAL",
        "DOUBLE":       "DECIMAL",
        "TEXT":         "VARCHAR",
        "STRING":       "VARCHAR",
        "BOOL":         "BOOLEAN",
        "TIMESTAMP_S":  "TIMESTAMP",
        "TIMESTAMP_MS": "TIMESTAMP",
        "TIMESTAMP_NS": "TIMESTAMP",
    }
    normalised_base = mapping.get(base, base)
    # Präzision übernehmen wenn vorhanden (außer bei DECIMAL ohne Angabe)
    if "(" in dtype and normalised_base not in ("DECIMAL",):
        suffix = dtype[dtype.index("("):]
        return normalised_base + suffix
    return normalised_base


def _null_pct(row: Any) -> float:
    """Liest null_percentage robust aus — Feldname variiert je nach DuckDB-Version."""
    for key in ("null_percentage", "null%", "null_pct"):
        val = row.get(key)
        if val is not None:
            try:
                return round(float(val), 2)
            except (TypeError, ValueError):
                pass
    return 0.0


def _fk_candidate(col_name: str, other_tables: list[str]) -> str | None:
    """Namens-Heuristik: projekt_nr → projekte, artikel_nr → artikel."""
    lower = col_name.lower()
    if lower in _ID_EXACT:
        return None
    for suffix in _ID_SUFFIXES:
        if lower.endswith(suffix) and lower != suffix:
            stem = lower[: -len(suffix)]
            if len(stem) < 2:  # zu kurz um sinnvoll zu matchen
                continue
            for tname in other_tables:
                t = tname.lower()
                if t == stem or t == stem + "e" or t == stem + "n" or t.startswith(stem):
                    return tname
    return None


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


# ---------------------------------------------------------------------------
# Kern-Profiling
# ---------------------------------------------------------------------------

def profile_csv(
    path: Path,
    table_name: str | None = None,
    all_table_names: list[str] | None = None,
) -> dict:
    """Profiliert eine einzelne CSV-Datei via DuckDB SUMMARIZE."""
    tname = table_name or path.stem
    src   = path.as_posix()
    con   = duckdb.connect()

    row_count: int = con.execute(
        f"SELECT COUNT(*) FROM read_csv_auto('{src}', nullstr='')"
    ).fetchone()[0]

    summary_df = con.execute(
        f"SUMMARIZE SELECT * FROM read_csv_auto('{src}', nullstr='')"
    ).df()

    # Basis-Sample für high-cardinality Spalten
    sample_df = con.execute(
        f"SELECT * FROM read_csv_auto('{src}', nullstr='') LIMIT 10"
    ).df()

    other_tables = [t for t in (all_table_names or []) if t != tname]
    columns: list[dict[str, Any]] = []

    for _, row in summary_df.iterrows():
        col_name: str  = str(row["column_name"])
        dtype          = _normalise_type(str(row["column_type"]))
        null_pct       = _null_pct(row)
        nullable       = null_pct > 0
        unique_count   = int(row.get("approx_unique") or 0)

        # Low-Cardinality (≤50): alle Distinct-Werte — natürliches Value Inventory
        # High-Cardinality: 5 Samples aus Vorschau
        quoted = f'"{col_name}"'
        if unique_count <= 50:
            try:
                all_vals = con.execute(
                    f"SELECT DISTINCT {quoted} "
                    f"FROM read_csv_auto('{src}', nullstr='') "
                    f"WHERE {quoted} IS NOT NULL "
                    f"ORDER BY {quoted}"
                ).df()
                samples = [str(s) for s in all_vals.iloc[:, 0].tolist()]
            except Exception:
                samples = (
                    [str(s) for s in sample_df[col_name].dropna().head(5).tolist()]
                    if col_name in sample_df.columns else []
                )
        else:
            samples = (
                [str(s) for s in sample_df[col_name].dropna().head(5).tolist()]
                if col_name in sample_df.columns else []
            )

        col: dict[str, Any] = {
            "name":         col_name,
            "duckdb_type":  dtype,
            "nullable":     nullable,
            "unique_count": unique_count,
            "null_pct":     null_pct,
            "sample":       samples,
        }

        # Statistiken: min/max für alle Typen, mean nur für Numerics
        min_val = row.get("min")
        if min_val is not None and str(min_val) not in ("None", "nan", ""):
            col["min"] = str(min_val)
            col["max"] = str(row.get("max", ""))

        is_numeric = (
            dtype.upper() in ("INTEGER", "BIGINT", "SMALLINT", "TINYINT", "HUGEINT")
            or dtype.upper().startswith("DECIMAL")
        )
        if is_numeric:
            avg = row.get("avg")
            if avg is not None:
                try:
                    f_avg = float(avg)
                    if f_avg == f_avg:  # NaN-Guard
                        col["mean"] = round(f_avg, 2)
                except (TypeError, ValueError):
                    pass

        col["semantic_hint"] = _semantic_hint(col_name, dtype, unique_count, row_count)

        fk = _fk_candidate(col_name, other_tables)
        if fk:
            col["fk_candidate"] = fk

        columns.append(col)

    con.close()

    return {
        "table":       tname,
        "source":      str(path),
        "profiled_at": datetime.now().date().isoformat(),
        "row_count":   row_count,
        "ddl":         _build_ddl(tname, columns),
        "columns":     columns,
    }


def _build_ddl(table_name: str, columns: list[dict], all_profiles: list[dict] | None = None) -> str:
    """Generiert CREATE TABLE DDL. Mit all_profiles werden FK REFERENCES aufgelöst."""
    parts = []
    for col in columns:
        name     = col["name"]
        dtype    = col["duckdb_type"]
        not_null = "" if col.get("nullable") else " NOT NULL"
        fk_ref   = ""
        if all_profiles and col.get("fk_candidate"):
            pk = _find_pk(all_profiles, col["fk_candidate"])
            if pk:
                fk_ref = f" REFERENCES {col['fk_candidate']}({pk})"
        parts.append(f"  {name} {dtype}{not_null}{fk_ref}")
    return f"CREATE TABLE {table_name} (\n" + ",\n".join(parts) + "\n);"


def profile_directory(csv_dir: Path) -> list[dict]:
    """Profiliert alle CSVs — zweiter Pass ergänzt FK REFERENCES im DDL."""
    csv_files = sorted(csv_dir.glob("*.csv"))
    if not csv_files:
        console.print(f"[red]Keine CSV-Dateien in {csv_dir}[/red]")
        return []

    table_names = [f.stem for f in csv_files]
    profiles = []
    for path in csv_files:
        console.print(f"  Analysiere [cyan]{path.name}[/cyan] ...")
        profiles.append(profile_csv(path, table_name=path.stem, all_table_names=table_names))

    # Zweiter Pass: DDL mit FK REFERENCES nachschärfen
    for p in profiles:
        p["ddl"] = _build_ddl(p["table"], p["columns"], all_profiles=profiles)

    return profiles


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------

def print_profile(profile: dict) -> None:
    t = Table(
        title=f"[bold]{profile['table']}[/bold]  ({profile['row_count']:,} Zeilen)",
        show_lines=True,
        header_style="bold cyan",
    )
    t.add_column("Spalte",   style="cyan", no_wrap=True)
    t.add_column("Typ",      no_wrap=True)
    t.add_column("Null %",   justify="right")
    t.add_column("Unique",   justify="right")
    t.add_column("Min / Max")
    t.add_column("Sample",   overflow="fold", max_width=40)
    t.add_column("Semantic", no_wrap=True)
    t.add_column("FK →",     style="yellow", no_wrap=True)

    for col in profile["columns"]:
        sem   = col.get("semantic_hint", "")
        style = _SEMANTIC_STYLE.get(sem, "")
        min_max = f"{col['min']} / {col['max']}" if "min" in col else ""
        t.add_row(
            col["name"],
            col["duckdb_type"],
            f"{col['null_pct']}%",
            str(col["unique_count"]),
            min_max,
            ", ".join(col.get("sample", [])),
            f"[{style}]{sem}[/{style}]" if style else sem,
            col.get("fk_candidate", ""),
        )

    console.print(t)


def save_yaml(profile: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{profile['table']}.yaml"
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(profile, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return out_path


# ---------------------------------------------------------------------------
# Prompt-Integration
# ---------------------------------------------------------------------------

def _slim_column(col: dict) -> dict:
    """Reduziert eine Spalte auf LLM-relevante Felder."""
    slim: dict = {"name": col["name"], "type": col["duckdb_type"]}
    if col.get("nullable"):
        slim["nullable"] = True
    if col.get("semantic_hint"):
        slim["semantic"] = col["semantic_hint"]
    if col.get("fk_candidate"):
        slim["fk"] = col["fk_candidate"]
    # Samples als Value Inventory — aber NICHT für FK-Identifier (nur numerische IDs, kein Mehrwert)
    samples = col.get("sample", [])
    is_fk_id = col.get("fk_candidate") and col.get("semantic_hint") == "identifier"
    if samples and not is_fk_id and col.get("semantic_hint") in ("dimension", "attribute"):
        slim["sample"] = samples
    return slim


def profiles_to_prompt_section(profiles: list[dict]) -> str:
    """Rendert Profile als schlankes YAML für den System-Prompt."""
    parts = []
    for p in profiles:
        slim = {
            "table":   p["table"],
            "rows":    p["row_count"],
            "ddl":     p["ddl"],
            "columns": [_slim_column(c) for c in p["columns"]],
        }
        parts.append(yaml.dump(slim, allow_unicode=True, default_flow_style=False, sort_keys=False))
    return "\n---\n".join(parts)


def extract_value_inventories(profiles: list[dict]) -> dict[str, list[str]]:
    """Extrahiert Kontakt- und Lieferantennamen aus den Profil-Samples."""
    result: dict[str, list[str]] = {}
    for p in profiles:
        for col in p["columns"]:
            if p["table"] == "kontakte" and col["name"] == "name":
                result["kontakte"] = col.get("sample", [])
            if p["table"] == "einkaufspositionen" and col["name"] == "lieferant_name":
                result["lieferanten"] = col.get("sample", [])
    return result


def load_profiles_from_dir(profiles_dir: Path) -> list[dict]:
    """Lädt alle YAML-Profile aus einem Verzeichnis."""
    profiles = []
    for yp in sorted(profiles_dir.glob("*.yaml")):
        with open(yp, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data and "table" in data:  # nur echte Profil-YAMLs laden
                profiles.append(data)
    return profiles
