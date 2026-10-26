# Kalkulator OZC

Projektowe obciążenie cieplne całego budynku (PN-EN 12831:2006) do doboru pompy ciepła,
liczone na podstawie protokołu audytu.

## Instalacja (bez uprawnień administratora)
Pobierz `Kalkulator-OZC-vX.Y.Z.zip` z zakładki **Releases**, rozpakuj i uruchom `Kalkulator OZC.exe`.
Wyniki zapisują się w `Dokumenty\Kalkulator OZC` — nowa wersja programu ich nie kasuje.

Dla programisty: dwuklik `uruchom.bat` (Python 3.11+, środowisko tworzy się samo).
Nowe wydanie .exe: `git tag v0.2.0 && git push origin v0.2.0` — GitHub zbuduje ZIP automatycznie.

Odczyt PDF przez AI wymaga klucza API Anthropic w zmiennej środowiskowej (jednorazowo, w cmd):
`setx ANTHROPIC_API_KEY "sk-ant-..."`, potem ponowne uruchomienie aplikacji.

## Praca z audytem
1. **Nowy audyt** → przeciągnij PDF/zdjęcia protokołu (lub wypełniony `szablony/szablon_OZC.xlsx`) → „Odczytaj audyt”.
2. Sprawdź pola z ⚠ i pytania do audytora; popraw wartości.
3. „Oblicz OZC” → „Zapisz adres”. Wynik trafia do `adresy/<nr>_<adres>/` (dane.xlsx, raport.md, wynik.json, oryginał).
4. **Lista adresów** — zestawienie wszystkich wyników, eksport do Excela.

## Pliki
- `konfiguracja.toml` — wszystkie wartości normowe, biblioteka przegród, założenia domyślne (ze źródłami).
  Po zmianie uruchom `python generuj_szablon.py`, żeby odświeżyć szablon Excel.
- `ozc/` — kalkulator (geometria, przegrody, grunt, obliczenia), odczyt AI, raporty.
- `testy/` — testy: `.venv\Scripts\python.exe -m pytest`
