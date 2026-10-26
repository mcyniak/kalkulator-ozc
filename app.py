"""Aplikacja OZC: wrzuć audyt → sprawdź odczyt → policz → zapisz. Uruchom: uruchom.bat"""
from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from ozc.ai_odczyt import BladOdczytu, odczytaj_audyt
from ozc.dane import BladDanych, Dane, normalizuj, opcje_listy, uzupelnij_domyslne, wczytaj_xlsx
from ozc import __version__
from ozc.konfiguracja import KATALOG_DANYCH
from ozc.obliczenia import oblicz
from ozc.pola import POLA, Pole, Sekcja
from ozc.raport import lista_adresow, raport_md, zapisz_adres

KATALOG_ADRESOW = KATALOG_DANYCH / "adresy"
ZRODLO_CZLOWIEK = "uzupełnione przez człowieka"
NIEPEWNE = {"protokół – odczyt niepewny", "AI – do sprawdzenia", "założenie domyślne"}

st.set_page_config(page_title="Kalkulator OZC", page_icon="🔥", layout="wide")
ss = st.session_state


# ---------------------------------------------------------------------------
# Wczytanie audytu
# ---------------------------------------------------------------------------

def wczytaj(pliki) -> None:
    excele = [p for p in pliki if p.name.lower().endswith(".xlsx")]
    try:
        if excele:
            dane, problemy = normalizuj(wczytaj_xlsx(io.BytesIO(excele[0].getvalue())))
            ss.odczyt = {"dane": uzupelnij_domyslne(dane), "pytania": problemy,
                         "podsumowanie": f"Wczytano z pliku {excele[0].name}.", "pliki": []}
        else:
            surowe = [(p.name, p.getvalue()) for p in pliki]
            with st.spinner("Claude czyta protokół… zwykle 1–3 minuty."):
                wynik = odczytaj_audyt(surowe)
            ss.odczyt = {"dane": wynik.dane, "pytania": wynik.pytania,
                         "podsumowanie": wynik.podsumowanie, "pliki": surowe}
    except BladOdczytu as e:
        st.error(str(e))
        return
    ss.wersja = ss.get("wersja", 0) + 1
    ss.pop("wynik", None)
    ss.pop("zapisano", None)


def tekst(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:g}".replace(".", ",")
    return str(v)


def formularz(dane: Dane) -> Dane:
    """Pola do sprawdzenia, sekcjami. Zmieniona wartość dostaje źródło „uzupełnione przez człowieka”."""
    wynik = Dane(dict(dane.wartosci), dict(dane.zrodla), dict(dane.uwagi))
    sekcje: list[tuple[str, list[Pole]]] = []
    for p in POLA:
        if isinstance(p, Sekcja):
            sekcje.append((p.tytul, []))
        elif p.rodzaj != "calc":
            sekcje[-1][1].append(p)

    w = ss.get("wersja", 0)
    for tytul, pola in sekcje:
        niepewnych = sum(1 for p in pola if dane.zrodla.get(p.klucz) in NIEPEWNE and dane.get(p.klucz) is not None)
        naglowek = tytul + (f"  —  ⚠ {niepewnych} do sprawdzenia" if niepewnych else "")
        with st.expander(naglowek, expanded=bool(niepewnych)):
            for p in pola:
                k = p.klucz
                zrodlo = dane.zrodla.get(k, "")
                c1, c2, c3 = st.columns([3, 2, 4])
                znak = "⚠ " if zrodlo in NIEPEWNE and dane.get(k) is not None else ""
                c1.markdown(f"{znak}**{p.etykieta}**" + (f" [{p.jednostka}]" if p.jednostka else ""))
                if zrodlo:
                    c1.caption(zrodlo)
                if p.rodzaj == "list":
                    opcje = [""] + opcje_listy(p)
                    obecna = dane.get(k)
                    nowa = c2.selectbox(p.etykieta, opcje, index=opcje.index(obecna) if obecna in opcje else 0,
                                        key=f"{w}_{k}", label_visibility="collapsed")
                else:
                    nowa = c2.text_input(p.etykieta, value=tekst(dane.get(k)), key=f"{w}_{k}",
                                         label_visibility="collapsed", help=p.podpowiedz or None)
                if dane.uwagi.get(k):
                    c3.caption(dane.uwagi[k])
                stara = tekst(dane.get(k)) if p.rodzaj != "list" else (dane.get(k) or "")
                if nowa != stara:
                    wynik.wartosci[k] = nowa or None
                    wynik.zrodla[k] = ZRODLO_CZLOWIEK
    return wynik


# ---------------------------------------------------------------------------
# Wynik
# ---------------------------------------------------------------------------

def pokaz_wynik(dane: Dane, w, pytania: list[str]) -> None:
    st.divider()
    st.metric(f"OZC — {dane.get('adres') or 'adres'}", f"{w.phi_HL_kW:.2f} kW")
    if w.ostrzezenia:
        st.warning("**Do sprawdzenia przed zapisem:**\n\n" + "\n".join(f"- {o}" for o in w.ostrzezenia))
    if st.button("💾 Zapisz do listy adresów", type="primary"):
        zapisz_adres(KATALOG_ADRESOW, dane, w, ss.odczyt.get("pliki", []), pytania)
        ss.zapisano = True
    if ss.get("zapisano"):
        st.success("Zapisano — wynik jest w zakładce „Lista adresów”.")


