"""Testdaten-Generator: erzeugt CSV-Dateien fuer alle Entitaeten."""
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
    return [
        {
            "kontakt_id": i,
            "name": fake.name(),
            "email": fake.email(),
            "telefon": fake.phone_number(),
        }
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# Gewerke
# ---------------------------------------------------------------------------

_GEWERK_NAMES = [
    "Elektro", "Sanitaer", "Heizung", "Lueftung",
    "Tiefbau", "Hochbau", "Maler", "Schreiner",
    "Metall", "Dachdecker",
]

def _gewerke() -> list[dict]:
    return [{"gewerk_id": i + 1, "name": n} for i, n in enumerate(_GEWERK_NAMES)]


# ---------------------------------------------------------------------------
# Artikel
# ---------------------------------------------------------------------------

_ARTIKEL_POOL = {
    "Kabel":       ["NYM-J 3x1.5", "NYM-J 5x2.5", "H07V-K 1x6", "LSZH 2x0.75",
                    "Erdkabel NYY-J 3x4", "Steuerleitung LiYCY 4x0.75"],
    "Rohr":        ["HT-Rohr DN50", "HT-Rohr DN100", "Kupferrohr 15mm", "Kupferrohr 22mm",
                    "PP-Rohr 20mm", "Edelstahlrohr 28mm"],
    "Fitting":     ["T-Stueck 15mm", "Winkel 90 22mm", "Muffe DN50", "Reduktion 22/15mm",
                    "Kupplung 20mm", "Doppelnippel DN25"],
    "Schalter":    ["Taster 16A", "Schalter IP44", "Lichtschalter 2-polig", "Steckdose UP",
                    "FI-Schutzschalter 40A", "Leitungsschutz B16"],
    "Armatur":     ["Kugelhahn DN25", "Absperrventil DN15", "Rueckschlagventil DN20",
                    "Thermostatventil", "Regulierventil DN32"],
    "Daemmung":    ["AF/Armaflex 13mm", "Steinwolle 50mm", "Glaswolle 80mm",
                    "PIR-Platte 40mm", "PE-Schaum 6mm"],
    "Befestigung": ["Rohrschelle DN50", "Gewindestange M10", "Duebel 8mm",
                    "Schraube M6x20", "Winkelkonsole 60mm", "Kabelschelle 25mm"],
}

_GRUPPE_PREFIX = {
    "Kabel": "KBL", "Rohr": "RHR", "Fitting": "FTG",
    "Schalter": "SCH", "Armatur": "ARM", "Daemmung": "DAE", "Befestigung": "BFG",
}

def _suchwort(gruppe: str, name: str, idx: int) -> str:
    prefix = _GRUPPE_PREFIX.get(gruppe, "ART")
    word = "".join(p.capitalize() for p in name.replace("-", " ").replace("/", " ").split())
    return f"{prefix}{word}{idx:03d}"

def _artikel() -> list[dict]:
    rows, idx = [], 0
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

_STAEDTE = ["Muenchen", "Berlin", "Hamburg", "Koeln", "Frankfurt",
            "Stuttgart", "Duesseldorf", "Nuernberg", "Bremen"]
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
# Einkaufspositionen — verkettet: Anfrage -> Bestellung -> Rechnung
# ---------------------------------------------------------------------------

_LIEFERANTEN = [
    (200001, "Elektro Mueller GmbH"),
    (200002, "Sanitaer Technik AG"),
    (200003, "Baumarkt Nord GmbH"),
    (200004, "Heizung Klima Sued"),
    (200005, "Installateur Bauer KG"),
    (200006, "TechSupply GmbH"),
    (200007, "Rohstoff Handel GmbH"),
    (200008, "Profi Baustoffe AG"),
]

_RABATTE = [0.0, 0.0, 0.0, 0.03, 0.05, 0.10, 0.15]

TODAY = date.today()


def _row(bn, belegdatum, typ, referenz_bn, liefertermin,
         pos_d, projekt_nr, lieferant, freitext="") -> dict:
    """Baut eine vollstaendige Positionszeile zusammen."""
    return {
        "belegnummer": bn,
        "belegdatum": belegdatum.isoformat() if isinstance(belegdatum, date) else belegdatum,
        "typ": typ,
        "referenz_belegnummer": referenz_bn if referenz_bn is not None else "",
        "liefertermin": liefertermin.isoformat() if isinstance(liefertermin, date) else (liefertermin or ""),
        "artikel_nr": pos_d["artikel_nr"],
        "gewerk_id": pos_d["gewerk_id"],
        "position": pos_d["position"],
        "menge": pos_d["menge"],
        "preis": pos_d["preis"],
        "rabatt": pos_d["rabatt"],
        "positionswert": pos_d["positionswert"],
        "freitext": freitext,
        "projekt_nr": projekt_nr,
        "lieferant_nr": lieferant[0],
        "lieferant_name": lieferant[1],
    }


def _vary_price(base_preis: float, pct: float) -> float:
    """Preisvariation um +/- pct (z.B. 0.07 = 7%)."""
    return round(base_preis * random.uniform(1 - pct, 1 + pct), 2)


def _pos_wert(menge, preis, rabatt) -> float:
    return round(menge * preis * (1 - rabatt), 2)


def _einkaufspositionen(
    projekte: list[dict],
    artikel: list[dict],
    gewerke: list[dict],
    n_anfragen: int = 50,
) -> list[dict]:
    """
    Erzeugt verkettete Belege:
      Anfrage (100%)
        -> Bestellung (70%, +/-7% Preis, mit Liefertermin)
             -> Rechnung (65% der faelligen, +/-2% Preis)
    """
    all_rows: list[dict] = []
    belegnum = 300001

    # ------------------------------------------------------------------ #
    # Phase 1: Anfragen                                                   #
    # ------------------------------------------------------------------ #
    anfragen_meta = []

    for _ in range(n_anfragen):
        bn = belegnum; belegnum += 1
        projekt = random.choice(projekte)
        lieferant = random.choice(_LIEFERANTEN)
        af_date = TODAY - timedelta(days=random.randint(60, 540))
        n_pos = random.randint(2, 6)

        pos_list = []
        for pos in range(1, n_pos + 1):
            art = random.choice(artikel)
            gew = random.choice(gewerke)
            menge = random.randint(1, 100)
            preis = round(random.uniform(1.50, 250.00), 2)
            rabatt = random.choice(_RABATTE)
            pd = {
                "artikel_nr": art["nummer"], "gewerk_id": gew["gewerk_id"],
                "position": pos, "menge": menge, "preis": preis,
                "rabatt": rabatt, "positionswert": _pos_wert(menge, preis, rabatt),
            }
            pos_list.append(pd)
            all_rows.append(_row(
                bn, af_date, "Anfrage", None, None,
                pd, projekt["projektnummer"], lieferant,
                freitext=fake.sentence() if random.random() < 0.2 else "",
            ))

        anfragen_meta.append({
            "bn": bn, "date": af_date,
            "projekt_nr": projekt["projektnummer"],
            "lieferant": lieferant,
            "positions": pos_list,
        })

    # ------------------------------------------------------------------ #
    # Phase 2: Bestellungen (70 % der Anfragen)                          #
    # ------------------------------------------------------------------ #
    bestellungen_meta = []
    for_bestellung = random.sample(anfragen_meta, int(len(anfragen_meta) * 0.70))

    for af in for_bestellung:
        bn = belegnum; belegnum += 1
        order_date = af["date"] + timedelta(days=random.randint(3, 21))
        if order_date >= TODAY:
            order_date = TODAY - timedelta(days=1)

        liefertermin = order_date + timedelta(days=random.randint(14, 70))

        best_positions = []
        for ref in af["positions"]:
            preis = _vary_price(ref["preis"], 0.07)
            rabatt = random.choice(_RABATTE)
            menge = ref["menge"]
            pd = {
                "artikel_nr": ref["artikel_nr"], "gewerk_id": ref["gewerk_id"],
                "position": ref["position"], "menge": menge, "preis": preis,
                "rabatt": rabatt, "positionswert": _pos_wert(menge, preis, rabatt),
            }
            best_positions.append(pd)
            all_rows.append(_row(
                bn, order_date, "Bestellung", af["bn"], liefertermin,
                pd, af["projekt_nr"], af["lieferant"],
            ))

        bestellungen_meta.append({
            "bn": bn, "order_date": order_date, "liefertermin": liefertermin,
            "projekt_nr": af["projekt_nr"],
            "lieferant": af["lieferant"],
            "positions": best_positions,
        })

    # ------------------------------------------------------------------ #
    # Phase 3: Rechnungen (65 % der Bestellungen mit vergangenem          #
    #          Liefertermin)                                               #
    # ------------------------------------------------------------------ #
    faellig = [b for b in bestellungen_meta if b["liefertermin"] < TODAY]
    for_rechnung = random.sample(faellig, int(len(faellig) * 0.65))

    for best in for_rechnung:
        bn = belegnum; belegnum += 1
        rechnung_date = best["liefertermin"] + timedelta(days=random.randint(0, 14))
        if rechnung_date >= TODAY:
            rechnung_date = TODAY - timedelta(days=1)

        for ref in best["positions"]:
            preis = _vary_price(ref["preis"], 0.02)
            rabatt = ref["rabatt"]   # Rechnung uebernimmt Rabatt der Bestellung
            menge = ref["menge"]
            pd = {
                "artikel_nr": ref["artikel_nr"], "gewerk_id": ref["gewerk_id"],
                "position": ref["position"], "menge": menge, "preis": preis,
                "rabatt": rabatt, "positionswert": _pos_wert(menge, preis, rabatt),
            }
            all_rows.append(_row(
                bn, rechnung_date, "Rechnung", best["bn"], None,
                pd, best["projekt_nr"], best["lieferant"],
            ))

    # Statistik ausgeben
    n_af = sum(1 for r in all_rows if r["typ"] == "Anfrage" and r["position"] == 1)
    n_be = sum(1 for r in all_rows if r["typ"] == "Bestellung" and r["position"] == 1)
    n_re = sum(1 for r in all_rows if r["typ"] == "Rechnung" and r["position"] == 1)
    n_ueb = sum(1 for b in bestellungen_meta
                if b["liefertermin"] < TODAY
                and b["bn"] not in {b2["bn"] for b2 in for_rechnung})
    print(f"  Anfragen: {n_af}  |  Bestellungen: {n_be}  |  Rechnungen: {n_re}  |  Ueberfaellig: {n_ueb}")

    return all_rows


# ---------------------------------------------------------------------------
# CSV-Writer  (None -> leer, damit DuckDB nullstr='' greift)
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
    gewerke  = _gewerke()
    artikel  = _artikel()
    projekte = _projekte(kontakte)
    positionen = _einkaufspositionen(projekte, artikel, gewerke)

    _write_csv(kontakte,   "kontakte.csv")
    _write_csv(gewerke,    "gewerke.csv")
    _write_csv(artikel,    "artikel.csv")
    _write_csv(projekte,   "projekte.csv")
    _write_csv(positionen, "einkaufspositionen.csv")
    print(f"Fertig! {len(positionen)} Positionen gesamt.")
