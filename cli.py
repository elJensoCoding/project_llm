"""Typer-CLI für die Projekt-LLM-Datenbank."""
import os
import subprocess
import sys
from pathlib import Path

# Windows: UTF-8 konsistent für alle print()-Ausgaben erzwingen
if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="pllm",
    help="Projekt-Datenbank mit lokalem LLM-Chat",
    add_completion=False,
)
console = Console()


@app.callback()
def main(
    config: Path = typer.Option(
        None, "--config", "-c",
        help="Konfigurationsdatei (Standard: pllm_config.yaml im aktuellen Verzeichnis)",
    ),
):
    """Lädt die Konfiguration vor allen Befehlen."""
    from src.config import load
    cfg = load(config)
    if config and config.exists():
        console.print(f"[dim]Konfiguration geladen: {config}[/dim]")


@app.command()
def generate():
    """Generiere Testdaten als CSV-Dateien."""
    from src.generator import generate_all
    generate_all()


@app.command()
def convert():
    """Konvertiere CSV-Dateien nach Parquet."""
    from src.converter import convert_all
    convert_all()


@app.command()
def init():
    """Generiere und konvertiere alle Daten in einem Schritt."""
    from src.generator import generate_all
    from src.converter import convert_all
    generate_all()
    convert_all()


@app.command()
def chat(
    model: str = typer.Option("qwen2.5-coder:7b", "--model", "-m", help="Ollama-Modell (qwen2.5-coder:7b, qwen3:4b, gemma3)"),
    port: int = typer.Option(8080, "--port", "-p", help="NiceGUI-Port"),
):
    """Starte das NiceGUI-Chat-Frontend."""
    import os as _os
    _os.environ["PLLM_MODEL"] = model
    console.print(f"[bold green]Starte Chat-Frontend[/bold green] → http://127.0.0.1:{port}")
    console.print(f"Modell: [cyan]{model}[/cyan]  |  Ctrl+C zum Beenden\n")
    from src.app import run
    run(port=port, model=model)


@app.command()
def query(
    sql: str = typer.Argument(..., help="SQL-Statement direkt ausführen"),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximale Anzahl Zeilen"),
):
    """Führe eine SQL-Abfrage direkt in DuckDB aus (ohne LLM)."""
    from src.db import execute

    df, error = execute(sql)
    if error:
        console.print(f"[red]Fehler:[/red] {error}")
        raise typer.Exit(1)

    if df is None or df.empty:
        console.print("[yellow]Keine Zeilen zurückgegeben.[/yellow]")
        return

    df = df.head(limit)
    table = Table(show_header=True, header_style="bold cyan")
    for col in df.columns:
        table.add_column(str(col), overflow="fold")
    for _, row in df.iterrows():
        table.add_row(*[str(v) if v is not None else "" for v in row])
    console.print(table)
    console.print(f"[dim]{len(df)} Zeile(n) angezeigt[/dim]")


@app.command()
def profile(
    path: Path = typer.Argument(None, help="CSV-Datei oder Verzeichnis (Default: csv_dir aus Config)"),
    out_dir: Path = typer.Option(None, "--out", "-o", help="Ausgabeverzeichnis für YAML (Default: profiles_dir aus Config)"),
):
    """Analysiere CSV-Dateien und leite DuckDB-Schema + YAML-Meta-Layer ab."""
    from src.profiler import profile_csv, profile_directory, print_profile, save_yaml
    from src import config as cfg

    path    = path    or cfg.csv_dir()
    out_dir = out_dir or cfg.profiles_dir()

    if path.is_dir():
        console.print(f"[bold green]Profiling Verzeichnis:[/bold green] {path}\n")
        profiles = profile_directory(path)
    elif path.suffix.lower() == ".csv":
        console.print(f"[bold green]Profiling:[/bold green] {path.name}\n")
        profiles = [profile_csv(path)]
    else:
        console.print("[red]Pfad muss eine .csv-Datei oder ein Verzeichnis sein.[/red]")
        raise typer.Exit(1)

    for p in profiles:
        print_profile(p)
        out = save_yaml(p, out_dir)
        console.print(f"  [dim]→ {out}[/dim]\n")

    console.print(f"[bold green]{len(profiles)} Tabelle(n) profiliert → {out_dir}[/bold green]")


