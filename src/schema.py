"""System-Prompt und Schema-Beschreibung für die LLM-SQL-Generierung."""
from datetime import date

from . import config

_SCHEMA = """
## Datenbankschema

### Tabelle: kontakte
| Spalte     | Typ     | Beschreibung           |
|------------|---------|------------------------|
| kontakt_id | INTEGER | Primärschlüssel        |
| name       | VARCHAR | Vollständiger Name     |
| email      | VARCHAR | E-Mail-Adresse         |
| telefon    | VARCHAR | Telefonnummer          |

### Tabelle: projekte
| Spalte               | Typ     | Beschreibung                              |
|----------------------|---------|-------------------------------------------|
| projektnummer        | INTEGER | Primärschlüssel, 5-stellig (z.B. 10001)  |
| schlagwort           | VARCHAR | Kurzbeschreibung des Projekts             |
| adresse              | VARCHAR | Projektadresse mit Stadt                  |
| projektleiter_id     | INTEGER | FK → kontakte.kontakt_id                  |
| projekteinkäufer_id  | INTEGER | FK → kontakte.kontakt_id                  |

### Tabelle: gewerke
| Spalte    | Typ     | Beschreibung                                          |
|-----------|---------|-------------------------------------------------------|
| gewerk_id | INTEGER | Primärschlüssel                                       |
| name      | VARCHAR | Name des Gewerks (Elektro, Sanitär, Heizung, Lüftung, Tiefbau, Hochbau, Maler, Schreiner, Metall, Dachdecker) |

### Tabelle: artikel
| Spalte       | Typ     | Beschreibung                          |
|--------------|---------|---------------------------------------|
| nummer       | INTEGER | Primärschlüssel, 6-stellig            |
| name         | VARCHAR | Artikelname                           |
| suchwort     | VARCHAR | Suchkürzel ohne Leerzeichen (CamelCase, z.B. KBLNymJ3X15001) |
| artikelgruppe| VARCHAR | Gruppe ohne Leerzeichen (Kabel, Rohr, Fitting, Schalter, Armatur, Dämmung, Befestigung) |

### Tabelle: einkaufspositionen
| Spalte               | Typ     | Beschreibung                                          |
|----------------------|---------|-------------------------------------------------------|
| belegnummer          | INTEGER | Belegnummer, 6-stellig (ein Beleg hat mehrere Positionen) |
| belegdatum           | DATE    | Datum des Belegs                                      |
| typ                  | VARCHAR | Belegtyp: 'Anfrage', 'Bestellung' oder 'Rechnung'     |
| referenz_belegnummer | INTEGER | Vorgaenger-Beleg: Bestellung→Anfrage, Rechnung→Bestellung; NULL bei Anfragen |
| liefertermin         | DATE    | Vereinbarter Liefertermin; nur bei Bestellungen gesetzt, sonst NULL |
| artikel_nr           | INTEGER | FK → artikel.nummer                                   |
| gewerk_id            | INTEGER | FK → gewerke.gewerk_id                                |
| position             | INTEGER | Positionsnummer innerhalb des Belegs (1, 2, 3, …)     |
| menge                | INTEGER | Menge                                                 |
| preis                | DECIMAL | Einzelpreis in Euro (darf zwischen Anfrage/Bestellung/Rechnung leicht abweichen) |
| rabatt               | DECIMAL | Rabatt als Dezimalzahl (0.10 = 10 %, 0.0 = kein Rabatt) |
| positionswert        | DECIMAL | Nettobetrag: menge * preis * (1 - rabatt)             |
| freitext             | VARCHAR | Optionaler Kommentar zur Position                     |
| projekt_nr           | INTEGER | FK → projekte.projektnummer                           |
| lieferant_nr         | INTEGER | Lieferantennummer, 6-stellig                          |
| lieferant_name       | VARCHAR | Name des Lieferanten                                  |

### Vorgangskette
Anfrage (referenz_belegnummer IS NULL)
  → Bestellung (referenz_belegnummer = Anfrage.belegnummer, hat liefertermin)
    → Rechnung (referenz_belegnummer = Bestellung.belegnummer)

Eine Bestellung gilt als UEBERFAELLIG wenn:
  liefertermin < CURRENT_DATE
  UND keine Rechnung mit referenz_belegnummer = Bestellung.belegnummer existiert

## Beziehungen
- projekte.projektleiter_id → kontakte.kontakt_id
- projekte.projekteinkäufer_id → kontakte.kontakt_id
- einkaufspositionen.artikel_nr → artikel.nummer
- einkaufspositionen.gewerk_id → gewerke.gewerk_id
- einkaufspositionen.projekt_nr → projekte.projektnummer
"""

