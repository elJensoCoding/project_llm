"""Testdaten-Generator: erzeugt CSV-Dateien für alle Entitäten."""
import csv
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")

from faker import Faker

fake = Faker("de_DE")
random.seed(42)
Faker.seed(42)

DATA_DIR = Path(__file__).parent.parent / "data" / "csv"

# ---------------------------------------------------------------------------
# Kontakte
# ---------------------------------------------------------------------------

def _kontakte(n: int = 15) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "kontakt_id": i,
            "name": fake.name(),
            "email": fake.email(),
            "telefon": fake.phone_number(),
        })
    return rows


# ---------------------------------------------------------------------------
# Gewerke
# ---------------------------------------------------------------------------

_GEWERK_NAMES = [
    "Elektro", "Sanitär", "Heizung", "Lüftung",
    "Tiefbau", "Hochbau", "Maler", "Schreiner",
    "Metall", "Dachdecker",
]

def _gewerke() -> list[dict]:
    return [{"gewerk_id": i + 1, "name": n} for i, n in enumerate(_GEWERK_NAMES)]


# ---------------------------------------------------------------------------
# Artikel
# ---------------------------------------------------------------------------

_ARTIKEL_POOL = {
    "Kabel":        ["NYM-J 3x1.5", "NYM-J 5x2.5", "H07V-K 1x6", "LSZH 2x0.75", "Erdkabel NYY-J 3x4", "Steuerleitung LiYCY 4x0.75"],
    "Rohr":         ["HT-Rohr DN50", "HT-Rohr DN100", "Kupferrohr 15mm", "Kupferrohr 22mm", "PP-Rohr 20mm", "Edelstahlrohr 28mm"],
    "Fitting":      ["T-Stück 15mm", "Winkel 90° 22mm", "Muffe DN50", "Reduktion 22/15mm", "Kupplung 20mm", "Doppelnippel DN25"],
    "Schalter":     ["Taster 16A", "Schalter IP44", "Lichtschalter 2-polig", "Steckdose UP", "FI-Schutzschalter 40A", "Leitungsschutz B16"],
    "Armatur":      ["Kugelhahn DN25", "Absperrventil DN15", "Rückschlagventil DN20", "Thermostatventil", "Regulierventil DN32"],
    "Dämmung":      ["AF/Armaflex 13mm", "Steinwolle 50mm", "Glaswolle 80mm", "PIR-Platte 40mm", "PE-Schaum 6mm"],
    "Befestigung":  ["Rohrschelle DN50", "Gewindestange M10", "Dübel 8mm", "Schraube M6x20", "Winkelkonsole 60mm", "Kabelschelle 25mm"],
}

_GRUPPE_PREFIX = {
    "Kabel": "KBL", "Rohr": "RHR", "Fitting": "FTG",
    "Schalter": "SCH", "Armatur": "ARM", "Dämmung": "DAE", "Befestigung": "BFG",
}

def _suchwort(gruppe: str, name: str, idx: int) -> str:
    prefix = _GRUPPE_PREFIX.get(gruppe, "ART")
    word = "".join(p.capitalize() for p in name.replace("-", " ").replace("°", "").split())
    return f"{prefix}{word}{idx:03d}"

def _artikel() -> list[dict]:
    rows = []
    idx = 0
    for gruppe, names in _ARTIKEL_POOL.items():
        for name in names:
            idx += 1
            rows.append({
                "nummer": 100000 + idx,
                "name": name,
                "suchwort": _suchwort(gruppe, name, idx),
                "artikelgruppe": gruppe,
            })
    return rows


# ---------------------------------------------------------------------------
# Projekte
# ---------------------------------------------------------------------------

_STAEDTE = ["München", "Berlin", "Hamburg", "Köln", "Frankfurt", "Stuttgart", "Düsseldorf", "Nürnberg", "Bremen"]
_PROJEKT_TYPEN = ["Neubau", "Sanierung", "Umbau", "Erweiterung", "Modernisierung"]

