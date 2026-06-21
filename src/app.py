"""NiceGUI Chat-Frontend fuer die Projekt-Datenbank."""
import asyncio
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from nicegui import Client, ui

from src.db import execute as db_execute
from src.llm import DEFAULT_MODEL, ChatSession

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
MODELS = [
    "qwen2.5-coder:7b",
    "qwen3:4b",
    "gemma3",
    "llama3.1:8b",
    "phi4",
    "codellama:7b",
]

EXAMPLES = [
    "Bestellvolumen nach Monat",
    "Top 5 Lieferanten nach Volumen",
    "Gesamtwert pro Gewerk und Belegtyp",
    "Durchschnittlicher Bestellwert pro Monat",
    "Rechnungen nach Monat gruppiert",
    "Alle Projekte anzeigen",
    "Ueberfaellige Bestellungen",
    "Welcher Projektleiter betreut die meisten Projekte?",
    "Durchschnittlicher Rabatt pro Lieferant",
]


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
class _State:
    def __init__(self):
        self.model: str = os.environ.get("PLLM_MODEL", DEFAULT_MODEL)
        self.session: ChatSession = ChatSession(model=self.model)
        self.lock: asyncio.Lock = asyncio.Lock()

    def swap_model(self, model: str) -> None:
        self.model = model
        self.session = ChatSession(model=model)

    def reset(self) -> None:
        self.session.reset()


_state = _State()


# ---------------------------------------------------------------------------
# Chart-Erkennung
# ---------------------------------------------------------------------------
_TIME_KEYWORDS = {"monat", "datum", "date", "jahr", "quartal", "tag", "woche", "month"}
_ID_SUFFIXES   = ("_id", "_nr", "nummer", "_key")
_ID_EXACT      = {"id", "nr", "nummer", "position"}


def _is_id_col(col: str) -> bool:
    """True wenn die Spalte wie ein Schlüssel/Zähler aussieht, kein Messwert."""
    lower = col.lower()
    return lower in _ID_EXACT or any(lower.endswith(s) for s in _ID_SUFFIXES)


def _build_chart_options(df: pd.DataFrame | None) -> dict | None:
    """Heuristik: gibt ECharts-Options zurück oder None wenn kein Chart passt."""
    if df is None or len(df) < 2:
        return None

    all_num    = df.select_dtypes(include="number").columns.tolist()
    id_cols    = [c for c in all_num if _is_id_col(c)]
    metric_cols = [c for c in all_num if not _is_id_col(c)]

    # Ohne echte Messwerte kein Chart
    if not metric_cols:
        return None

    # Kategorisch: Text-Spalten + ID-artige Zahlen (gut als X-Achse, nicht als Y)
    cat_cols = [c for c in df.columns if c not in all_num] + id_cols
    if not cat_cols:
        return None

    x_col = cat_cols[0]
    y_cols = metric_cols[:3]

    is_time = any(kw in x_col.lower() for kw in _TIME_KEYWORDS)

    # X-Achsenbeschriftung: Timestamps auf "Jun 2024" kuerzen
    try:
        x_labels = pd.to_datetime(df[x_col], format="mixed").dt.strftime("%b %Y").tolist()
    except Exception:
        x_labels = df[x_col].astype(str).str[:20].tolist()

    def _safe_vals(col):
        return [round(float(v), 2) if pd.notna(v) else 0 for v in df[col]]

    # Donut: wenige Kategorien, eine Kennzahl, kein Zeitbezug
    if not is_time and len(df) <= 7 and len(y_cols) == 1:
        data = [{"name": n, "value": v}
                for n, v in zip(x_labels, _safe_vals(y_cols[0]))]
        return {
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
            "legend": {"type": "scroll", "orient": "vertical",
                       "right": "5%", "top": "middle"},
            "series": [{
                "type": "pie",
                "radius": ["38%", "65%"],
                "center": ["40%", "50%"],
                "data": data,
                "label": {"formatter": "{b}\n{d}%"},
                "emphasis": {"itemStyle": {"shadowBlur": 10}},
            }],
        }

    # Linie (Zeitreihe) oder Balken (Kategorien)
    chart_type = "line" if is_time else "bar"
    series = []
    for y_col in y_cols:
        s = {"name": y_col, "type": chart_type,
             "data": _safe_vals(y_col), "smooth": True}
        if is_time and len(y_cols) == 1:
            s["areaStyle"] = {"opacity": 0.25}
        series.append(s)

    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": y_cols} if len(y_cols) > 1 else {},
        "grid": {"left": "3%", "right": "4%", "bottom": "18%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": x_labels,
            "axisLabel": {"rotate": 30 if len(x_labels) > 5 else 0},
        },
        "yAxis": {"type": "value"},
        "series": series,
    }


