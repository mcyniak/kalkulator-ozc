"""Klucz API Anthropic wpisywany w aplikacji — zapisywany lokalnie u użytkownika, nigdy w kodzie.

Plik leży w %LOCALAPPDATA%\\Kalkulator OZC (nie w Dokumentach, które bywają synchronizowane z OneDrive).
Klucz zapisany w aplikacji ma pierwszeństwo przed zmienną środowiskową ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import os
from pathlib import Path

ZMIENNA = "ANTHROPIC_API_KEY"
PLIK_KLUCZA = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Kalkulator OZC" / "klucz_api.txt"


def zapisany_klucz(plik: Path | None = None) -> str | None:
    try:
        klucz = (plik or PLIK_KLUCZA).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return klucz or None


def zastosuj_zapisany(plik: Path | None = None) -> None:
    """Ustawia zapisany klucz dla bieżącego procesu (SDK czyta go ze zmiennej środowiskowej)."""
    klucz = zapisany_klucz(plik)
    if klucz:
        os.environ[ZMIENNA] = klucz


def zapisz(klucz: str, plik: Path | None = None) -> None:
    plik = plik or PLIK_KLUCZA
    plik.parent.mkdir(parents=True, exist_ok=True)
    plik.write_text(klucz.strip(), encoding="utf-8")
    os.environ[ZMIENNA] = klucz.strip()


def usun(plik: Path | None = None) -> None:
    (plik or PLIK_KLUCZA).unlink(missing_ok=True)
    os.environ.pop(ZMIENNA, None)


def aktywny_klucz() -> str | None:
    return os.environ.get(ZMIENNA) or None


def zamaskowany(klucz: str) -> str:
    return f"{klucz[:7]}…{klucz[-4:]}" if len(klucz) > 12 else "…"


def sprawdz(klucz: str, model: str) -> str | None:
    """Sprawdza klucz bezpłatnym zapytaniem o model. Zwraca komunikat błędu albo None, gdy działa."""
    import anthropic  # ciężka biblioteka — tylko przy sprawdzaniu klucza
    try:
        anthropic.Anthropic(api_key=klucz.strip(), max_retries=0, timeout=20).models.retrieve(model)
    except anthropic.AuthenticationError:
        return "Klucz jest nieprawidłowy albo został unieważniony."
    except anthropic.PermissionDeniedError:
        return "Klucz nie ma dostępu do modelu — sprawdź uprawnienia w konsoli Anthropic."
    except anthropic.APIConnectionError:
        return "Brak połączenia z API — sprawdź internet."
    except anthropic.APIStatusError as e:
        return f"API zwróciło błąd {e.status_code} — spróbuj później."
    return None
