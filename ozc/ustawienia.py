"""Ustawienia użytkownika (np. folder na raporty) — plik JSON w %LOCALAPPDATA%\\Kalkulator OZC."""
from __future__ import annotations

import json
import os
from pathlib import Path

PLIK_USTAWIEN = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Kalkulator OZC" / "ustawienia.json"


def wczytaj(plik: Path | None = None) -> dict:
    try:
        return json.loads((plik or PLIK_USTAWIEN).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def ustaw(klucz: str, wartosc, plik: Path | None = None) -> None:
    plik = plik or PLIK_USTAWIEN
    dane = wczytaj(plik)
    if wartosc in (None, ""):
        dane.pop(klucz, None)
    else:
        dane[klucz] = wartosc
    plik.parent.mkdir(parents=True, exist_ok=True)
    plik.write_text(json.dumps(dane, ensure_ascii=False, indent=2), encoding="utf-8")


def folder_raportow() -> Path | None:
    """Dodatkowy folder, do którego kopiowane są raporty OZC (np. na Dysku współdzielonym)."""
    sciezka = wczytaj().get("folder_raportow")
    return Path(sciezka) if sciezka else None
