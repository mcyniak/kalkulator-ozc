"""Wczytanie pliku konfiguracja.toml (jedno źródło wartości normowych i biblioteki)."""
from __future__ import annotations

import os
import sys
import tomllib
from functools import cache
from pathlib import Path

KATALOG_PROJEKTU = Path(__file__).resolve().parent.parent
PLIK_KONFIGURACJI = KATALOG_PROJEKTU / "konfiguracja.toml"

# Wersja .exe (PyInstaller) trzyma wyniki w Dokumentach, żeby aktualizacja programu ich nie skasowała.
if os.environ.get("OZC_DANE"):
    KATALOG_DANYCH = Path(os.environ["OZC_DANE"])
elif getattr(sys, "frozen", False):
    KATALOG_DANYCH = Path.home() / "Documents" / "Kalkulator OZC"
else:
    KATALOG_DANYCH = KATALOG_PROJEKTU


@cache
def wczytaj_konfiguracje(sciezka: Path = PLIK_KONFIGURACJI) -> dict:
    return tomllib.loads(sciezka.read_text(encoding="utf-8"))
