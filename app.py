"""Aplikacja OZC: wrzuć audyty → sprawdź odczyt → policz → zapisz. Uruchom: uruchom.bat"""
from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import streamlit as st

from ozc import __version__, klucz_api
from ozc.ai_odczyt import MODEL, BladOdczytu, odczytaj_audyt
from ozc.dane import BladDanych, Dane, normalizuj, opcje_listy, uzupelnij_domyslne, wczytaj_xlsx
from ozc.konfiguracja import KATALOG_DANYCH
from ozc.obliczenia import oblicz
from ozc.pola import POLA, Pole, Sekcja
from ozc.raport import lista_adresow, zapisz_adres

KATALOG_ADRESOW = KATALOG_DANYCH / "adresy"
ZRODLO_CZLOWIEK = "uzupełnione przez człowieka"
NIEPEWNE = {"protokół – odczyt niepewny", "AI – do sprawdzenia", "założenie domyślne"}
OBRAZY = (".jpg", ".jpeg", ".png", ".webp")
ROWNOLEGLE_ODCZYTY = 4

st.set_page_config(page_title="Kalkulator OZC", page_icon="🔥", layout="wide")
ss = st.session_state
klucz_api.zastosuj_zapisany()


# ---------------------------------------------------------------------------
# Wczytanie audytów
# ---------------------------------------------------------------------------

def grupuj_pliki(pliki) -> list[tuple[str, list[tuple[str, bytes]]]]:
    """Każdy PDF i każdy Excel to osobny audyt; wszystkie zdjęcia razem to jeden audyt (strony protokołu)."""
    audyty, zdjecia = [], []
    for p in pliki:
        if p.name.lower().endswith(OBRAZY):
            zdjecia.append((p.name, p.getvalue()))
        else:
            audyty.append((p.name, [(p.name, p.getvalue())]))
    if zdjecia:
        audyty.append((f"{zdjecia[0][0]} (+{len(zdjecia) - 1} zdjęć)" if len(zdjecia) > 1 else zdjecia[0][0], zdjecia))
    return audyty


def odczytaj(nazwa: str, pliki: list[tuple[str, bytes]]) -> dict:
    """Odczyt jednego audytu — wywoływany w wątku, bez funkcji Streamlit."""
    audyt = {"nazwa": nazwa, "pliki": pliki, "dane": None, "pytania": [], "podsumowanie": "",
             "wynik": None, "blad": None, "zapisano": False}
    try:
        if nazwa.lower().endswith(".xlsx"):
            dane, problemy = normalizuj(wczytaj_xlsx(io.BytesIO(pliki[0][1])))
            audyt.update(dane=uzupelnij_domyslne(dane), pytania=problemy, pliki=[])
        else:
            w = odczytaj_audyt(pliki)
            audyt.update(dane=w.dane, pytania=w.pytania, podsumowanie=w.podsumowanie)
    except BladOdczytu as e:
        audyt["blad"] = f"Błąd odczytu: {e}"
    except Exception as e:  # noqa: BLE001 — jeden zły plik nie może zatrzymać całej partii
        audyt["blad"] = f"Nie udało się odczytać pliku: {e}"
    return audyt


def wczytaj_partie(pliki) -> None:
    grupy = grupuj_pliki(pliki)
    if any(not n.lower().endswith(".xlsx") for n, _ in grupy) and not klucz_api.aktywny_klucz():
        st.error("Brak klucza API — wpisz go w zakładce „Ustawienia”. Bez klucza można wczytać tylko pliki Excel.")
        return
    postep = st.progress(0.0, text=f"Claude czyta audyty: 0 z {len(grupy)} (każdy ok. 1–3 min)…")
    wyniki: list[dict | None] = [None] * len(grupy)
    with ThreadPoolExecutor(max_workers=ROWNOLEGLE_ODCZYTY) as pula:
        zadania = {pula.submit(odczytaj, n, p): i for i, (n, p) in enumerate(grupy)}
        for gotowe, z in enumerate(as_completed(zadania), start=1):
            wyniki[zadania[z]] = z.result()
            postep.progress(gotowe / len(grupy), text=f"Claude czyta audyty: {gotowe} z {len(grupy)}…")
    postep.empty()
    for a in wyniki:
        if a["dane"] is not None:
            policz(a)
    ss.audyty = wyniki
    ss.wersja = ss.get("wersja", 0) + 1


