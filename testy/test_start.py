"""Uruchamianie programu (start.py): szybki start i otwieranie przeglądarki dopiero, gdy serwer odpowiada."""
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import start
from ozc.konfiguracja import KATALOG_PROJEKTU


def test_start_nie_laduje_ciezkich_bibliotek():
    """Ciężkie biblioteki ładowane przed serwerem wydłużały start nawet o kilkadziesiąt sekund."""
    kod = ("import sys, start; print(','.join(m for m in ('anthropic', 'matplotlib', 'pandas', 'docx', "
           "'streamlit') if m in sys.modules))")
    wynik = subprocess.run([sys.executable, "-c", kod], cwd=KATALOG_PROJEKTU, capture_output=True, text=True,
                           check=True)
    assert wynik.stdout.strip() == ""


def _wolny_port() -> int:
    return start.wolny_port()


def test_brak_serwera_to_brak_odpowiedzi():
    assert start.czekaj_na_serwer(_wolny_port(), limit=0.5) is False


def test_dzialajacy_serwer_jest_wykrywany():
    class Zdrowie(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    serwer = HTTPServer(("127.0.0.1", 0), Zdrowie)
    threading.Thread(target=serwer.serve_forever, daemon=True).start()
    try:
        assert start.czekaj_na_serwer(serwer.server_address[1], limit=5) is True
    finally:
        serwer.shutdown()