# Eingebaute Beispiele als Fallback wenn keine Config-Beispiele vorhanden.
# Bei neuen Domänen werden diese durch prompt.examples in pllm_config.yaml ersetzt.
_BUILTIN_EXAMPLES = """
## Beispiele (Frage → erwartetes SQL)

Frage: Alle Projekte anzeigen
SQL: SELECT projektnummer, schlagwort, adresse FROM projekte ORDER BY projektnummer

Frage: Alle Bestellungen für Projekt 10001
SQL: SELECT belegnummer, belegdatum, position, menge, preis, positionswert, lieferant_name FROM einkaufspositionen WHERE projekt_nr = 10001 AND typ = 'Bestellung' ORDER BY belegnummer, position

Frage: Gesamtwert aller Rechnungen pro Projekt
SQL: SELECT p.projektnummer, p.schlagwort, SUM(e.positionswert) AS rechnungssumme FROM einkaufspositionen e JOIN projekte p ON e.projekt_nr = p.projektnummer WHERE e.typ = 'Rechnung' GROUP BY p.projektnummer, p.schlagwort ORDER BY rechnungssumme DESC

Frage: Top 5 Lieferanten nach Bestellvolumen
SQL: SELECT lieferant_name, COUNT(DISTINCT belegnummer) AS anzahl_belege, SUM(positionswert) AS volumen FROM einkaufspositionen WHERE typ = 'Bestellung' GROUP BY lieferant_name ORDER BY volumen DESC LIMIT 5

Frage: Rechnungen nach Monat gruppiert
SQL: SELECT DATE_TRUNC('month', belegdatum) AS monat, COUNT(DISTINCT belegnummer) AS anzahl_belege, SUM(positionswert) AS summe FROM einkaufspositionen WHERE typ = 'Rechnung' GROUP BY monat ORDER BY monat

Frage: Bestellungen im Gewerk Elektro im letzten Quartal
SQL: SELECT e.belegnummer, e.belegdatum, e.lieferant_name, g.name AS gewerk, e.positionswert FROM einkaufspositionen e JOIN gewerke g ON e.gewerk_id = g.gewerk_id WHERE g.name = 'Elektro' AND e.typ = 'Bestellung' AND e.belegdatum >= CURRENT_DATE - INTERVAL '3 months' ORDER BY e.belegdatum DESC

Frage: Projektleiter und Einkäufer pro Projekt
SQL: SELECT p.projektnummer, p.schlagwort, kl.name AS projektleiter, ke.name AS projekteinkäufer FROM projekte p JOIN kontakte kl ON p.projektleiter_id = kl.kontakt_id JOIN kontakte ke ON p."projekteinkäufer_id" = ke.kontakt_id

Frage: Welche Belegtypen erstellt Yvette Otto am häufigsten?
SQL: SELECT e.typ, COUNT(DISTINCT e.belegnummer) AS anzahl FROM einkaufspositionen e JOIN projekte p ON e.projekt_nr = p.projektnummer JOIN kontakte k ON p."projekteinkäufer_id" = k.kontakt_id WHERE k.name ILIKE '%Yvette Otto%' GROUP BY e.typ ORDER BY anzahl DESC

Frage: Durchschnittlicher Rabatt pro Lieferant
SQL: SELECT lieferant_name, ROUND(AVG(rabatt) * 100, 1) AS avg_rabatt_pct, COUNT(*) AS positionen FROM einkaufspositionen WHERE rabatt > 0 GROUP BY lieferant_name ORDER BY avg_rabatt_pct DESC

Frage: Durchschnittlicher Bestellwert pro Monat
SQL: SELECT monat, ROUND(AVG(total), 2) AS avg_bestellwert FROM (SELECT belegnummer, DATE_TRUNC('month', MIN(belegdatum)) AS monat, SUM(positionswert) AS total FROM einkaufspositionen WHERE typ = 'Bestellung' GROUP BY belegnummer) t GROUP BY monat ORDER BY monat

Frage: Alle ueberfaelligen Bestellungen (Liefertermin vergangen, noch keine Rechnung)
SQL: SELECT b.belegnummer, b.belegdatum, b.liefertermin, b.lieferant_name, b.projekt_nr, DATEDIFF('day', b.liefertermin::DATE, CURRENT_DATE) AS tage_ueberfaellig, ROUND(SUM(b.positionswert), 2) AS bestellwert FROM einkaufspositionen b WHERE b.typ = 'Bestellung' AND b.liefertermin::DATE < CURRENT_DATE AND b.belegnummer NOT IN (SELECT referenz_belegnummer FROM einkaufspositionen WHERE typ = 'Rechnung' AND referenz_belegnummer IS NOT NULL) GROUP BY b.belegnummer, b.belegdatum, b.liefertermin, b.lieferant_name, b.projekt_nr ORDER BY b.liefertermin

Frage: Vorgangskette Anfrage Bestellung Rechnung mit Status fuer ein Projekt
SQL: SELECT a.belegnummer AS anfrage_nr, a.belegdatum AS anfrage_datum, b.belegnummer AS bestell_nr, b.belegdatum AS bestell_datum, b.liefertermin, r.belegnummer AS rechnung_nr, CASE WHEN r.belegnummer IS NOT NULL THEN 'Abgerechnet' WHEN b.belegnummer IS NULL THEN 'Nur Anfrage' WHEN b.liefertermin::DATE < CURRENT_DATE THEN 'Ueberfaellig' ELSE 'Offen' END AS status FROM (SELECT DISTINCT belegnummer, belegdatum, projekt_nr FROM einkaufspositionen WHERE typ = 'Anfrage') a LEFT JOIN (SELECT DISTINCT belegnummer, belegdatum, liefertermin, referenz_belegnummer FROM einkaufspositionen WHERE typ = 'Bestellung') b ON b.referenz_belegnummer = a.belegnummer LEFT JOIN (SELECT DISTINCT belegnummer, referenz_belegnummer FROM einkaufspositionen WHERE typ = 'Rechnung') r ON r.referenz_belegnummer = b.belegnummer WHERE a.projekt_nr = 10001 ORDER BY a.belegnummer

Frage: Gib mir die Adresse zu dem Projekt, wo xxx yyy Projekteinkäufer ist.
SQL: SELECT p.projektnummer, p.schlagwort, p.adresse, k.name AS projekteinkäufer FROM projekte p JOIN kontakte k ON p."projekteinkäufer_id" = k.kontakt_id WHERE k.name ILIKE '%xxx yyy%'
[SYSTEM-ERGEBNIS: projektnummer=10017, schlagwort=Rohstoff Neubau, adresse=Hauptstr. 5 Hamburg, projekteinkäufer=xxx yyy]

Folgefrage: Zeig das Projekt.
SQL: SELECT * FROM projekte WHERE projektnummer = 10017
"""


