# Projekt-LLM

Proof of Concept: Natürlichsprachliche Abfragen auf einer lokalen Datenbank — ohne NL-Parser, stattdessen generiert ein lokales LLM das SQL on-the-fly. Vollständig konfigurierbar für beliebige Domänen.

---

## Idee

Ein lokales LLM (via [Ollama](https://ollama.com)) erhält Schema, Businessregeln und Beispiel-Queries aus einer YAML-Konfiguration. Es generiert DuckDB-SQL, das direkt auf Parquet-Dateien oder einer persistenten DuckDB ausgeführt wird. Das Ergebnis erscheint als interaktive Tabelle und Chart im Chat.

Follow-up-Fragen funktionieren, weil der vollständige Gesprächsverlauf inklusive der zurückgegebenen Daten als Kontext erhalten bleibt:

> *"Wer ist Projekteinkäufer von Projekt 35403?"* → *"Zeig den Standort"* → *"Alle Bestellungen dazu"*

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
- **yaml2duckdb**: lädt YAML-Profile typisiert (inkl. FK REFERENCES, Datumsformat-Parsing, Sentinel-Bereinigung) in DuckDB und/oder Parquet
- **Dynamische Value Inventories**: Stammdaten (Mitarbeiter, Projekte, Kategorien) werden live aus der DB geladen, nicht aus statischen Snapshots
- **Query-Logger**: jede Abfrage wird protokolliert, per 👎-Button als fehlerhaft markierbar — direkte Vorlage für neue Prompt-Beispiele
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
  path: data/db.duckdb    # persistente DuckDB; null = in-memory + Parquet-Views aus parquet_dir
  csv_dir: data/csv
  parquet_dir: data/parquet
  profiles_dir: data/schema

llm:
  model: qwen2.5-coder:7b

app:
  port: 8080
  host: 127.0.0.1

prompt:
  system_role: >
    Du bist ein SQL-Experte für DuckDB und Assistent im Projekteinkauf.
    Du generierst SQL-Abfragen auf einer Einkaufsdatenbank mit Projekten,
    Mitarbeitern, Lieferanten, Artikeln und Einkaufsvorgängen. Antworte auf Deutsch.

  extra_rules:
    - "mitarbeiter hat getrennte Spalten: 'prename' (Vorname) und 'name' (Nachname).
      Für Volltextsuche: CONCAT(prename, ' ', name) ILIKE '%Vorname Nachname%'"
    - "liefertermin ist VARCHAR im Format DD.MM.YY (zweistelliges Jahr!).
      Casten: STRPTIME(liefertermin, '%d.%m.%y')::DATE"

  examples:
    - q: "Welcher Projektleiter betreut die meisten Projekte?"
      sql: >
        SELECT CONCAT(m.prename, ' ', m.name) AS projektleiter, COUNT(*) AS anzahl
        FROM project p JOIN mitarbeiter m ON p.projektleiter_mitarbeiter_id = m.id
        GROUP BY m.id, m.prename, m.name ORDER BY anzahl DESC

    # Follow-up-Beispiel mit Kontext
    - q: "Wer ist Projekteinkäufer von Projekt 35403?"
      sql: "SELECT CONCAT(m.prename,' ',m.name) AS einkaeufer FROM project p JOIN mitarbeiter m ON p.projekteinkaeufer_mitarbeiter_id = m.id WHERE p.nummer = '35403'"
      context: "[SYSTEM-ERGEBNIS: einkaeufer=Linus Schulte]"
      followup_q: "Zeig seine Kontaktdaten."
      followup_sql: "SELECT prename, name, email, telefon FROM mitarbeiter WHERE CONCAT(prename,' ',name) ILIKE '%Linus Schulte%'"

# Stammdaten, die bei jedem App-Start live aus der DB geladen und in den Prompt
# injiziert werden — kein statischer Snapshot, da sich die Werte über die Zeit ändern.
value_inventories:
  - label: Mitarbeiter
    sql: "SELECT CONCAT(prename, ' ', name) AS vollname FROM mitarbeiter ORDER BY name"
    hint: "Für Personensuchen: CONCAT(prename, ' ', name) ILIKE '%Vorname Nachname%'"
  - label: Projekte
    sql: "SELECT nummer, such, ort FROM project ORDER BY CAST(nummer AS INTEGER)"
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
| `prompt` | Vollständigen System-Prompt ausgeben (Debugging) |
| `log [--flagged]` | Query-Log anzeigen, optional nur fehlerhaft markierte |
| `models` | Verfügbare Ollama-Modelle anzeigen |

### Optionen

```bash
python cli.py chat --model gemma3 --port 8081
python cli.py profile                              # Default: csv_dir aus Config
python cli.py profile data/csv/projekte.csv        # einzelne Datei
python cli.py profile --out data/schema/
python cli.py yaml2duckdb                          # Default: profiles_dir → parquet_dir
python cli.py yaml2duckdb --db data/db.duckdb
python cli.py yaml2duckdb --db data/db.duckdb --parquet data/parquet/
python cli.py query "SELECT COUNT(*) FROM project"
python cli.py prompt                               # Zeigt den kompletten System-Prompt
python cli.py log                                   # Alle protokollierten Queries
python cli.py log --flagged                         # Nur als fehlerhaft markierte
```

---

## Workflows

### Demo-Daten (Schnellstart)

```bash
python cli.py init    # Testdaten generieren + nach Parquet konvertieren
python cli.py chat    # Frontend starten → http://127.0.0.1:8080
```

### Workflow mit eigenen Daten (ERP-Export o.ä.)

```bash
# 1. CSV-Daten ablegen
cp meine_daten/*.csv data/csv/

# 2. Profilen — Schema ableiten, YAML schreiben
python cli.py profile

# 3. data/schema/*.yaml prüfen und nachschärfen:
#    - semantic_hint korrigieren wo die Heuristik daneben liegt
#      (z.B. Spalten die auf _id enden aber Kategorien sind, keine FKs)
#    - date_format ergänzen wenn Datumsspalten nicht ISO-Format sind
#    - null_values ergänzen für Sentinel-Werte (z.B. "++.++.++", "(0,0,0)")
#    - duckdb_type korrigieren wo nötig (DOUBLE→DECIMAL ist bereits automatisch)

# 4. Typisiert laden (Parquet und/oder persistente DuckDB)
python cli.py yaml2duckdb --db data/db.duckdb

# 5. pllm_config.yaml anpassen:
#    - database.path auf die DuckDB-Datei setzen
#    - system_role: Domänenbeschreibung
#    - extra_rules: Eigenheiten des Datenmodells (Datumsformate, getrennte Namen, etc.)
#    - value_inventories: SQL-Queries für Stammdaten (Personen, Kategorien, ...)
#    - examples: anfangs leer lassen

# 6. Chat starten, testen, Fails sammeln
python cli.py chat
# → bei jedem Fail: 👎-Button klicken

# 7. Fails reviewen und als Beispiele nachtragen
python cli.py log --flagged
# → Frage + generiertes SQL + Fehler direkt sichtbar
# → korrigiertes SQL als neues Beispiel in pllm_config.yaml einfügen
# → zurück zu Schritt 6
```

Dieser Frage→Fail→Beispiel-Loop ist der eigentliche "Prompt-Design"-Prozess — nicht alles lässt sich vorab antizipieren, der Logger macht das systematisch nachvollziehbar.

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
├── pllm_config.yaml        # Hauptkonfiguration (Pfade, Modell, Prompt, Value Inventories)
├── pyproject.toml
├── setup.ps1               # Windows-Quickstart
├── src/
│   ├── config.py           # Konfigurationsloader (YAML + Env-Vars), zentrale Accessor-Funktionen
│   ├── generator.py        # Faker-Datengenerator → CSV
│   ├── converter.py        # CSV → Parquet (einfach, ohne YAML)
│   ├── profiler.py         # CSV-Profiler: Statistiken, Schema, FK-Erkennung → YAML
│   ├── yaml2duckdb.py      # YAML-Profile → typisierte DuckDB-Tabellen + Parquet
│   ├── query_log.py        # JSONL-Logger für Queries, Flag-Mechanismus
│   ├── schema.py           # System-Prompt: generische DuckDB-Regeln + Fallback-Schema/-Beispiele
│   ├── db.py               # DuckDB-Verbindung (in-memory oder persistent), thread-sicher
│   ├── llm.py              # Ollama ChatSession: ask() + feed_result() + interpret()
│   └── app.py              # NiceGUI Chat-Frontend, Chart-Erkennung, Multi-User, Logging
└── data/
    ├── csv/                # CSV-Quelldaten             (nicht eingecheckt)
    ├── schema/             # YAML-Profile (Schema-Layer) (nicht eingecheckt)
    ├── parquet/            # Typisierte Parquet-Dateien  (nicht eingecheckt)
    ├── db.duckdb           # Persistente DuckDB          (nicht eingecheckt)
    └── query_log.jsonl     # Query-Protokoll              (nicht eingecheckt)
```

---

## CSV-Profiler

`pllm profile` analysiert CSV-Dateien mit DuckDB `SUMMARIZE` und schreibt pro Tabelle eine YAML-Datei:

- **Schema**: DuckDB-Typen inkl. `CREATE TABLE` DDL mit `NOT NULL` und `REFERENCES`
- **Statistiken**: Kardinalität, Null-%, Min/Max je Spalte
- **Value Inventory**: alle Distinct-Werte für Low-Cardinality-Spalten (≤50 unique) im Profil — nützlich für Doku, das eigentliche LLM-Value-Inventory kommt zur Laufzeit live aus der DB (siehe `value_inventories` in der Config)
- **Semantic Hints**: `identifier` / `date` / `measure` / `dimension` / `attribute` per Heuristik — bei ERP-Exporten manuell nachschärfen, z.B. wenn eine `_id`-Spalte tatsächlich eine Kategorie ist
- **FK-Kandidaten**: Namensanalyse (`project_id` → `project`, `artikel_id` → `artikel`)

`DOUBLE` wird immer als `DECIMAL` ausgegeben — in kaufmännischen Daten sind Fließkommazahlen fast immer Geldbeträge.

### Manuelle Profil-Erweiterungen für reale Daten

ERP-Exporte haben oft Eigenheiten die die automatische Erkennung nicht abdeckt — pro Spalte ergänzbar:

```yaml
- name: liefertermin
  duckdb_type: VARCHAR
  date_format: "%d.%m.%y"        # nicht-ISO-Datumsformat → STRPTIME statt CAST
  null_values: ["++.++.++"]      # Sentinel-Werte → werden nach dem Laden auf NULL gesetzt
```

`yaml2duckdb` liest Spalten mit `date_format` zunächst als VARCHAR ein (DuckDBs `read_csv_auto` würde sie sonst selbst — oft falsch — als DATE interpretieren, z.B. `31.12.25` als Jahr 2031) und wendet dann `STRPTIME` an. `null_values` werden nach dem Laden per `UPDATE ... SET col = NULL WHERE col = '...'` bereinigt.

---

## LLM-Ansatz

### Prompt-Schichten

Der System-Prompt besteht aus mehreren Schichten:

```
system_role          ← pllm_config.yaml: prompt.system_role
DuckDB-Regelwerk     ← schema.py (generisch, systemkritisch, hardcoded)
Schema               ← data/schema/*.yaml (Profile)  ODER  schema.py Fallback
Value Inventories    ← live aus DB geladen (pllm_config.yaml: value_inventories)
extra_rules          ← pllm_config.yaml: prompt.extra_rules
examples             ← pllm_config.yaml: prompt.examples  ODER  schema.py Fallback
```

Designprinzip: Regeln die für das System unumgänglich sind (kein Markdown, DuckDB-Syntaxkorrekturen, Follow-up-Mechanismus) sind in `schema.py` hardcoded. Alles Domänenspezifische (welche Tabellen, welche Eigenheiten, welche Beispiele) lebt in `pllm_config.yaml` und kann ohne Codeänderung angepasst werden.

Mit `python cli.py prompt` lässt sich der komplette zusammengesetzte Prompt jederzeit einsehen — hilfreich beim Debuggen von Fehlinterpretationen.

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

`feed_result()` hängt nach jeder Abfrage die Ergebniszeilen als `[SYSTEM-ERGEBNIS]`-Block an die letzte Assistenten-Nachricht. Folgefragen können so konkrete Werte aus dem vorherigen Ergebnis referenzieren, statt auf Beispielwerte zurückzufallen.

### Value Inventories (dynamisch)

Beim App-Start werden die in `value_inventories` konfigurierten SQL-Queries live gegen die DB ausgeführt und als eigene Stammdaten-Sektion in den Prompt injiziert:

```yaml
value_inventories:
  - label: Mitarbeiter
    sql: "SELECT CONCAT(prename, ' ', name) AS vollname FROM mitarbeiter ORDER BY name"
    hint: "Für Personensuchen: CONCAT(prename, ' ', name) ILIKE '%Vorname Nachname%'"
```

Wichtig: bewusst **nicht** aus den statischen Profil-Samples übernommen — Stammdaten (Mitarbeiter, Projekte, Lieferanten) ändern sich über die Zeit, ein Snapshot würde veralten. Mehrere getrennte Inventories (z.B. interne `mitarbeiter` vs. externe `kontakte`) helfen dem Modell außerdem, Namen der richtigen Tabelle zuzuordnen.

### Query-Logger

Jede Abfrage (Frage, generiertes SQL, Fehler, Zeilenzahl, ob ein Retry nötig war) wird nach `data/query_log.jsonl` geschrieben. Im Chat gibt es pro Antwort einen 👎-Button, der den Eintrag als `flagged: true` markiert.

```bash
python cli.py log --flagged
```

zeigt alle markierten Einträge mit voller Frage + SQL + Fehlermeldung — die direkte Vorlage um neue `examples`/`extra_rules` in der Config zu ergänzen.

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
# → system_role, value_inventories, examples anpassen

# 2. Daten ablegen und profilen
cp /pfad/zu/daten/*.csv data/csv/
python cli.py --config meine_domäne.yaml profile

# 3. In DuckDB laden
python cli.py --config meine_domäne.yaml yaml2duckdb

# 4. Starten, testen, Fails sammeln, nachschärfen
python cli.py --config meine_domäne.yaml chat
python cli.py --config meine_domäne.yaml log --flagged
```

Kein Code anfassen.

---

## Bekannte Einschränkungen

- SQL-Qualität hängt vom Modell ab; `qwen2.5-coder:7b` ist bei komplexen Subqueries überlegen
- Max. 1 automatischer Retry — mehrfach verschachtelte Fehler müssen manuell als Follow-up korrigiert werden
- Konversationshistorie liegt im RAM, kein Persistence über Server-Neustarts
- FK-Erkennung im Profiler ist namensbasiert; semantisch unbenannte FKs werden nicht erkannt, `_id`-Suffixe ohne FK-Charakter (Kategorien) werden fälschlich als `identifier` klassifiziert — manuelle Korrektur im Profil nötig
- DuckDB enforced keine FK-Constraints — `REFERENCES` dient nur als Dokumentation für den LLM
- `read_csv_auto` parst Datumsspalten mit zweistelligem Jahr oft falsch (z.B. `31.12.25` → Jahr 2031 statt 2025) — `date_format` im Profil zwingend bei nicht-ISO-Formaten
- Reale Datenquellen (ERP-Exporte) bringen oft Sentinel-Werte (`++.++.++`, `(0,0,0)`) und inkonsistente Spalten mit — `null_values` im Profil deckt das ab, eine instabile Export-Pipeline bleibt aber eine Datenqualitätsfrage außerhalb dieses Tools

---

## Lizenz

MIT