# ---------------------------------------------------------------------------
# Tabellen-Rendering
# ---------------------------------------------------------------------------
_PAGE_SIZE = 20
_GRID_HEIGHT_PX = 350   # etwas kleiner wenn Chart darueber steht


def _result_table(df: pd.DataFrame, container) -> None:
    """Chart (wenn erkennbar) + Tabelle, beide volle Breite."""
    chart_opts = _build_chart_options(df)
    cols = [
        {"field": c, "headerName": c, "sortable": True,
         "filter": True, "resizable": True, "minWidth": 100}
        for c in df.columns
    ]
    rows = df.fillna("").astype(str).to_dict("records")
    use_pagination = len(rows) > _PAGE_SIZE
    grid_opts = {
        "columnDefs": cols,
        "rowData": rows,
        "onGridReady": "p => p.api.sizeColumnsToFit()",
        "onGridSizeChanged": "p => p.api.sizeColumnsToFit()",
    }
    if use_pagination:
        grid_opts["pagination"] = True
        grid_opts["paginationPageSize"] = _PAGE_SIZE

    with container:
        if chart_opts:
            ui.echart(chart_opts).classes("w-full").style("height: 380px")
            ui.separator().classes("my-2")
        ui.aggrid(grid_opts).classes("w-full").style(f"height: {_GRID_HEIGHT_PX}px")
        ui.label(f"{len(df):,} Zeile(n)  |  {len(df.columns)} Spalte(n)").classes(
            "text-xs text-gray-400 mt-1"
        )