def _extra_rules_section() -> str:
    rules = config.extra_rules()
    if not rules:
        return ""
    lines = "\n".join(f"- {r}" for r in rules)
    return f"\n## Zusätzliche Regeln (aus Konfiguration)\n{lines}\n"


def _examples_section() -> str:
    """Config-Beispiele haben Vorrang — sonst eingebaute Demo-Beispiele als Fallback."""
    examples = config.prompt_examples()
    if examples:
        lines = []
        for ex in examples:
            entry = f"Frage: {ex['q']}\nSQL: {ex['sql'].strip()}"
            # Optionales Follow-up (Kontext + Folgefrage)
            if ex.get("context"):
                entry += f"\n{ex['context']}"
            if ex.get("followup_q"):
                entry += f"\nFolgefrage: {ex['followup_q']}\nSQL: {ex['followup_sql'].strip()}"
            lines.append(entry)
        return "\n## Beispiele (Frage → erwartetes SQL)\n\n" + "\n\n".join(lines) + "\n"
    return _BUILTIN_EXAMPLES


def get_system_prompt(
    kontakte: list[str] | None = None,
    lieferanten: list[str] | None = None,
    profiles: list[dict] | None = None,
    value_inventories: list[dict] | None = None,
) -> str:
    today = date.today().isoformat()

    # Schema-Sektion: aus Profilen wenn vorhanden, sonst manuell gepflegtes _SCHEMA
    if profiles:
        from .profiler import profiles_to_prompt_section
        schema_section = (
            "## Datenbankschema (aus Profildaten)\n\n"
            + profiles_to_prompt_section(profiles)
        )
    else:
        schema_section = _SCHEMA

    # Dynamische Value Inventories (aus DB zur Laufzeit) haben Vorrang
    # Legacy-Fallback auf statische kontakte/lieferanten-Listen
    if value_inventories:
        inv_lines = []
        for inv in value_inventories:
            values_str = ", ".join(str(v) for v in inv["values"])
            block = f"### {inv['label']}\n{values_str}"
            if inv.get("hint"):
                block += f"\n→ {inv['hint']}"
            inv_lines.append(block)
        kontakte_section = "\n## Stammdaten (zur Laufzeit aus DB geladen)\n\n" + "\n\n".join(inv_lines) + "\n"
        lieferanten_section = ""
    else:
        # Legacy-Fallback für Demo-Daten
        kontakte_section = (
            "\n## Bekannte Kontaktnamen\n"
            + ", ".join(kontakte)
            + "\nNutze diese Namen für ILIKE-Filter bei Personensuchen.\n"
            if kontakte else ""
        )
        lieferanten_section = (
            "\n## Bekannte Lieferantennamen\n"
            + ", ".join(lieferanten)
            + "\nLieferanten sind KEINE eigene Tabelle — lieferant_name und lieferant_nr "
            "stehen direkt als Spalten in einkaufspositionen. Niemals auf eine Tabelle "
            "'lieferanten' joinen. Nutze ILIKE auf einkaufspositionen.lieferant_name.\n"
            if lieferanten else ""
        )
    _role = config.system_role() or "Du bist ein SQL-Experte für DuckDB. Du generierst SQL-Abfragen basierend auf Nutzerfragen in natürlicher Sprache."
    return f"""{_role}

## Regeln
- Antworte NUR mit dem SQL-Statement — keine Erklärungen, kein Markdown, keine Codeblöcke
- Verwende ausschließlich DuckDB-kompatibles SQL
- Heutiges Datum: {today} — für relative Zeitangaben CURRENT_DATE und INTERVAL-Syntax verwenden
- Spaltennamen mit Umlauten (z.B. projekteinkäufer_id) in doppelte Anführungszeichen setzen
- Textsuche auf Namen/Adressen/Bezeichnungen immer mit ILIKE statt LIKE (case-insensitiv)
- Bei Folgefragen IMMER auf den KONVERSATIONSVERLAUF zurueckgreifen:
      a) Den [SYSTEM-ERGEBNIS]-Block der letzten Antwort prüfen — dort stehen konkrete
         Werte (IDs, Nummern, Namen) aus dem vorherigen Ergebnis. Diese direkt als Filter verwenden.
      b) Falls der gesuchte Wert im Ergebnis fehlt, die WHERE-/JOIN-Bedingungen des letzten
         SQL ableiten und als Subquery wiederverwenden.
      c) Werte aus den BEISPIELEN unten sind NUR illustrativ — sie dürfen NIEMALS als
         Kontext-Anker bei Folgefragen dienen.
      Das vorherige SQL sinnvoll erweitern oder umschreiben (z.B. "gruppiere das nach Monat")
- Zahlen in Euro auf 2 Dezimalstellen runden: ROUND(wert, 2)
- FALSCH: col IS NOT IN (...)   RICHTIG: col NOT IN (...)
      FALSCH: col IS IN (...)       RICHTIG: col IN (...)
      IS/IS NOT nur für NULL-Vergleiche: col IS NULL, col IS NOT NULL
- Datumsfilter NUR einbauen wenn die Frage explizit einen Zeitraum oder ein Datum nennt.
      Enthält die Frage KEIN Datum, KEIN "letztes Quartal", KEIN "dieses Jahr" o.ä. → KEINEN Datumsfilter setzen.
- Bei ambigen Anfragen die naheliegendste Interpretation wählen
- DuckDB-Funktionen statt PostgreSQL/Oracle verwenden:
    FALSCH: TO_CHAR(datum, 'YYYY-MM')  RICHTIG: strftime(datum::DATE, '%Y-%m')
    FALSCH: TO_DATE(str, 'YYYY-MM-DD') RICHTIG: CAST(str AS DATE)
    FALSCH: NVL(a, b)                  RICHTIG: COALESCE(a, b)
    FALSCH: DECODE(x, a, b)            RICHTIG: CASE WHEN x=a THEN b END
    Datum-Filter: belegdatum::DATE >= '2025-01-01' AND belegdatum::DATE < '2025-02-01'
    Jahr/Monat extrahieren: YEAR(belegdatum), MONTH(belegdatum)
    Kalenderformat: strftime(datum::DATE, '%Y-W%V') fuer ISO-Kalenderwoche
    Quartal: FALSCH: strftime(..., '%Y-Q%q')  RICHTIG: YEAR(belegdatum) || '-Q' || QUARTER(belegdatum)
    Differenz in Tagen: FALSCH: DATE_PART('day', date1 - date2)  RICHTIG: DATEDIFF('day', date1, date2)

{schema_section}{kontakte_section}{lieferanten_section}{_extra_rules_section()}{_examples_section()}
Gib ausschließlich das SQL zurück, sonst nichts."""
