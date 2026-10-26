"""Klucz API zapisywany w aplikacji — bez połączenia z API."""
import os

from ozc import klucz_api


def test_zapis_odczyt_usuniecie(tmp_path, monkeypatch):
    monkeypatch.delenv(klucz_api.ZMIENNA, raising=False)
    plik = tmp_path / "Kalkulator OZC" / "klucz_api.txt"
    assert klucz_api.zapisany_klucz(plik) is None

    klucz_api.zapisz("  sk-ant-testowy-1234  ", plik)
    assert plik.read_text(encoding="utf-8") == "sk-ant-testowy-1234"
    assert os.environ[klucz_api.ZMIENNA] == "sk-ant-testowy-1234"

    monkeypatch.delenv(klucz_api.ZMIENNA)
    klucz_api.zastosuj_zapisany(plik)
    assert klucz_api.aktywny_klucz() == "sk-ant-testowy-1234"

    klucz_api.usun(plik)
    assert not plik.exists() and klucz_api.aktywny_klucz() is None


def test_zapisany_klucz_wygrywa_ze_zmienna(tmp_path, monkeypatch):
    monkeypatch.setenv(klucz_api.ZMIENNA, "sk-ant-ze-zmiennej")
    plik = tmp_path / "klucz.txt"
    plik.write_text("sk-ant-z-aplikacji", encoding="utf-8")
    klucz_api.zastosuj_zapisany(plik)
    assert klucz_api.aktywny_klucz() == "sk-ant-z-aplikacji"


def test_maskowanie():
    assert klucz_api.zamaskowany("sk-ant-api03-abcdefghijklmnop-WXYZ") == "sk-ant-…WXYZ"
    assert "sk-ant-api03" not in klucz_api.zamaskowany("sk-ant-api03-abcdefghijklmnop-WXYZ")