# ---------------------------------------------------------------------------
# Seite
# ---------------------------------------------------------------------------
@ui.page("/")
def index(client: Client) -> None:

    async def send(question: str) -> None:
        question = question.strip()
        if not question:
            return

        txt_input.value = ""
        txt_input.disable()
        btn_send.disable()

        # Nutzernachricht (Bubble, rechts) — eigener Block in chat_area
        with chat_area:
            with ui.chat_message(name="Du", sent=True):
                ui.label(question).classes("whitespace-pre-wrap")

        # Pro Turn einen Container: Bubble + Ergebnis darin zusammengefasst.
        # Dadurch bleibt die Reihenfolge stabil unabhaengig von der
        # dynamischen Hoehe des Aggrids.
        with chat_area:
            turn = ui.column().classes("w-full gap-1")

        with turn:
            with ui.chat_message(name="Assistent"):
                msg_col = ui.column().classes("w-full gap-1")
            # Ergebnis-Platzhalter als echte Zeile im selben Container
            result_area = ui.column().classes("w-full")

        with msg_col:
            status = ui.label("SQL wird generiert ...").classes(
                "text-gray-400 italic text-sm"
            )

        # LLM im Thread-Pool
        try:
            async with _state.lock:
                sql = await asyncio.to_thread(_state.session.ask, question)
        except Exception as exc:
            status.delete()
            with msg_col:
                ui.label(f"LLM-Fehler: {exc}").classes("text-red-500 text-sm")
                ui.label("Laeuft Ollama? -> ollama serve").classes("text-gray-400 text-xs")
            _unlock()
            return

        status.set_text("SQL wird ausgefuehrt ...")
        df, error = await asyncio.to_thread(db_execute, sql)
        status.delete()

        has_data = not error and df is not None and not df.empty

        # Ergebnis in den Konversationsverlauf einpflegen — nur so weiss das
        # Modell bei Folgefragen, welche konkreten Werte zurueckkamen.
        if has_data:
            async with _state.lock:
                await asyncio.to_thread(_state.session.feed_result, df)

        # Bubble: erst Interpretation-Placeholder, darunter SQL-Klappe.
        # Tabelle erscheint sofort; Interpretationstext laeuft danach nach.
        with msg_col:
            if has_data:
                interp_label = (
                    ui.label("Zusammenfassung wird erstellt ...")
                    .classes("text-gray-400 italic text-sm animate-pulse")
                )
            with ui.expansion("SQL", icon="code").classes("w-full"):
                ui.code(sql, language="sql").classes("w-full text-sm overflow-auto").style("max-height: 200px")

        with result_area:
            if error:
                ui.label(f"Fehler: {error}").classes("text-red-500 text-sm")
            elif not has_data:
                ui.label("Keine Ergebnisse.").classes("text-gray-400 text-sm italic")
            else:
                _result_table(df, result_area)

        # Zweiter LLM-Call: Freitext-Zusammenfassung (nur wenn Daten vorhanden)
        if has_data:
            try:
                interpretation = await asyncio.to_thread(
                    _state.session.interpret, question, sql, df
                )
            except Exception:
                interpretation = None

            if interpretation:
                interp_label.set_text(interpretation)
                interp_label.classes(
                    remove="text-gray-400 italic text-sm animate-pulse",
                    add="text-slate-800 text-sm",
                )
            else:
                interp_label.delete()

        await client.run_javascript(
            "window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})"
        )
        _unlock()

    def _unlock() -> None:
        txt_input.enable()
        btn_send.enable()
        txt_input.run_method("focus")

    def on_model_change(e) -> None:
        _state.swap_model(e.value)
        ui.notify(f"Modell: {e.value}", type="positive", position="top-right", timeout=2000)

    def on_reset() -> None:
        _state.reset()
        chat_area.clear()
        with chat_area:
            _welcome_message()
        ui.notify("Konversation zurueckgesetzt", position="top-right", timeout=2000)

    def on_example(q: str) -> None:
        txt_input.value = q
        ui.timer(0.05, lambda: asyncio.ensure_future(send(q)), once=True)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    with ui.header().classes("bg-slate-800 text-white px-6 py-2 items-center gap-4"):
        ui.label("Projekt-DB Assistent").classes("text-lg font-bold flex-1")
        ui.select(
            MODELS,
            value=_state.model,
            on_change=on_model_change,
        ).classes("w-56").props('outlined dense dark label="Modell"')

    with ui.left_drawer(fixed=True, elevated=True).classes(
        "bg-slate-50 flex flex-col gap-1 p-4"
    ):
        ui.label("Beispielfragen").classes("font-semibold text-slate-600 text-sm mb-1")
        for ex in EXAMPLES:
            (
                ui.button(ex, on_click=lambda _, q=ex: on_example(q))
                .props("flat align=left no-caps")
                .classes("w-full text-left text-slate-700 text-sm px-2")
            )
        ui.separator().classes("my-2")
        (
            ui.button("Neue Konversation", icon="refresh", on_click=on_reset)
            .props("flat color=negative no-caps")
            .classes("w-full")
        )

    # Scrollbarer Hauptbereich — breiter als vorher (max-w-5xl statt 3xl)
    with ui.column().classes("w-full max-w-5xl mx-auto px-6 pt-6 pb-32 gap-3"):
        chat_area = ui.column().classes("w-full gap-2")
        with chat_area:
            _welcome_message()

    # Fixierter Eingabebereich
    with ui.footer().classes("bg-white border-t border-gray-200 shadow-md px-6 py-3"):
        with ui.row().classes("w-full max-w-5xl mx-auto gap-2 items-center"):
            txt_input = (
                ui.input(placeholder="Deine Frage zur Projektdatenbank ...")
                .classes("flex-1")
                .props("outlined dense clearable")
            )
            txt_input.on(
                "keydown.enter",
                lambda: asyncio.ensure_future(send(txt_input.value)),
            )
            btn_send = (
                ui.button(
                    "Senden",
                    icon="send",
                    on_click=lambda: asyncio.ensure_future(send(txt_input.value)),
                )
                .props("color=primary no-caps")
            )

    txt_input.run_method("focus")


def _welcome_message() -> None:
    with ui.chat_message(name="Assistent"):
        ui.markdown(
            "Hallo! Stell mir Fragen zur Projektdatenbank - "
            "ich generiere das SQL und zeige die Ergebnisse direkt an.\n\n"
            "Follow-up-Fragen funktionieren: erst *Bestellungen fuer Projekt 10001*, "
            "dann *gruppiere nach Monat*."
        )


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------
def run(port: int = 8080, model: str | None = None) -> None:
    if model:
        _state.swap_model(model)
    ui.run(
        host="127.0.0.1",
        port=port,
        title="Projekt-DB Assistent",
        reload=False,
        show=True,
    )


if __name__ == "__main__":
    run()
