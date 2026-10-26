"""Punkt startowy wersji .exe: uruchamia aplikację Streamlit lokalnie i otwiera przeglądarkę.

Zawsze ten sam adres (http://localhost:8599): ponowne uruchomienie nie stawia drugiego serwera,
tylko otwiera działający. Wersja .exe nie ma okna konsoli — komunikaty trafiają do pliku log.txt.
"""
import os
import socket
import sys
import threading
import tomllib
import traceback
import urllib.request
import webbrowser
from pathlib import Path

# app.py jest uruchamiany przez Streamlit z pliku, więc PyInstaller nie widzi jego importów — wskazujemy je tutaj.
import anthropic  # noqa: F401
import openpyxl  # noqa: F401
import pandas  # noqa: F401

import ozc.ai_odczyt  # noqa: F401
import ozc.obliczenia  # noqa: F401
import ozc.podglad  # noqa: F401
import ozc.raport  # noqa: F401
import ozc.raport_word  # noqa: F401
from streamlit.web import cli

PORT = int(os.environ.get("OZC_PORT", 8599))


def opcje_wygladu(katalog: Path) -> list[str]:
    """Ustawienia z .streamlit/config.toml jako flagi — exe nie startuje z katalogu projektu, więc sam plik nie wystarczy."""
    plik = katalog / ".streamlit" / "config.toml"
    if not plik.exists():
        return []
    flagi = []

    def dodaj(prefiks: str, sekcja: dict) -> None:
        for k, v in sekcja.items():
            if isinstance(v, dict):
                dodaj(f"{prefiks}.{k}", v)
            else:
                flagi.append(f"--{prefiks}.{k}={str(v).lower() if isinstance(v, bool) else v}")

    for nazwa, sekcja in tomllib.loads(plik.read_text(encoding="utf-8")).items():
        dodaj(nazwa, sekcja)
    return flagi
KATALOG_LOGU = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Kalkulator OZC"


def juz_dziala(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/_stcore/health", timeout=2) as odp:
            return odp.read().strip() == b"ok"
    except OSError:
        return False


def port_wolny(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("localhost", port))
        except OSError:
            return False
    return True


def wolny_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def autotest(katalog: Path) -> None:
    """Wykonuje app.py bez serwera i przeglądarki — wyłapuje brakujące moduły w spakowanym .exe."""
    import runpy
    runpy.run_path(str(katalog / "app.py"), run_name="__main__")
    from ozc.raport_word import utworz_docx  # noqa: F401 — szablon python-docx i matplotlib w paczce
    print("AUTOTEST OK")


def main() -> None:
    katalog = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    if sys.stdout is None:  # .exe bez okna konsoli — komunikaty do pliku
        KATALOG_LOGU.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(KATALOG_LOGU / "log.txt", "a", encoding="utf-8", buffering=1)

    if "--autotest" in sys.argv:
        try:
            autotest(katalog)
        except BaseException:
            traceback.print_exc()
            sys.exit(1)
        sys.exit(0)

    if juz_dziala(PORT):
        webbrowser.open(f"http://localhost:{PORT}")
        return
    port = PORT if port_wolny(PORT) else wolny_port()
    adres = f"http://localhost:{port}"
    print(f"Kalkulator OZC dziala pod adresem {adres}")
    threading.Timer(3, webbrowser.open, [adres]).start()
    # headless=true: bez pytania o e-mail przy pierwszym uruchomieniu; przeglądarkę otwieramy sami.
    sys.argv = ["streamlit", "run", str(katalog / "app.py"), f"--server.port={port}",
                "--server.address=localhost", "--server.headless=true",
                "--browser.gatherUsageStats=false", "--global.developmentMode=false",
                "--client.toolbarMode=viewer", *opcje_wygladu(katalog)]
    sys.exit(cli.main())


if __name__ == "__main__":
    main()
