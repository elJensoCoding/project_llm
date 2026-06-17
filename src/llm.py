"""LLM-Schnittstelle: Ollama-Chat mit Session-Kontext."""
import re

import ollama

from .schema import get_system_prompt

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

    def reset(self) -> None:
        self._messages = [{"role": "system", "content": get_system_prompt()}]

    @property
    def turn_count(self) -> int:
        """Anzahl der Nutzer-Turns (ohne System-Prompt)."""
        return sum(1 for m in self._messages if m["role"] == "user")