def _projekte(kontakte: list[dict], n: int = 25) -> list[dict]:
    ids = [k["kontakt_id"] for k in kontakte]
    rows = []
    for i in range(n):
        pl = random.choice(ids)
        pe = random.choice([k for k in ids if k != pl])
        rows.append({
            "projektnummer": 10001 + i,
            "schlagwort": fake.company().split()[0] + " " + random.choice(_PROJEKT_TYPEN),
            "adresse": fake.street_address() + ", " + random.choice(_STAEDTE),
            "projektleiter_id": pl,
            "projekteinkäufer_id": pe,
        })
    return rows


# ---------------------------------------------------------------------------
# Einkaufspositionen
# ---------------------------------------------------------------------------

_LIEFERANTEN = [
    (200001, "Elektro Müller GmbH"),
    (200002, "Sanitär Technik AG"),
    (200003, "Baumarkt Nord GmbH"),
    (200004, "Heizung Klima Süd"),
    (200005, "Installateur Bauer KG"),
    (200006, "TechSupply GmbH"),
    (200007, "Rohstoff Handel GmbH"),
    (200008, "Profi Baustoffe AG"),
]

_TYPEN = ["Anfrage", "Bestellung", "Rechnung"]
_RABATTE = [0.0, 0.0, 0.0, 0.03, 0.05, 0.10, 0.15]


def _random_date(days_ago_min: int = 0, days_ago_max: int = 730) -> str:
    offset = random.randint(days_ago_min, days_ago_max)
    return (date.today() - timedelta(days=offset)).isoformat()


def _einkaufspositionen(projekte: list[dict], artikel: list[dict], gewerke: list[dict], n_belege: int = 150) -> list[dict]:
    rows = []
    for i in range(n_belege):
        belegnummer = 300001 + i
        typ = random.choice(_TYPEN)
        projekt = random.choice(projekte)
        lieferant_nr, lieferant_name = random.choice(_LIEFERANTEN)
        belegdatum = _random_date(0, 730)

        n_pos = random.randint(2, 8)
        for pos in range(1, n_pos + 1):
            art = random.choice(artikel)
            gew = random.choice(gewerke)
            menge = random.randint(1, 100)
            preis = round(random.uniform(1.50, 250.00), 2)
            rabatt = random.choice(_RABATTE)
            positionswert = round(menge * preis * (1 - rabatt), 2)
            rows.append({
                "belegnummer": belegnummer,
                "belegdatum": belegdatum,
                "typ": typ,
                "artikel_nr": art["nummer"],
                "gewerk_id": gew["gewerk_id"],
                "position": pos,
                "menge": menge,
                "preis": preis,
                "rabatt": rabatt,
                "positionswert": positionswert,
                "freitext": fake.sentence() if random.random() < 0.25 else "",
                "projekt_nr": projekt["projektnummer"],
                "lieferant_nr": lieferant_nr,
                "lieferant_name": lieferant_name,
            })
    return rows


# ---------------------------------------------------------------------------
# CSV-Writer
# ---------------------------------------------------------------------------

def _write_csv(rows: list[dict], filename: str) -> None:
    if not rows:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {path.name}: {len(rows)} Zeilen")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_all() -> None:
    print("Generiere Testdaten...")
    kontakte = _kontakte()
    gewerke = _gewerke()
    artikel = _artikel()
    projekte = _projekte(kontakte)
    positionen = _einkaufspositionen(projekte, artikel, gewerke)

    _write_csv(kontakte, "kontakte.csv")
    _write_csv(gewerke, "gewerke.csv")
    _write_csv(artikel, "artikel.csv")
    _write_csv(projekte, "projekte.csv")
    _write_csv(positionen, "einkaufspositionen.csv")
    print(f"Fertig! {len(positionen)} Positionen auf {len(projekte)} Projekte verteilt.")
