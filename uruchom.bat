@echo off
REM Uruchamia kalkulator OZC w przegladarce. Zamknij to okno, aby zakonczyc.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Pierwsze uruchomienie - instaluje potrzebne pakiety, to potrwa kilka minut...
    python -m venv .venv || goto :blad
    ".venv\Scripts\python.exe" -m pip install -q -r wymagania.txt || goto :blad
)
".venv\Scripts\python.exe" -m streamlit run app.py --server.address localhost --server.headless false --browser.gatherUsageStats false --client.toolbarMode viewer
goto :eof

:blad
echo.
echo Nie udalo sie przygotowac srodowiska. Sprawdz, czy Python 3.11+ jest zainstalowany.
pause
