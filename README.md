# Projekt-LLM

Proof of Concept: Natürlichsprachliche Abfragen auf einer lokalen Projektdatenbank — ohne NL-Parser, stattdessen generiert ein lokales LLM das SQL on-the-fly.

---

## Idee

Ein lokales LLM (via [Ollama](https://ollama.com)) erhält eine kompakte Schemabeschreibung mit Beispielabfragen und dem aktuellen Datum. Auf Basis dieser Semantik generiert es DuckDB-SQL, das direkt auf Parquet-Dateien ausgeführt wird. Das Ergebnis erscheint als interaktive Tabelle und Chart im Chat.

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
- Verkettete Belegkette: Anfrage → Bestellung → Rechnung mit Preisvariation und Liefertermin
- **CSV-Profiler**: analysiert CSV-Pakete, leitet DuckDB-Schema ab, schreibt YAML-Meta-Layer
- **yaml2duckdb**: lädt YAML-Profile typisiert in DuckDB und/oder Parquet
- Datengenerator für realistische Testdaten (Faker, `de_DE`)
- CLI für alle Schritte: Datengenerierung, Profiling, Konvertierung, Chat, direkte SQL-Abfragen

---

## Tech Stack

| Komponente | Technologie |
|---|---|
| Storage | CSV → Parquet |
| Query Engine | [DuckDB](https://duckdb.org) |
| LLM | [Ollama](https://ollama.com) (lokal) |
| Frontend | [NiceGUI](https://nicegui.io) |
| Charts | ECharts (via `ui.echart`) |
| CLI | [Typer](https://typer.tiangolo.com) + [Rich](https://rich.readthedocs.io) |
| Datengenerator | [Faker](https://faker.readthedocs.io) (`de_DE`) |

---

## Datenmodell

```
kontakte
  kontakt_id, name, email, telefon

projekte
  projektnummer (5-stellig), schlagwort, adresse
  projektleiter_id    → kontakte
  projekteinkäufer_id → kontakte

gewerke
  gewerk_id, name  (Elektro, Sanitär, Heizung, Lüftung, Tiefbau, …)

artikel
  nummer (6-stellig), name
  suchwort       (CamelCase, kein Leerzeichen)
  artikelgruppe  (Kabel, Rohr, Fitting, Schalter, Armatur, Dämmung, Befestigung)

einkaufspositionen
  belegnummer (6-stellig), belegdatum
  typ                  Anfrage | Bestellung | Rechnung
  referenz_belegnummer → vorheriger Beleg (Bestellung→Anfrage, Rechnung→Bestellung)
  liefertermin         gesetzt nur bei Bestellungen
  artikel_nr  → artikel
  gewerk_id   → gewerke
  projekt_nr  → projekte
  position, menge, preis, rabatt, positionswert
  lieferant_nr, lieferant_name, freitext
```

### Vorgangskette

```
Anfrage  ──(70%)──▶  Bestellung  ──(65% der fälligen)──▶  Rechnung
           ±7% Preis   + Liefertermin                       ±2% Preis
```

Eine Bestellung gilt als **überfällig** wenn `liefertermin < heute` und noch keine Rechnung existiert.

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

## Setup (Windows)

```powershell
cd C:\dev\repos\project_llm
.\setup.ps1
```

Das Script erstellt eine virtuelle Umgebung, installiert alle Abhängigkeiten und generiert Testdaten.

**Manuell (alle Plattformen):**

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
python cli.py init             # Daten generieren + nach Parquet konvertieren
```

---

## Verwendung

### Chat-Frontend starten

```bash
python cli.py chat
# Mit anderem Modell:
python cli.py chat --model gemma3
```

Öffnet automatisch `http://127.0.0.1:8080`.

### CLI-Befehle

```bash
python cli.py generate          # Testdaten als CSV erzeugen
python cli.py convert           # CSV → Parquet (einfach, ohne Typisierung)
python cli.py init              # generate + convert in einem Schritt
python cli.py chat              # NiceGUI-Frontend starten
python cli.py query "SELECT …"  # SQL direkt ausführen (ohne LLM)
python cli.py models            # Verfügbare Ollama-Modelle anzeigen

# Profiling & typisierte Konvertierung
python cli.py profile data/csv/                          # alle CSVs analysieren → data/profiles/*.yaml
python cli.py profile data/csv/projekte.csv              # einzelne Datei
python cli.py yaml2duckdb data/profiles/                 # YAML → Parquet (Default: data/parquet/)
python cli.py yaml2duckdb data/profiles/ --db data/warehouse.duckdb          # → persistente DuckDB
python cli.py yaml2duckdb data/profiles/ --db data/warehouse.duckdb \
                                         --parquet data/parquet/             # → beides
```

### Gegen eine persistente DuckDB testen

Wer statt Parquet-Views direkt gegen eine DuckDB-Datei arbeiten will (z.B. nach `yaml2duckdb --db`):

```bash
# Windows
set PLLM_DB=data/warehouse.duckdb
python cli.py chat

# Linux/Mac
PLLM_DB=data/warehouse.duckdb python cli.py chat
```

Ist `PLLM_DB` gesetzt, verbindet sich `db.py` mit der Datei statt in-memory. Die Tabellen müssen dann bereits drin sein (`yaml2duckdb --db` hat sie angelegt).

---

### Empfohlener Workflow mit eigenen Daten

```bash
# 1. CSV-Daten ablegen
cp meine_daten/*.csv data/csv/

# 2. Profilen — Schema ableiten, YAML schreiben
python cli.py profile data/csv/

# 3. Review: data/profiles/*.yaml prüfen und ggf. Typen anpassen

# 4. Typisiert laden
python cli.py yaml2duckdb data/profiles/ --parquet data/parquet/

# 5. Chat starten
python cli.py chat
```

---

## Projektstruktur

```
project_llm/
├── cli.py                  # Typer-Einstiegspunkt
├── pyproject.toml
├── setup.ps1               # Windows-Quickstart
├── src/
│   ├── generator.py        # Faker-Datengenerator → CSV (Anfrage→Bestellung→Rechnung)
│   ├── converter.py        # CSV → Parquet via DuckDB (einfach, ohne YAML)
│   ├── profiler.py         # CSV-Profiler: Statistiken, Schema, FK-Erkennung → YAML
│   ├── yaml2duckdb.py      # YAML-Profile → typisierte DuckDB-Tabellen + Parquet
│   ├── schema.py           # System-Prompt: Schema + Beispielabfragen + DuckDB-Regeln
│   ├── db.py               # DuckDB-Views über Parquet, thread-sicher
│   ├── llm.py              # Ollama ChatSession: ask() + feed_result() + interpret()
│   └── app.py              # NiceGUI Chat-Frontend, Chart-Erkennung, Multi-User
└── data/
    ├── csv/                # CSV-Quelldaten            (nicht eingecheckt)
    ├── profiles/           # YAML-Meta-Layer           (nicht eingecheckt)
    └── parquet/            # Typisierte Parquet-Dateien (nicht eingecheckt)
```

---

## CSV-Profiler

`pllm profile` analysiert CSV-Dateien mit DuckDB `SUMMARIZE` und schreibt pro Tabelle eine YAML-Datei mit:

- abgeleitetem DuckDB-Schema inkl. `CREATE TABLE`-DDL
- Statistiken je Spalte: Typ, Nullable, Kardinalität, Null-%, Min/Max, Mittelwert, Sample-Werte
- Semantic Hint (`identifier` / `date` / `measure` / `dimension` / `attribute`) per Heuristik
- FK-Kandidaten durch Namensanalyse (`projekt_nr` → `projekte`, `artikel_nr` → `artikel`)

`DOUBLE` wird dabei immer als `DECIMAL` ausgegeben — in kaufmännischen Daten sind Fließkommazahlen fast immer Geldbeträge.

Beispiel-YAML (`projekte.yaml`):

```yaml
table: projekte
source: data/csv/projekte.csv
profiled_at: '2026-06-25'
row_count: 25
ddl: |
  CREATE TABLE projekte (
    projektnummer INTEGER,
    schlagwort VARCHAR,
    adresse VARCHAR,
    projektleiter_id INTEGER,
    projekteinkäufer_id INTEGER
  );
columns:
  - name: projektnummer
    duckdb_type: INTEGER
    nullable: false
    unique_count: 25
    null_pct: 0.0
    sample: ['10001', '10002', '10003']
    min: '10001'
    max: '10025'
    semantic_hint: identifier

  - name: projektleiter_id
    duckdb_type: INTEGER
    nullable: false
    unique_count: 12
    semantic_hint: identifier
    fk_candidate: kontakte
```

---

## LLM-Ansatz

### Zwei-Pass-Strategie

Jede Nutzeranfrage durchläuft zwei LLM-Calls:

1. **SQL-Generierung** (`ask()`) — zustandsbehaftet, mit vollständigem Gesprächsverlauf. Das Modell antwortet ausschließlich mit dem SQL-Statement.
2. **Freitext-Zusammenfassung** (`interpret()`) — zustandslos, bekommt nur Frage + Ergebnis. Liefert 2–3 Sätze mit konkreten Zahlen und Namen.

### Automatischer SQL-Retry

Bei einem DuckDB-Fehler wird die Fehlermeldung automatisch ans LLM zurückgegeben:

```
→ LLM:    SELECT … WHERE col IS NOT IN (…)
→ DuckDB: Parser Error: syntax error at or near "NOT"
→ Retry:  LLM korrigiert → SELECT … WHERE col NOT IN (…)  ✓
```

Schlägt auch der zweite Versuch fehl, erscheint der Fehler im Chat. Die SQL-Klappe zeigt `SQL (korrigiert)` wenn ein Retry erfolgreich war.

### Follow-up-Kontext

Nach jeder erfolgreichen Abfrage hängt `feed_result()` eine kompakte Vorschau der zurückgegebenen Daten als `[SYSTEM-ERGEBNIS]`-Block an die letzte Assistenten-Nachricht im Verlauf. Damit kann das Modell bei Folgefragen auf konkrete Werte (z. B. Projektnummern) aus dem vorherigen Ergebnis zurückgreifen, statt auf Demo-Werte aus den Beispielabfragen zu fallen.

### Value Inventories

Beim App-Start werden `kontakte.name` und `einkaufspositionen.lieferant_name` aus DuckDB geladen und in jeden System-Prompt injiziert. Das verhindert zwei häufige Fehler bei kleineren Modellen:

- Personennamen werden per `ILIKE` korrekt aufgelöst statt halluziniert
- Lieferanten werden nicht fälschlicherweise als eigene Tabelle gesucht

### System-Prompt

Das Modell erhält:

- vollständiges Tabellenschema inkl. Spaltentypen und Fremdschlüsseln
- Geschäftsregeln (Vorgangskette, Überfälligkeitsdefinition, `positionswert`-Formel)
- das heutige Datum (für relative Zeitabfragen wie *"letztes Quartal"*)
- DuckDB-spezifische Funktionsregeln (`strftime` statt `TO_CHAR`, `ILIKE` für case-insensitive Suche, Quartal via `YEAR() || '-Q' || QUARTER()`, `NOT IN` statt `IS NOT IN`)
- Beispielpaare Frage → SQL für typische Muster (Subquery-Aggregation, JOINs, Datumsgruppierung, Vorgangskette, Follow-up-Kontext)

### Multi-User

Jeder Browser-Tab erhält eine eigene `ChatSession` (eigene Konversationshistorie). LLM-Requests werden über einen globalen `asyncio.Lock` serialisiert — Ollama läuft als einzelner Prozess, parallele Inferenz würde alle User verlangsamen. DuckDB-Zugriffe sind über einen separaten `threading.Lock` in `db.py` abgesichert.

```
Tab A ──┐                          ┌── globaler asyncio.Lock ──▶ Ollama
        ├── je eigene ChatSession ─┤
Tab B ──┘                          └── globaler threading.Lock ──▶ DuckDB
```

---

## Chart-Erkennung

Die Heuristik in `app.py` wählt automatisch den passenden Chart-Typ:

| Ergebnisstruktur | Chart |
|---|---|
| Datum/Zeit-Spalte + Messwert | Linie mit Fläche |
| ≤ 7 Kategorien + 1 Messwert | Donut |
| Kategorien + Messwerte | Balken |
| Nur IDs oder kein Messwert | kein Chart |

ID-artige Spalten (`*_id`, `*_nr`, `*nummer`) werden dabei nie als Messwert interpretiert, sondern als kategorische X-Achse.

---

## Bekannte Einschränkungen

- SQL-Qualität hängt vom Modell ab; `qwen2.5-coder:7b` ist General-Purpose-Modellen bei komplexen Subqueries überlegen
- Max. 1 automatischer Retry — mehrfach verschachtelte Fehler müssen manuell als Follow-up korrigiert werden
- Konversationshistorie liegt im RAM, kein Persistence über Server-Neustarts
- Profiler-FK-Erkennung ist namensbasiert; semantisch unbenannte FKs werden nicht erkannt

---

## Lizenz

MIT