def policz(audyt: dict) -> None:
    dane, problemy = normalizuj(audyt["dane"])
    audyt["dane"], audyt["wynik"], audyt["blad"] = dane, None, None
    if problemy:
        audyt["blad"] = "Popraw dane: " + "; ".join(problemy)
        return
    try:
        audyt["wynik"] = oblicz(dane)
    except BladDanych as e:
        audyt["blad"] = "Brak danych: " + "; ".join(p.removeprefix("Brak danych: ") for p in e.problemy)


def status(a: dict) -> str:
    if a["zapisano"]:
        return "✅ zapisano"
    if a["blad"]:
        return "❌ " + ("błąd odczytu" if a["dane"] is None else "brak danych")
    n = len(a["wynik"].ostrzezenia)
    return f"⚠ {n} do sprawdzenia" if n else "✔ gotowe"


def zapisz(a: dict) -> None:
    zapisz_adres(KATALOG_ADRESOW, a["dane"], a["wynik"], a["pliki"], a["pytania"])
    a["zapisano"] = True


# ---------------------------------------------------------------------------
# Formularz sprawdzania
# ---------------------------------------------------------------------------

def tekst(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:g}".replace(".", ",")
    return str(v)


def formularz(dane: Dane, prefiks: str) -> Dane:
    """Pola do sprawdzenia, sekcjami. Zmieniona wartość dostaje źródło „uzupełnione przez człowieka”."""
    wynik = Dane(dict(dane.wartosci), dict(dane.zrodla), dict(dane.uwagi))
    sekcje: list[tuple[str, list[Pole]]] = []
    for p in POLA:
        if isinstance(p, Sekcja):
            sekcje.append((p.tytul, []))
        elif p.rodzaj != "calc":
            sekcje[-1][1].append(p)

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
                                        key=f"{prefiks}_{k}", label_visibility="collapsed")
                else:
                    nowa = c2.text_input(p.etykieta, value=tekst(dane.get(k)), key=f"{prefiks}_{k}",
                                         label_visibility="collapsed", help=p.podpowiedz or None)
                if dane.uwagi.get(k):
                    c3.caption(dane.uwagi[k])
                stara = tekst(dane.get(k)) if p.rodzaj != "list" else (dane.get(k) or "")
                if nowa != stara:
                    wynik.wartosci[k] = nowa or None
                    wynik.zrodla[k] = ZRODLO_CZLOWIEK
    return wynik


def sprawdzanie(a: dict, i: int) -> None:
    if a["dane"] is None:
        st.error(a["blad"])
        return
    if a["wynik"]:
        st.metric(f"OZC — {a['dane'].get('adres') or a['nazwa']}", f"{a['wynik'].phi_HL_kW:.2f} kW")
        if a["wynik"].ostrzezenia:
            st.warning("**Do sprawdzenia:**\n\n" + "\n".join(f"- {o}" for o in a["wynik"].ostrzezenia))
    elif a["blad"]:
        st.error(a["blad"])
    if a["podsumowanie"]:
        st.info(a["podsumowanie"])
    if a["pytania"]:
        st.warning("**Pytania do audytora / braki:**\n\n" + "\n".join(f"- {p}" for p in a["pytania"]))

    st.markdown("Pola z ⚠ są niepewne albo przyjęte domyślnie — zweryfikuj je i kliknij „Przelicz”.")
    poprawione = formularz(a["dane"], f"{ss.get('wersja', 0)}_{i}")
    c1, c2 = st.columns(2)
    if c1.button("🔄 Przelicz", key=f"przelicz_{i}"):
        a["dane"] = poprawione
        a["zapisano"] = False
        policz(a)
        st.rerun()
    if a["wynik"] and not a["zapisano"] and c2.button("💾 Zapisz ten adres", type="primary", key=f"zapisz_{i}"):
        zapisz(a)
        st.rerun()
    if a["zapisano"]:
        st.success("Zapisano — wynik jest w zakładce „Lista adresów”.")


# ---------------------------------------------------------------------------
# Strony
# ---------------------------------------------------------------------------

