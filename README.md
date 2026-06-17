# Projekt-LLM

Proof of Concept: Natürlichsprachliche Abfragen auf einer lokalen Projektdatenbank — ohne NL-Parser, stattdessen generiert ein lokales LLM das SQL on-the-fly.

---

## Idee

Ein lokales LLM (via [Ollama](https://ollama.com)) erhält eine kompakte Schemabeschreibung mit Beispielabfragen und dem aktuellen Datum. Auf Basis dieser Semantik generiert es DuckDB-SQL, das direkt auf Parquet-Dateien ausgeführt wird. Das Ergebnis erscheint als interaktive Tabelle im Chat.

Follow-up-Fragen funktionieren, weil der vollständige Gesprächsverlauf als Kontext erhalten bleibt:

> *"Bestellungen für Projekt 10001"* → *"gruppiere nach Monat"* → *"nur Gewerk Elektro"*

---

## Features

- Natürlichsprachliche Abfragen ohne eigenen Parser
- Lokales LLM über Ollama (kein Cloud-API-Key nötig)
- Follow-up-Fragen durch Session-Kontext
- Interaktive Ergebnistabelle (sortierbar, filterbar, Pagination)
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
| CLI | [Typer](https://typer.tiangolo.com) + [Rich](https://rich.readthedocs.io) |
| Datengenerator | [Faker](https://faker.readthedocs.io) (`de_DE`) |

---

## Datenmodell

```
kontakte
  kontakt_id, name, email, telefon

projekte
  projektnummer (5-stellig), schlagwort, adresse
  projektleiter_id  → kontakte
  projekteinkäufer_id → kontakte

gewerke
  gewerk_id, name  (Elektro, Sanitär, Heizung, …)

artikel
  nummer (6-stellig), name
  suchwort       (CamelCase, kein Leerzeichen)
  artikelgruppe  (CamelCase, kein Leerzeichen)

einkaufspositionen
  belegnummer (6-stellig), belegdatum
  typ          Anfrage | Bestellung | Rechnung
  artikel_nr   → artikel
  gewerk_id    → gewerke
  projekt_nr   → projekte
  position, menge, preis, rabatt, positionswert
  lieferant_nr, lieferant_name, freitext
```

---

## Voraussetzungen

- Python 3.11+
- [Ollama](https://ollama.com) installiert und gestartet (`ollama serve`)
- Empfohlenes Modell:

```bash
ollama pull qwen2.5-coder:7b   # beste SQL-Qualität
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
│   ├── generator.py        # Faker-Datengenerator → CSV
│   ├── converter.py        # CSV → Parquet via DuckDB
│   ├── schema.py           # System-Prompt: Schema + Beispielabfragen + Datum
│   ├── db.py               # DuckDB-Views über Parquet, thread-sicher
│   ├── llm.py              # Ollama ChatSession mit Gesprächsverlauf
│   └── app.py              # NiceGUI Chat-Frontend
└── data/
    ├── csv/                # Generierte CSV-Dateien  (nicht eingecheckt)
    └── parquet/            # Konvertierte Parquet-Dateien  (nicht eingecheckt)
```

---

## LLM-Ansatz

Das LLM erhält einen System-Prompt mit:

- vollständigem Tabellenschema inkl. Spaltentypen und Fremdschlüsseln
- Geschäftsregeln (z. B. `positionswert = menge * preis * (1 - rabatt)`)
- dem heutigen Datum (für relative Zeitabfragen wie *"letztes Quartal"*)
- Beispielpaaren Frage → SQL für typische Muster (Subquery-Aggregation, JOINs, Datumsgruppierung)

Das Modell antwortet ausschließlich mit dem SQL-Statement. Die App führt es aus und zeigt das Ergebnis — kein weiteres Parsing nötig.

---

## Bekannte Einschränkungen

- Single-User-Tool: eine LLM-Session pro Prozess, kein Multi-User-Betrieb
- SQL-Qualität hängt vom Modell ab; komplexe Subquery-Muster gelingen `qwen2.5-coder` zuverlässiger als General-Purpose-Modellen
- Kein Retry bei SQL-Fehlern — die Fehlermeldung erscheint im Chat und kann als Follow-up weitergegeben werden

---

## Lizenz

MIT
