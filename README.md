# Kalkulator OZC

Projektowe obciążenie cieplne całego budynku (PN-EN 12831:2006) do doboru pompy ciepła,
liczone na podstawie protokołu audytu.

## Instalacja (bez uprawnień administratora)
Pobierz `Kalkulator-OZC-vX.Y.Z.zip` z zakładki **Releases**, rozpakuj i uruchom `Kalkulator OZC.exe`.
Wyniki zapisują się w `Dokumenty\Kalkulator OZC` — nowa wersja programu ich nie kasuje.

Dla programisty: dwuklik `uruchom.bat` (Python 3.11+, środowisko tworzy się samo).
Nowe wydanie .exe: `git tag v0.2.0 && git push origin v0.2.0` — GitHub zbuduje ZIP automatycznie.

Komputerowe audyty FlexiPower (PDF z tekstem) program czyta sam — bez AI i bez klucza.
Skany i zdjęcia protokołów odręcznych czyta AI, co wymaga klucza API Anthropic — wpisz go raz w zakładce
**Ustawienia** (zapisuje się lokalnie w `%LOCALAPPDATA%\Kalkulator OZC`, nigdy w kodzie ani repozytorium).

## Praca z audytami
1. **Audyty** → przeciągnij PDF-y (każdy PDF = osobny adres, można wiele naraz) → „Odczytaj”.
   Działają wszystkie formaty: komputerowe audyty FlexiPower, skany protokołów odręcznych (stare i nowe wersje
   formularza, z tabelą okien na elewacjach) i wypełniony `szablony/szablon_OZC.xlsx`. Zdjęcia stron jednego
   protokołu wrzuca się razem w osobnej partii. Skan bez klucza API nie blokuje reszty partii.
2. Tabela pokazuje OZC i status każdego audytu, program od razu otwiera pierwszy do sprawdzenia. Sekcja
   **Do uzupełnienia / Do potwierdzenia** pokazuje tylko pola, których nie udało się odczytać albo które są
   szacunkiem — z wycinkiem audytu w tym miejscu. Ostrzeżenia (np. ściana bez ocieplenia, nietypowe W/m²,
   wynik niezgodny ze zużyciem paliwa) wskazują audyty, w których zwykle jest błąd danych.
3. Wpisz lub popraw wartości i kliknij **„Zatwierdź i zapisz raport”** — program liczy OZC, tworzy raport
   w Wordzie i PDF (`OZC_<adres>_<data>_<godzina>`, układ FlexiPower Group; PDF tworzy zainstalowany Word)
   i przechodzi do następnego audytu. „Zapisz wszystkie gotowe” zapisuje naraz audyty bez braków i ostrzeżeń.
4. **Lista adresów** — Adres | OZC [kW] | Word | PDF; eksport do Excela z linkami do raportów.
   W **Ustawieniach** można wskazać dodatkowy folder na raporty (np. na Dysku współdzielonym).

## Pliki
- `konfiguracja.toml` — wszystkie wartości normowe, biblioteka przegród, założenia domyślne (ze źródłami).
  Po zmianie uruchom `python generuj_szablon.py`, żeby odświeżyć szablon Excel.
- `ozc/` — kalkulator (geometria, przegrody, grunt, obliczenia), odczyt AI, raporty.
- `testy/` — testy: `.venv\Scripts\python.exe -m pytest`
