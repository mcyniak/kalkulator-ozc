# Kalkulator OZC

Projektowe obciążenie cieplne całego budynku (PN-EN 12831:2006) do doboru pompy ciepła,
liczone na podstawie protokołu audytu.

## Instalacja (bez uprawnień administratora)
Pobierz `Kalkulator-OZC-vX.Y.Z.zip` z zakładki **Releases**, rozpakuj i uruchom `Kalkulator OZC.exe`.
Wyniki zapisują się w `Dokumenty\Kalkulator OZC` — nowa wersja programu ich nie kasuje.

Dla programisty: dwuklik `uruchom.bat` (Python 3.11+, środowisko tworzy się samo).
Nowe wydanie .exe: `git tag v0.2.0 && git push origin v0.2.0` — GitHub zbuduje ZIP automatycznie.

Odczyt PDF przez AI wymaga klucza API Anthropic — wpisz go raz w zakładce **Ustawienia**
(zapisuje się lokalnie w `%LOCALAPPDATA%\Kalkulator OZC`, nigdy w kodzie ani repozytorium).

## Praca z audytami
1. **Audyty** → przeciągnij PDF-y (każdy PDF = osobny adres, można wiele naraz) → „Odczytaj”.
   Zdjęcia stron jednego protokołu wrzuca się razem w osobnej partii. Działa też wypełniony `szablony/szablon_OZC.xlsx`.
2. Tabela pokazuje OZC i status każdego audytu. Otwórz audyt: sekcja **Do uzupełnienia / Do potwierdzenia**
   pokazuje tylko pola, których AI nie odczytało albo nie było pewne — z wycinkiem skanu w tym miejscu.
   Wpisz lub popraw wartości i kliknij „Przelicz i potwierdź”.
3. „Zapisz adres i utwórz raport” (albo „Zapisz wszystkie gotowe”) — powstaje raport OZC w Wordzie i PDF
   (`OZC_<adres>_<data>_<godzina>`) w układzie FlexiPower Group. PDF tworzy zainstalowany Word.
4. **Lista adresów** — Adres | OZC [kW] | Word | PDF; eksport do Excela z linkami do raportów.
   W **Ustawieniach** można wskazać dodatkowy folder na raporty (np. na Dysku współdzielonym).

## Pliki
- `konfiguracja.toml` — wszystkie wartości normowe, biblioteka przegród, założenia domyślne (ze źródłami).
  Po zmianie uruchom `python generuj_szablon.py`, żeby odświeżyć szablon Excel.
- `ozc/` — kalkulator (geometria, przegrody, grunt, obliczenia), odczyt AI, raporty.
- `testy/` — testy: `.venv\Scripts\python.exe -m pytest`
