"""Generuje szablon danych wejściowych OZC (.xlsx) z pliku konfiguracja.toml.

Użycie:
    python generuj_szablon.py                      -> szablony/szablon_OZC.xlsx (pusty)
    python generuj_szablon.py przyklady/X.toml     -> przyklady/X.xlsx (wypełniony)

Każde pole wejściowe ma w Excelu nazwę zdefiniowaną (np. h_parter), po której
kalkulator czyta dane — układ wierszy można więc zmieniać bez psucia odczytu.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from ozc.szablon import zbuduj_skoroszyt

KATALOG = Path(__file__).parent


def generuj(przyklad_sciezka: Path | None) -> Path:
    if przyklad_sciezka:
        dane = tomllib.loads(przyklad_sciezka.read_text(encoding="utf-8"))
        wyjscie = przyklad_sciezka.with_suffix(".xlsx")
    else:
        dane = None
        wyjscie = KATALOG / "szablony" / "szablon_OZC.xlsx"
    wyjscie.parent.mkdir(exist_ok=True)
    zbuduj_skoroszyt(dane).save(wyjscie)
    return wyjscie


if __name__ == "__main__":
    sciezka = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print(generuj(sciezka))
