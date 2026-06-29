"""LLM-Schnittstelle: Ollama-Chat mit Session-Kontext."""
import re

import ollama
import pandas as pd

from .schema import get_system_prompt

_INTERPRET_SYSTEM = (
    "Du bist ein freundlicher Assistent in einer Projekteinkaufsabteilung. "
    "Du bekommst eine Nutzerfrage und das Ergebnis einer Datenbankabfrage. "
    "Fasse das Ergebnis in 2-3 knappen deutschen Saetzen zusammen. "
    "Nenne konkrete Zahlen und Namen aus den Daten. "
    "Kein Markdown, keine Aufzaehlung, keine Formatierung — nur Fliestext."
)


def _df_to_text(df: pd.DataFrame, max_rows: int = 12) -> str:
    """Kompakte Textdarstellung eines DataFrame fuer den LLM-Kontext."""
    n = len(df)
    lines = [f"{n} Zeile(n), Spalten: {', '.join(df.columns)}"]

    # Datentabelle (begrenzt)
    preview = df.head(max_rows)
    lines.append(preview.to_string(index=False))

    if n > max_rows:
        lines.append(f"... ({n - max_rows} weitere Zeilen nicht gezeigt)")

    # Numerische Kennzahlen bei groesseren Ergebnissen
    num_cols = df.select_dtypes(include="number").columns.tolist()
    if num_cols and n > 1:
        stats = df[num_cols].agg(["sum", "mean", "min", "max"]).round(2)
        lines.append(f"\nStatistik:\n{stats.to_string()}")

    return "\n".join(lines)

DEFAULT_MODEL = "qwen2.5-coder:7b"


def _strip_fences(text: str) -> str:
    """Entfernt Markdown-Codeblöcke und imitierte Ergebnis-Blöcke aus der LLM-Antwort."""
    text = text.strip()
    # Markdown-Codeblöcke entfernen
    text = re.sub(r"^```(?:sql)?\s*\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text)
    # LLM imitiert manchmal den von feed_result angehängten [SYSTEM-ERGEBNIS]-Block.
    # Alles ab diesem Marker abschneiden — es ist kein gültiges SQL.
    text = re.sub(r"\n\n\[SYSTEM-ERGEBNIS.*", "", text, flags=re.DOTALL)
    return text.strip()


class ChatSession:
    """Hält den Gesprächsverlauf für Follow-up-Fragen."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        profiles: list[dict] | None = None,
        value_inventories: list[dict] | None = None,
        # Legacy-Parameter für Demo-Daten ohne DB-Verbindung
        kontakte: list[str] | None = None,
        lieferanten: list[str] | None = None,
    ) -> None:
        self.model = model
        self._profiles = profiles
        self._value_inventories = value_inventories
        self._kontakte = kontakte
        self._lieferanten = lieferanten
        self._messages: list[dict] = [
            {"role": "system", "content": get_system_prompt(
                kontakte, lieferanten, profiles, value_inventories
            )}
        ]

    def ask(self, question: str) -> str:
        """Schickt eine Frage ans LLM, gibt das generierte SQL zurück."""
        self._messages.append({"role": "user", "content": question})
        response = ollama.chat(model=self.model, messages=self._messages)
        raw = response.message.content
        sql = _strip_fences(raw)
        # Speichere das bereinigte SQL im Verlauf, damit Follow-ups Kontext haben
        self._messages.append({"role": "assistant", "content": sql})
        return sql

    def feed_result(self, df: pd.DataFrame, max_rows: int = 5) -> None:
        """Haengt das Abfrageergebnis an die letzte SQL-Antwort im Verlauf an.

        Dadurch weiss das Modell bei Folgefragen, welche konkreten Werte
        (Projektnummern, Namen, Datumswerte …) die vorherige Abfrage geliefert hat.
        """
        if df is None or df.empty:
            return
        if not self._messages or self._messages[-1]["role"] != "assistant":
            return
        n = len(df)
        cols = ", ".join(df.columns)
        preview = df.head(max_rows).to_string(index=False)
        snippet = f"[SYSTEM-ERGEBNIS: {n} Zeile(n), Spalten: {cols}]\n{preview}"
        if n > max_rows:
            snippet += f"\n... ({n - max_rows} weitere Zeilen nicht gezeigt)"
        self._messages[-1]["content"] += f"\n\n{snippet}"

    def interpret(self, question: str, sql: str, df: pd.DataFrame) -> str:
        """Zweiter Pass: Ergebnis-DataFrame -> kurzer Freitext.
        Voellig zustandslos — benutzt NICHT self._messages."""
        data_text = _df_to_text(df)
        messages = [
            {"role": "system", "content": _INTERPRET_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Frage: {question}\n\n"
                    f"Ergebnis:\n{data_text}"
                ),
            },
        ]
        response = ollama.chat(model=self.model, messages=messages)
        return response.message.content.strip()

    def reset(self) -> None:
        self._messages = [{"role": "system", "content": get_system_prompt(
            self._kontakte, self._lieferanten, self._profiles, self._value_inventories
        )}]

    @property
    def turn_count(self) -> int:
        """Anzahl der Nutzer-Turns (ohne System-Prompt)."""
        return sum(1 for m in self._messages if m["role"] == "user")
