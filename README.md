# Projekt-LLM

Proof of Concept: Natürlichsprachliche Abfragen auf einer lokalen Datenbank — ohne NL-Parser, stattdessen generiert ein lokales LLM das SQL on-the-fly. Vollständig konfigurierbar für beliebige Domänen.

---

## Idee

Ein lokales LLM (via [Ollama](https://ollama.com)) erhält Schema, Businessregeln und Beispiel-Queries aus einer YAML-Konfiguration. Es generiert DuckDB-SQL, das direkt auf Parquet-Dateien oder einer persistenten DuckDB ausgeführt wird. Das Ergebnis erscheint als interaktive Tabelle und Chart im Chat.

Follow-up-Fragen funktionieren, weil der vollständige Gesprächsverlauf inklusive der zurückgegebenen Daten als Kontext erhalten bleibt:

> *"Adresse zum Projekt von Einkäufer xxx yyy"* → *"Zeig das Projekt"* → *"Alle Bestellungen dazu"*

---

## Features

- Natürlichsprachliche Abfragen ohne eigenen Parser
- Lokales LLM über Ollama (kein Cloud-API-Key nötig)
- Follow-up-Fragen durch Session-Kontext inkl. Ergebnisrückführung
- Automatischer SQL-Retry bei Syntaxfehlern (1 Korrekturpass, transparent im UI)
- Automatische Chart-Erkennung: Zeitreihe → Linie/Fläche, ≤7 Kategorien → Donut, sonst Balken
- Interaktive Ergebnistabelle (sortierbar, filterbar, Pagination ab 20 Zeilen)
- Freitext-Zusammenfassung der Ergebnisse (zweiter LLM-Pass, zustandslos)
- Multi-User: jeder Browser-Tab bekommt eine eigene Konversationshistorie
- **CSV-Profiler**: analysiert CSV-Pakete, leitet DuckDB-Schema ab, schreibt YAML-Meta-Layer
- **yaml2duckdb**: lädt YAML-Profile typisiert inkl. FK REFERENCES in DuckDB und/oder Parquet
- **Vollständig konfigurierbar** via `pllm_config.yaml` — für beliebige Domänen ohne Code-Änderungen

---

## Tech Stack

| Komponente | Technologie |
|---|---|
| Storage | CSV → Parquet oder persistente DuckDB |
| Query Engine | [DuckDB](https://duckdb.org) |
| LLM | [Ollama](https://ollama.com) (lokal) |
| Frontend | [NiceGUI](https://nicegui.io) |
| Charts | ECharts (via `ui.echart`) |
| CLI | [Typer](https://typer.tiangolo.com) + [Rich](https://rich.readthedocs.io) |
| Datengenerator | [Faker](https://faker.readthedocs.io) (`de_DE`) |

---

## Voraussetzungen

- Python 3.11+
- [Ollama](https://ollama.com) installiert und gestartet (`ollama serve`)
- Empfohlenes Modell:

```bash
ollama pull qwen2.5-coder:7b   # beste SQL-Qualität im Test
# Alternativen
ollama pull gemma3
ollama pull qwen3:4b
```

---

## Setup

```powershell
# Windows Quickstart
cd C:\dev\repos\project_llm
.\setup.ps1
```

```bash
# Manuell (alle Plattformen)
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
```

---

## Konfiguration (`pllm_config.yaml`)

Alle Pfade, Modell-Auswahl und der komplette LLM-Prompt werden über `pllm_config.yaml` im Projektverzeichnis gesteuert:

```yaml
version: 1

database:
  path: null              # null = in-memory + Parquet | Pfad = persistente DuckDB
  csv_dir: data/csv
  parquet_dir: data/parquet
  profiles_dir: data/profiles

llm:
  model: qwen2.5-coder:7b

app:
  port: 8080
  host: 127.0.0.1

prompt:
  system_role: >
    Du bist ein SQL-Experte für DuckDB. Du generierst SQL-Abfragen
    basierend auf Nutzerfragen in natürlicher Sprache.

  extra_rules:
    - "Beträge immer in Euro mit 2 Dezimalstellen ausgeben"

  examples:
    - q: "Alle Projekte anzeigen"
      sql: "SELECT projektnummer, schlagwort FROM projekte ORDER BY projektnummer"

    # Follow-up-Beispiel mit Kontext
    - q: "Wer ist Projekteinkäufer für Projekt in Hamburg?"
      sql: "SELECT p.projektnummer, k.name FROM projekte p JOIN kontakte k ..."
      context: "[SYSTEM-ERGEBNIS: projektnummer=10017, name=Max Müller]"
      followup_q: "Zeig das Projekt."
      followup_sql: "SELECT * FROM projekte WHERE projektnummer = 10017"
```

**Priorität:** `pllm_config.yaml` → Umgebungsvariablen (`PLLM_DB`, `PLLM_MODEL`) → CLI-Flags

Eine alternative Config kann mit `--config` angegeben werden:

```bash
python cli.py --config mein_projekt.yaml chat
```

---

## CLI-Referenz

```
python cli.py [--config DATEI] BEFEHL [OPTIONEN]
```

| Befehl | Beschreibung |
|---|---|
| `generate` | Testdaten als CSV erzeugen (Faker, de_DE) |
| `convert` | CSV → Parquet (einfach, ohne Typisierung) |
| `init` | `generate` + `convert` in einem Schritt |
| `profile [PFAD]` | CSV-Dateien analysieren → YAML-Profile |
| `yaml2duckdb [PFAD]` | YAML-Profile → DuckDB / Parquet |
| `chat` | NiceGUI-Frontend starten |
| `query "SQL"` | SQL direkt ausführen (ohne LLM) |
| `models` | Verfügbare Ollama-Modelle anzeigen |

### Optionen

```bash
python cli.py chat --model gemma3 --port 8081
python cli.py profile                              # Default: csv_dir aus Config
python cli.py profile data/csv/projekte.csv        # einzelne Datei
python cli.py profile --out data/profiles/
python cli.py yaml2duckdb                          # Default: profiles_dir → parquet_dir
python cli.py yaml2duckdb --db data/warehouse.duckdb
python cli.py yaml2duckdb --db data/warehouse.duckdb --parquet data/parquet/
python cli.py query "SELECT COUNT(*) FROM projekte"
```

---

## Workflows

### Demo-Daten (Schnellstart)

```bash
python cli.py init    # Testdaten generieren + nach Parquet konvertieren
python cli.py chat    # Frontend starten → http://127.0.0.1:8080
```

### Empfohlener Workflow mit eigenen Daten

```bash
# 1. CSV-Daten ablegen
cp meine_daten/*.csv data/csv/

# 2. Profilen — Schema ableiten, YAML schreiben
python cli.py profile

# 3. data/profiles/*.yaml prüfen, Typen ggf. anpassen

# 4. Typisiert in Parquet laden (DuckDB inferiert sonst Typen)
python cli.py yaml2duckdb

# 5. pllm_config.yaml anpassen:
#    - system_role: Domänenbeschreibung
#    - examples: domänenspezifische Beispiel-Queries

# 6. Chat starten
python cli.py chat
```

### Workflow mit persistenter DuckDB

```bash
python cli.py profile
python cli.py yaml2duckdb --db data/warehouse.duckdb

# In pllm_config.yaml:
#   database:
#     path: data/warehouse.duckdb

python cli.py chat
```

### Mehrere Domänen parallel

```bash
python cli.py --config projekte.yaml chat    # Port 8080
python cli.py --config logistik.yaml chat    # Port 8081
```

---

## Projektstruktur

```
project_llm/
├── cli.py                  # Typer-Einstiegspunkt
├── pllm_config.yaml        # Hauptkonfiguration (Pfade, Modell, Prompt, Beispiele)
├── pyproject.toml
├── setup.ps1               # Windows-Quickstart
├── src/
│   ├── config.py           # Konfigurationsloader (YAML + Env-Vars)
│   ├── generator.py        # Faker-Datengenerator → CSV
│   ├── converter.py        # CSV → Parquet (einfach, ohne YAML)
│   ├── profiler.py         # CSV-Profiler: Statistiken, Schema, FK-Erkennung → YAML
│   ├── yaml2duckdb.py      # YAML-Profile → typisierte DuckDB-Tabellen + Parquet
│   ├── schema.py           # System-Prompt: DuckDB-Regeln + Fallback-Schema/-Beispiele
│   ├── db.py               # DuckDB-Verbindung (in-memory oder persistent), thread-sicher
│   ├── llm.py              # Ollama ChatSession: ask() + feed_result() + interpret()
│   └── app.py              # NiceGUI Chat-Frontend, Chart-Erkennung, Multi-User
└── data/
    ├── csv/                # CSV-Quelldaten            (nicht eingecheckt)
    ├── profiles/           # YAML-Meta-Layer           (nicht eingecheckt)
    └── parquet/            # Typisierte Parquet-Dateien (nicht eingecheckt)
```

---

## CSV-Profiler

`pllm profile` analysiert CSV-Dateien mit DuckDB `SUMMARIZE` und schreibt pro Tabelle eine YAML-Datei:

- **Schema**: DuckDB-Typen inkl. `CREATE TABLE` DDL mit `NOT NULL` und `REFERENCES`
- **Statistiken**: Kardinalität, Null-%, Min/Max je Spalte
- **Value Inventory**: alle Distinct-Werte für Low-Cardinality-Spalten (≤50 unique) — dienen direkt als Kontext im LLM-Prompt
- **Semantic Hints**: `identifier` / `date` / `measure` / `dimension` / `attribute` per Heuristik
- **FK-Kandidaten**: Namensanalyse (`projekt_nr` → `projekte`, `artikel_nr` → `artikel`)

`DOUBLE` wird immer als `DECIMAL` ausgegeben — in kaufmännischen Daten sind Fließkommazahlen fast immer Geldbeträge.

Die Profile werden beim App-Start automatisch in den LLM-System-Prompt injiziert und ersetzen dabei das manuell gepflegte Fallback-Schema sowie die separaten Value-Inventory-Abfragen.

---

## LLM-Ansatz

### Prompt-Schichten

Der System-Prompt besteht aus mehreren Schichten, alle konfigurierbar:

```
system_role          ← pllm_config.yaml: prompt.system_role
DuckDB-Regelwerk     ← schema.py (generisch, domänenunabhängig)
Schema               ← data/profiles/*.yaml  ODER  schema.py Fallback
Value Inventories    ← aus Profil-Samples (Kontakte, Lieferanten etc.)
extra_rules          ← pllm_config.yaml: prompt.extra_rules
examples             ← pllm_config.yaml: prompt.examples  ODER  schema.py Fallback
```

### Zwei-Pass-Strategie

1. **SQL-Generierung** (`ask()`) — zustandsbehaftet, mit vollständigem Gesprächsverlauf
2. **Freitext-Zusammenfassung** (`interpret()`) — zustandslos, 2–3 Sätze mit konkreten Zahlen

### Automatischer SQL-Retry

```
→ LLM:    SELECT … WHERE col IS NOT IN (…)
→ DuckDB: Parser Error: syntax error at or near "NOT"
→ Retry:  LLM korrigiert → SELECT … WHERE col NOT IN (…)  ✓
→ UI:     SQL-Klappe zeigt "SQL (korrigiert)"
```

### Follow-up-Kontext

`feed_result()` hängt nach jeder Abfrage die Ergebniszeilen als `[SYSTEM-ERGEBNIS]`-Block an die letzte Assistenten-Nachricht. Folgefragen können so konkrete Werte (z.B. Projektnummern) aus dem vorherigen Ergebnis referenzieren.

### Multi-User

```
Tab A ──┐                          ┌── globaler asyncio.Lock ──▶ Ollama
        ├── je eigene ChatSession ─┤
Tab B ──┘                          └── globaler threading.Lock ──▶ DuckDB
```

---

## Chart-Erkennung

| Ergebnisstruktur | Chart |
|---|---|
| Datum/Zeit-Spalte + Messwert | Linie mit Fläche |
| ≤ 7 Kategorien + 1 Messwert | Donut |
| Kategorien + Messwerte | Balken |
| Nur IDs oder kein Messwert | kein Chart |

ID-artige Spalten (`*_id`, `*_nr`, `*nummer`) werden nie als Messwert interpretiert, sondern als kategorische X-Achse.

---

## Neue Domäne einrichten

```bash
# 1. Config kopieren und anpassen
cp pllm_config.yaml meine_domäne.yaml
# → system_role, examples anpassen

# 2. Daten ablegen und profilen
cp /pfad/zu/daten/*.csv data/csv/
python cli.py --config meine_domäne.yaml profile

# 3. In DuckDB laden
python cli.py --config meine_domäne.yaml yaml2duckdb

# 4. Starten
python cli.py --config meine_domäne.yaml chat
```

Kein Code anfassen.

---

## Bekannte Einschränkungen

- SQL-Qualität hängt vom Modell ab; `qwen2.5-coder:7b` ist bei komplexen Subqueries überlegen
- Max. 1 automatischer Retry — mehrfach verschachtelte Fehler müssen manuell als Follow-up korrigiert werden
- Konversationshistorie liegt im RAM, kein Persistence über Server-Neustarts
- FK-Erkennung im Profiler ist namensbasiert; semantisch unbenannte FKs werden nicht erkannt
- DuckDB enforced keine FK-Constraints — `REFERENCES` dient nur als Dokumentation für den LLM

---

## Lizenz

MIT