def strona_audyty() -> None:
    st.title("Audyty")
    st.markdown("**1.** Wrzuć audyty — **każdy PDF to osobny adres** (można wiele naraz). "
                "Zdjęcia stron jednego protokołu wrzuć razem w osobnej partii. Działa też wypełniony szablon Excel.")
    pliki = st.file_uploader("Pliki audytów", type=["pdf", "jpg", "jpeg", "png", "webp", "xlsx"],
                             accept_multiple_files=True, label_visibility="collapsed",
                             key=f"wgrane_{ss.get('wersja', 0)}")
    if pliki and st.button(f"📄 Odczytaj ({len(grupuj_pliki(pliki))})", type="primary"):
        wczytaj_partie(pliki)

    audyty = ss.get("audyty")
    if not audyty:
        return

    st.markdown("**2.** Wyniki odczytu. Otwórz audyt poniżej, żeby sprawdzić dane i zapisać.")
    tabela = pd.DataFrame([{
        "Plik": a["nazwa"],
        "Adres": a["dane"].get("adres") if a["dane"] else "—",
        "OZC [kW]": round(a["wynik"].phi_HL_kW, 2) if a["wynik"] else None,
        "Status": status(a),
    } for a in audyty])
    st.dataframe(tabela, hide_index=True, width="content")

    gotowe = [a for a in audyty if a["wynik"] and not a["wynik"].ostrzezenia and not a["zapisano"]]
    c1, c2 = st.columns(2)
    if gotowe and c1.button(f"💾 Zapisz wszystkie bez ostrzeżeń ({len(gotowe)})"):
        for a in gotowe:
            zapisz(a)
        st.rerun()
    if c2.button("🗑 Wyczyść i zacznij nową partię"):
        ss.pop("audyty", None)
        ss.wersja = ss.get("wersja", 0) + 1
        st.rerun()

    st.markdown("**3.** Sprawdź audyt.")
    etykiety = [f"{i + 1}. {a['nazwa']} — {status(a)}" for i, a in enumerate(audyty)]
    i = st.selectbox("Audyt", range(len(audyty)), format_func=lambda j: etykiety[j], label_visibility="collapsed")
    sprawdzanie(audyty[i], i)


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


def strona_ustawienia() -> None:
    st.title("Ustawienia")
    st.subheader("Klucz API Anthropic")
    aktywny = klucz_api.aktywny_klucz()
    if aktywny:
        st.success(f"Klucz jest ustawiony: `{klucz_api.zamaskowany(aktywny)}` — odczyt PDF przez AI działa.")
    else:
        st.warning("Brak klucza — odczyt PDF nie zadziała (pliki Excel tak).")

    with st.form("klucz", clear_on_submit=True):
        nowy = st.text_input("Nowy klucz", type="password", placeholder="sk-ant-...")
        if st.form_submit_button("Sprawdź i zapisz", type="primary") and nowy.strip():
            with st.spinner("Sprawdzam klucz…"):
                blad = klucz_api.sprawdz(nowy, MODEL)
            if blad:
                st.error(blad)
            else:
                klucz_api.zapisz(nowy)
                st.rerun()
    if klucz_api.zapisany_klucz() and st.button("Usuń zapisany klucz"):
        klucz_api.usun()
        st.rerun()
    st.caption(f"Klucz zapisuje się tylko na tym komputerze, w pliku {klucz_api.PLIK_KLUCZA}. "
               "Klucz wygenerujesz w konsoli Anthropic (platform.claude.com → API Keys).")

    st.subheader("Jak to działa")
    st.markdown("""
- AI odczytuje protokół i przy każdej wartości oznacza źródło: protokół / odczyt niepewny / do sprawdzenia.
  Czego nie ma w protokole, nie zgaduje — program wstawia założenie domyślne (oznaczone ⚠).
- Obliczenia: PN-EN 12831:2006 dla całego budynku; grunt wg PN-EN ISO 13370.
- Koszt odczytu: ok. 0,1–0,3 USD za protokół.
""")
    st.caption(f"Wersja {__version__} · wyniki zapisują się w {KATALOG_ADRESOW}")


strony = {"Audyty": strona_audyty, "Lista adresów": strona_lista, "Ustawienia": strona_ustawienia}
wybrana = st.sidebar.radio("Menu", list(strony))
if not klucz_api.aktywny_klucz():
    st.sidebar.warning("Brak klucza API — wpisz go w „Ustawieniach”.")
strony[wybrana]()
