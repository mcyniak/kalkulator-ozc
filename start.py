"""Punkt startowy wersji .exe: uruchamia aplikację Streamlit lokalnie i otwiera przeglądarkę.

Zawsze ten sam adres (http://localhost:8599): ponowne uruchomienie nie stawia drugiego serwera,
tylko otwiera działający. Przeglądarka otwiera się dopiero, gdy serwer odpowiada — do tego czasu
widać okienko startowe. Wersja .exe nie ma okna konsoli — komunikaty trafiają do pliku log.txt.
"""
import ctypes
import os
import socket
import sys
import threading
import time
import tomllib
import traceback
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

try:
    import pyi_splash  # okienko startowe .exe (PyInstaller) — od razu widać, że program się uruchamia
except ImportError:
    pyi_splash = None

PORT = int(os.environ.get("OZC_PORT", 8599))
CZAS_STARTU = 180            # [s] po tylu sekundach bez odpowiedzi serwera pokazujemy komunikat
NAZWA_MUTEXU = "Local\\KalkulatorOZC"
_BEZ_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # firmowe proxy nie może łapać localhost


def _moduly_dla_pyinstallera() -> None:  # pragma: no cover — nigdy nie wywoływana
    """app.py jest uruchamiany przez Streamlit z pliku, więc PyInstaller nie widzi jego importów — wskazujemy je tutaj.
    W funkcji, a nie na górze pliku: ciężkie biblioteki ładują się dopiero, gdy są potrzebne (szybszy start)."""
    import anthropic  # noqa: F401
    import openpyxl  # noqa: F401
    import pandas  # noqa: F401

    import ozc.ai_odczyt  # noqa: F401
    import ozc.obliczenia  # noqa: F401
    import ozc.podglad  # noqa: F401
    import ozc.raport  # noqa: F401
    import ozc.raport_word  # noqa: F401


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
PLIK_PORTU = KATALOG_LOGU / "port.txt"


def splash(tekst: str | None = None) -> None:
    """Zmienia napis okienka startowego albo je zamyka (tekst=None). Bez okienka (np. uruchom.bat) nic nie robi."""
    if pyi_splash is None:
        return
    try:
        if tekst:
            pyi_splash.update_text(tekst)
        else:
            pyi_splash.close()
    except Exception:  # noqa: BLE001 — okienko jest tylko informacją, nie może zatrzymać startu
        pass


def log(tekst: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {tekst}", flush=True)


def juz_dziala(port: int) -> bool:
    try:
        with _BEZ_PROXY.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=2) as odp:
            return odp.read().strip() == b"ok"
    except OSError:
        return False


def czekaj_na_serwer(port: int, limit: float = CZAS_STARTU) -> bool:
    koniec = time.monotonic() + limit
    while time.monotonic() < koniec:
        if juz_dziala(port):
            return True
        time.sleep(0.3)
    return False


def komunikat(tekst: str) -> None:
    splash()
    log(tekst)
    try:
        ctypes.windll.user32.MessageBoxW(None, tekst, "Kalkulator OZC", 0x30)
    except Exception:  # noqa: BLE001 — poza Windows wystarczy wpis w logu
        pass


_mutex = None


def pierwsza_kopia() -> bool:
    """Czy żadna inna kopia programu nie działa ani się nie uruchamia (nazwany mutex Windows znika z procesem)."""
    global _mutex
    try:
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, NAZWA_MUTEXU)
        return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS
    except Exception:  # noqa: BLE001
        return True


def port_dzialajacej_kopii() -> int:
    try:
        return int(PLIK_PORTU.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return PORT


def otworz_gdy_gotowy(port: int) -> None:
    """Otwiera przeglądarkę dopiero, gdy serwer odpowiada (wcześniej byłaby strona „nie można połączyć”)."""
    if czekaj_na_serwer(port):
        log(f"Serwer gotowy — otwieram http://localhost:{port}")
        webbrowser.open(f"http://localhost:{port}")
        splash()
    else:
        komunikat(f"Program nie uruchomił się w ciągu {CZAS_STARTU // 60} minut.\n\n"
                  "Zamknij go (Menedżer zadań → Kalkulator OZC) i spróbuj ponownie. "
                  f"Szczegóły są w pliku:\n{KATALOG_LOGU / 'log.txt'}")


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

    if not pierwsza_kopia():  # druga kopia (np. drugie kliknięcie w trakcie startu) — nie stawiamy drugiego serwera
        log("Program już działa albo się uruchamia — czekam na niego")
        splash("Program już się uruchamia — za chwilę otworzy się okno…")
        otworz_gdy_gotowy(port_dzialajacej_kopii())
        return
    if juz_dziala(PORT):  # starsza wersja bez blokady pierwszej kopii
        webbrowser.open(f"http://localhost:{PORT}")
        splash()
        return
    port = PORT if port_wolny(PORT) else wolny_port()
    try:
        KATALOG_LOGU.mkdir(parents=True, exist_ok=True)
        PLIK_PORTU.write_text(str(port), encoding="utf-8")
    except OSError:
        pass
    log(f"Kalkulator OZC uruchamia się pod adresem http://localhost:{port}")
    splash("Uruchamiam program… (pierwszy start po instalacji może potrwać do minuty)")
    threading.Thread(target=otworz_gdy_gotowy, args=(port,), daemon=True).start()
    from streamlit.web import cli
    # headless=true: bez pytania o e-mail przy pierwszym uruchomieniu; przeglądarkę otwieramy sami.
    # fileWatcherType=none: bez śledzenia zmian tysięcy plików paczki (zbędne i spowalnia).
    sys.argv = ["streamlit", "run", str(katalog / "app.py"), f"--server.port={port}",
                "--server.address=localhost", "--server.headless=true",
                "--browser.gatherUsageStats=false", "--global.developmentMode=false",
                "--server.fileWatcherType=none", "--server.runOnSave=false",
                "--client.toolbarMode=viewer", *opcje_wygladu(katalog)]
    sys.exit(cli.main())


if __name__ == "__main__":
    main()
