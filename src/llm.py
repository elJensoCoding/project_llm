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
    """Entfernt Markdown-Codeblöcke falls das Modell sie trotzdem liefert."""
    text = text.strip()
    # Remove ```sql ... ``` or ``` ... ```
    text = re.sub(r"^```(?:sql)?\s*\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


class ChatSession:
    """Hält den Gesprächsverlauf für Follow-up-Fragen."""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self._messages: list[dict] = [
            {"role": "system", "content": get_system_prompt()}
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
        self._messages = [{"role": "system", "content": get_system_prompt()}]

    @property
    def turn_count(self) -> int:
        """Anzahl der Nutzer-Turns (ohne System-Prompt)."""
        return sum(1 for m in self._messages if m["role"] == "user")