@app.command()
def yaml2duckdb(
    path: Path = typer.Argument(..., help="YAML-Profildatei oder Verzeichnis mit YAML-Dateien"),
    db: Path = typer.Option(None, "--db", help="Persistente DuckDB-Datei (z.B. data/warehouse.duckdb)"),
    parquet: Path = typer.Option(None, "--parquet", "-p", help="Parquet-Ausgabeverzeichnis (z.B. data/parquet)"),
):
    """Lade YAML-Profile typisiert in DuckDB und/oder als Parquet."""
    from src.yaml2duckdb import load_profile, load_directory
    from src import config as cfg

    if not db and not parquet:
        parquet = cfg.parquet_dir()
        console.print(f"[dim]Kein --db/--parquet angegeben — schreibe nach {parquet}[/dim]\n")

    if path.is_dir():
        console.print(f"[bold green]yaml2duckdb:[/bold green] {path}\n")
        load_directory(path, db_path=db, parquet_dir=parquet)
    elif path.suffix.lower() == ".yaml":
        console.print(f"[bold green]yaml2duckdb:[/bold green] {path.name}\n")
        load_profile(path, db_path=db, parquet_dir=parquet)
    else:
        console.print("[red]Pfad muss eine .yaml-Datei oder ein Verzeichnis sein.[/red]")
        raise typer.Exit(1)

    console.print("\n[bold green]Fertig.[/bold green]")


@app.command()
def log(
    flagged: bool = typer.Option(False, "--flagged", "-f", help="Nur als fehlerhaft markierte Einträge zeigen"),
):
    """Zeigt den Query-Log. Mit --flagged nur fehlerhafte Einträge."""
    from src.query_log import read_all
    entries = read_all(only_flagged=flagged)
    if not entries:
        console.print("[yellow]Keine Einträge im Log.[/yellow]")
        return

    table = Table(
        "Zeit", "Frage", "Fehler", "Zeilen", "Retry", "Flag",
        header_style="bold cyan", show_lines=True
    )
    for e in entries:
        flag_mark = "[red]✗[/red]" if e.get("flagged") else ""
        err_short = (e["error"] or "")[:50]
        table.add_row(
            e["ts"],
            e["question"][:60],
            err_short,
            str(e["rows"]),
            "✓" if e["retried"] else "",
            flag_mark,
        )
    console.print(table)
    console.print(f"\n[dim]{len(entries)} Eintrag/Einträge{' (geflaggt)' if flagged else ''}[/dim]")

    # Geflaggte Queries als Rohdaten ausgeben — direkt zum Einbauen als Beispiele
    if not flagged:
        flagged_entries = [e for e in entries if e.get("flagged")]
        if flagged_entries:
            console.print(f"\n[bold yellow]{len(flagged_entries)} als fehlerhaft markiert:[/bold yellow]")
            for e in flagged_entries:
                console.print(f"\n[cyan]Frage:[/cyan] {e['question']}")
                console.print(f"[red]SQL:[/red] {e['sql']}")
                if e["error"]:
                    console.print(f"[red]Fehler:[/red] {e['error']}")


@app.command()
def prompt():
    """Gibt den aktuellen System-Prompt inkl. Schema und Value Inventories aus."""
    from src.profiler import load_profiles_from_dir
    from src import config as cfg
    from src.schema import get_system_prompt
    from src.db import execute

    profiles = []
    pd = cfg.profiles_dir()
    if pd.exists():
        profiles = load_profiles_from_dir(pd)

    # Value Inventories aus DB laden
    value_inventories = []
    for inv in cfg.value_inventories():
        df, err = execute(inv["sql"])
        if not err and df is not None and not df.empty:
            rows = df.apply(lambda r: "  ".join(str(v) for v in r if v), axis=1).tolist()
            value_inventories.append({"label": inv["label"], "values": rows, "hint": inv.get("hint", "")})

    prompt_text = get_system_prompt(profiles=profiles, value_inventories=value_inventories)
    console.print(prompt_text)


@app.command()
def models():
    """Listet verfügbare Ollama-Modelle auf."""
    import ollama
    try:
        result = ollama.list()
        table = Table("Modell", "Größe", "Geändert", header_style="bold cyan")
        for m in result.models:
            size_gb = f"{m.size / 1e9:.1f} GB" if m.size else "?"
            table.add_row(m.model, size_gb, str(m.modified_at)[:10] if m.modified_at else "?")
        console.print(table)
    except Exception as e:
        console.print(f"[red]Ollama nicht erreichbar:[/red] {e}")
        console.print("Starte Ollama mit: [cyan]ollama serve[/cyan]")


if __name__ == "__main__":
    app()
