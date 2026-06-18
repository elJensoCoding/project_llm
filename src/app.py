"""NiceGUI Chat-Frontend fuer die Projekt-Datenbank."""
import asyncio
import os
import sys
from pathlib import Path

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
    "Alle Projekte anzeigen",
    "Bestellungen fuer Projekt 10001",
    "Top 5 Lieferanten nach Volumen",
    "Rechnungen nach Monat gruppiert",
    "Gesamtwert pro Gewerk und Belegtyp",
    "Welcher Projektleiter betreut die meisten Projekte?",
    "Durchschnittlicher Rabatt pro Lieferant",
    "Artikel in der Gruppe Kabel",
    "Offene Anfragen ohne Bestellung",
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
# Hilfs-Funktionen
# ---------------------------------------------------------------------------
_PAGE_SIZE = 20
_GRID_HEIGHT_PX = 420   # feste Hoehe — layout bricht nicht mehr auf


def _result_table(df, container) -> None:
    """Volle Breite, feste Hoehe, Pagination — stabil bei beliebig vielen Zeilen."""
    cols = [
        {
            "field": c,
            "headerName": c,
            "sortable": True,
            "filter": True,
            "resizable": True,
            "minWidth": 100,
        }
        for c in df.columns
    ]
    rows = df.fillna("").astype(str).to_dict("records")
    use_pagination = len(rows) > _PAGE_SIZE
    with container:
        grid_opts = {
            "columnDefs": cols,
            "rowData": rows,
            "onGridReady": "p => p.api.sizeColumnsToFit()",
            "onGridSizeChanged": "p => p.api.sizeColumnsToFit()",
        }
        if use_pagination:
            grid_opts["pagination"] = True
            grid_opts["paginationPageSize"] = _PAGE_SIZE
        (
            ui.aggrid(grid_opts)
            .classes("w-full")
            .style(f"height: {_GRID_HEIGHT_PX}px")
        )
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