# ---------------------------------------------------------------------------
# Strony
# ---------------------------------------------------------------------------

def strona_nowy_audyt() -> None:
    st.title("Nowy audyt")
    st.markdown("**1.** Wrzuć skan protokołu (PDF lub zdjęcia stron) albo wypełniony szablon Excel.")
    pliki = st.file_uploader("Pliki audytu", type=["pdf", "jpg", "jpeg", "png", "webp", "xlsx"],
                             accept_multiple_files=True, label_visibility="collapsed")
    if pliki and st.button("📄 Odczytaj audyt", type="primary"):
        jest_excel = any(p.name.lower().endswith(".xlsx") for p in pliki)
        if not jest_excel and not os.environ.get("ANTHROPIC_API_KEY"):
            st.error("Brak klucza API (zmienna ANTHROPIC_API_KEY) — patrz zakładka „Pomoc”. "
                     "Bez klucza można wczytać tylko wypełniony szablon Excel.")
        else:
            wczytaj(pliki)

    if "odczyt" not in ss:
        return
    odczyt = ss.odczyt
    st.markdown("**2.** Sprawdź odczyt. Pola z ⚠ są niepewne albo przyjęte domyślnie — zweryfikuj je.")
    if odczyt["podsumowanie"]:
        st.info(odczyt["podsumowanie"])
    if odczyt["pytania"]:
        st.warning("**Pytania do audytora / braki:**\n\n" + "\n".join(f"- {p}" for p in odczyt["pytania"]))

    dane_formularz = formularz(odczyt["dane"])

    st.markdown("**3.** Policz OZC.")
    if st.button("🔥 Oblicz OZC", type="primary"):
        dane, problemy = normalizuj(dane_formularz)
        if problemy:
            st.error("Popraw dane:\n\n" + "\n".join(f"- {p}" for p in problemy))
            ss.pop("wynik", None)
        else:
            try:
                ss.wynik = (dane, oblicz(dane))
                ss.pop("zapisano", None)
            except BladDanych as e:
                st.error("Nie można policzyć — uzupełnij:\n\n" + "\n".join(f"- {p}" for p in e.problemy))
                ss.pop("wynik", None)
    if "wynik" in ss:
        pokaz_wynik(*ss.wynik, odczyt["pytania"])


def strona_lista() -> None:
    st.title("Lista adresów")
    adresy = lista_adresow(KATALOG_ADRESOW)
    if not adresy:
        st.info("Nie zapisano jeszcze żadnego adresu.")
        return
    tabela = pd.DataFrame([{"Adres": a.get("adres"), "OZC [kW]": a.get("phi_HL_kW")} for a in adresy])
    st.dataframe(tabela, hide_index=True, width="content")

    bufor = io.BytesIO()
    tabela.to_excel(bufor, index=False)
    st.download_button("Pobierz tabelę (.xlsx)", bufor.getvalue(), file_name="OZC_adresy.xlsx")


def strona_pomoc() -> None:
    st.title("Pomoc")
    if os.environ.get("ANTHROPIC_API_KEY"):
        st.success("Klucz API jest ustawiony — odczyt PDF przez AI działa.")
    else:
        st.error("Brak klucza API. Odczyt PDF przez AI nie zadziała (Excel tak).")
    st.markdown("""
**Jak ustawić klucz API (jednorazowo):**
1. Wygeneruj klucz na https://platform.claude.com (Settings → API Keys).
2. Otwórz „Wiersz polecenia” (cmd) i wpisz: `setx ANTHROPIC_API_KEY "sk-ant-..."`
3. Zamknij to okno i uruchom aplikację ponownie (`uruchom.bat`).

**Jak to działa:**
- AI odczytuje protokół i oznacza przy każdej wartości źródło: protokół / odczyt niepewny / do sprawdzenia.
  Czego nie ma w protokole, nie zgaduje — program wstawia założenie domyślne (oznaczone).
- Obliczenia: PN-EN 12831:2006 dla całego budynku; grunt wg PN-EN ISO 13370.
  Wszystkie wartości normowe i biblioteka przegród są w pliku `konfiguracja.toml`.
- Każdy zapisany adres to folder w `adresy/` z plikami: `dane.xlsx`, `raport.md`, `wynik.json` i oryginałem audytu.

**Koszt odczytu:** ok. 0,1–0,3 USD za protokół (model Claude Opus 5.5).
""")


strony = {"Nowy audyt": strona_nowy_audyt, "Lista adresów": strona_lista, "Pomoc": strona_pomoc}
wybrana = st.sidebar.radio("Menu", list(strony))
st.sidebar.caption(f"Wersja {__version__}\n\nWyniki: {KATALOG_ADRESOW}")
strony[wybrana]()
