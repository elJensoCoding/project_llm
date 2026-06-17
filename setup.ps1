# Setup-Script für Windows PowerShell
# Ausführen mit: .\setup.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=== Projekt-LLM Setup ===" -ForegroundColor Cyan

# Virtualenv anlegen
if (-not (Test-Path ".venv")) {
    Write-Host "Erstelle .venv..." -ForegroundColor Yellow
    python -m venv .venv
}

# Aktivieren
& .\.venv\Scripts\Activate.ps1

# Abhängigkeiten installieren
Write-Host "Installiere Abhängigkeiten..." -ForegroundColor Yellow
pip install -e .

# Datagen
Write-Host "Generiere Testdaten..." -ForegroundColor Yellow
python cli.py init

Write-Host ""
Write-Host "=== Setup abgeschlossen ===" -ForegroundColor Green
Write-Host "Starte Chat mit:  python cli.py chat" -ForegroundColor Cyan
Write-Host "Oder direkt:      python src/app.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "Empfohlene Modelle (falls noch nicht vorhanden):" -ForegroundColor Yellow
Write-Host "  ollama pull qwen2.5-coder:7b" -ForegroundColor Cyan
Write-Host "  ollama pull gemma3" -ForegroundColor Cyan
