"""Punkt startowy wersji .exe: uruchamia aplikację Streamlit lokalnie i otwiera przeglądarkę."""
import socket
import sys
import threading
import webbrowser
from pathlib import Path

# app.py jest uruchamiany przez Streamlit z pliku, więc PyInstaller nie widzi jego importów — wskazujemy je tutaj.
import anthropic  # noqa: F401
import openpyxl  # noqa: F401
import pandas  # noqa: F401

import ozc.ai_odczyt  # noqa: F401
import ozc.obliczenia  # noqa: F401
import ozc.raport  # noqa: F401
from streamlit.web import cli


def wolny_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def main() -> None:
    katalog = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    port = wolny_port()
    adres = f"http://localhost:{port}"
    # Konsola Windows źle wyświetla polskie znaki — komunikat bez nich.
    print(f"Kalkulator OZC dziala pod adresem {adres}\nZamknij to okno, aby zakonczyc program.\n")
    threading.Timer(3, webbrowser.open, [adres]).start()
    # headless=true: bez pytania o e-mail przy pierwszym uruchomieniu; przeglądarkę otwieramy sami.
    sys.argv = ["streamlit", "run", str(katalog / "app.py"), f"--server.port={port}",
                "--server.address=localhost", "--server.headless=true",
                "--browser.gatherUsageStats=false", "--global.developmentMode=false",
                "--client.toolbarMode=viewer"]
    sys.exit(cli.main())


if __name__ == "__main__":
    main()
