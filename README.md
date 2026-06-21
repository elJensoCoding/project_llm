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
- Automatische Chart-Erkennung: Zeitreihe → Linie/Fläche, ≤7 Kategorien → Donut, sonst Balken
- Interaktive Ergebnistabelle (sortierbar, filterbar, Pagination ab 20 Zeilen)
- Freitext-Zusammenfassung der Ergebnisse (zweiter LLM-Pass, zustandslos)
- Multi-User: jeder Browser-Tab bekommt eine eigene Konversationshistorie
- Verkettetete Belegkette: Anfrage → Bestellung → Rechnung mit Preisvariation und Liefertermin
- Datengenerator für realistische Testdaten (Faker, `de_DE`)
- CLI für alle Schritte: Datengenerierung, Konvertierung, Chat, direkte SQL-Abfragen

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
python cli.py generate   # Testdaten als CSV erzeugen
python cli.py convert    # CSV → Parquet
python cli.py init       # generate + convert in einem Schritt
python cli.py chat       # NiceGUI-Frontend starten
python cli.py query "SELECT ..."  # SQL direkt ausführen (ohne LLM)
python cli.py models     # Verfügbare Ollama-Modelle anzeigen
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
│   ├── converter.py        # CSV → Parquet via DuckDB
│   ├── schema.py           # System-Prompt: Schema + Beispielabfragen + DuckDB-Regeln
│   ├── db.py               # DuckDB-Views über Parquet, thread-sicher
│   ├── llm.py              # Ollama ChatSession: ask() + feed_result() + interpret()
│   └── app.py              # NiceGUI Chat-Frontend, Chart-Erkennung, Multi-User
└── data/
    ├── csv/                # Generierte CSV-Dateien  (nicht eingecheckt)
    └── parquet/            # Konvertierte Parquet-Dateien  (nicht eingecheckt)
```

---

## LLM-Ansatz

### Zwei-Pass-Strategie

Jede Nutzeranfrage durchläuft zwei LLM-Calls:

1. **SQL-Generierung** (`ask()`) — zustandsbehaftet, mit vollständigem Gesprächsverlauf. Das Modell antwortet ausschließlich mit dem SQL-Statement.
2. **Freitext-Zusammenfassung** (`interpret()`) — zustandslos, bekommt nur Frage + Ergebnis. Liefert 2–3 Sätze mit konkreten Zahlen und Namen.

### Follow-up-Kontext

Nach jeder erfolgreichen Abfrage hängt `feed_result()` eine kompakte Vorschau der zurückgegebenen Daten als `[SYSTEM-ERGEBNIS]`-Block an die letzte Assistenten-Nachricht im Verlauf. Damit kann das Modell bei Folgefragen auf konkrete Werte (z. B. Projektnummern) aus dem vorherigen Ergebnis zurückgreifen, statt auf Demo-Werte aus den Beispielabfragen zu fallen.

### System-Prompt

Das Modell erhält:

- vollständiges Tabellenschema inkl. Spaltentypen und Fremdschlüsseln
- Geschäftsregeln (Vorgangskette, Überfälligkeitsdefinition, `positionswert`-Formel)
- das heutige Datum (für relative Zeitabfragen wie *"letztes Quartal"*)
- DuckDB-spezifische Funktionsregeln (`strftime` statt `TO_CHAR`, `ILIKE` für case-insensitive Suche, Quartal via `YEAR() || '-Q' || QUARTER()`)
- Beispielpaare Frage → SQL für typische Muster (Subquery-Aggregation, JOINs, Datumsgruppierung, Vorgangskette)

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

- SQL-Qualität hängt vom Modell ab; komplexe Subquery-Muster gelingen `qwen2.5-coder:7b` zuverlässiger als General-Purpose-Modellen
- Kein automatischer SQL-Retry — die Fehlermeldung erscheint im Chat und kann als Follow-up weitergegeben werden
- Konversationshistorie liegt im RAM, kein Persistence über Server-Neustarts

---

## Lizenz

MIT
