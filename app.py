"""Aplikacja OZC: wrzuć audyty → uzupełnij to, czego AI nie odczytało → policz → raport Word/PDF. Uruchom: uruchom.bat"""
from __future__ import annotations

import hashlib
import io
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import streamlit as st
from openpyxl import Workbook
from openpyxl.styles import Font

from ozc import __version__, klucz_api, ustawienia
from ozc.ai_odczyt import MODEL, BladOdczytu, Pytanie, odczytaj_audyt
from ozc.import_flexipower import importuj, rozpoznaj
from ozc.dane import BladDanych, Dane, Miejsce, normalizuj, opcje_listy, uzupelnij_domyslne, wczytaj_xlsx
from ozc.konfiguracja import KATALOG_DANYCH, wczytaj_konfiguracje
from ozc.obliczenia import etykieta_z_sekcja, oblicz, pola_do_uzupelnienia, zalozenia_kluczowe
from ozc.podglad import jedna_strona, liczba_stron, wycinek
from ozc.pola import POLA, POLA_WEJSCIOWE, Pole, Sekcja
from ozc.raport import lista_adresow, raport_dla_folderu, zapisz_adres

KATALOG_ADRESOW = KATALOG_DANYCH / "adresy"
ZRODLO_CZLOWIEK = "uzupełnione przez człowieka"
NIEPEWNE_AI = {"protokół – odczyt niepewny", "AI – do sprawdzenia", "wyliczone z audytu"}
NIEPEWNE = NIEPEWNE_AI | {"założenie domyślne"}
OBRAZY = (".jpg", ".jpeg", ".png", ".webp")
ROWNOLEGLE_ODCZYTY = 4
BRAK_KLUCZA = ("Skan wymaga odczytu przez AI, a nie ma klucza API — wpisz go w zakładce „Ustawienia” "
               "i wrzuć ten plik ponownie.")

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


def komputerowy(nazwa: str, pliki: list[tuple[str, bytes]]) -> bool:
    """Komputerowy audyt FlexiPower (PDF z warstwą tekstu) — czytany wprost, bez AI."""
    return len(pliki) == 1 and nazwa.lower().endswith(".pdf") and rozpoznaj(pliki[0][1])


def nieodczytany(nazwa: str, pliki: list[tuple[str, bytes]], blad: str | None = None) -> dict:
    return {"id": hashlib.sha1(b"".join(z for _, z in pliki)).hexdigest()[:12], "nazwa": nazwa, "pliki": pliki,
            "dane": None, "pytania": [], "podsumowanie": "", "wynik": None, "blad": blad, "zapisano": None}


def odczytaj(nazwa: str, pliki: list[tuple[str, bytes]], komp: bool | None = None) -> dict:
    """Odczyt jednego audytu — wywoływany w wątku, bez funkcji Streamlit. komp: wynik komputerowy(), jeśli znany."""
    audyt = nieodczytany(nazwa, pliki)
    try:
        if nazwa.lower().endswith(".xlsx"):
            dane, problemy = normalizuj(wczytaj_xlsx(io.BytesIO(pliki[0][1])))
            audyt.update(dane=uzupelnij_domyslne(dane), pytania=[Pytanie(p) for p in problemy], pliki=[])
        else:
            if komp is None:
                komp = komputerowy(nazwa, pliki)
            w = importuj(pliki[0][1]) if komp else odczytaj_audyt(pliki)
            audyt.update(dane=w.dane, pytania=w.pytania, podsumowanie=w.podsumowanie)
    except BladOdczytu as e:
        audyt["blad"] = f"Błąd odczytu: {e}"
    except Exception as e:  # noqa: BLE001 — jeden zły plik nie może zatrzymać całej partii
        audyt["blad"] = f"Nie udało się odczytać pliku: {e}"
    return audyt


def wczytaj_partie(pliki) -> None:
    grupy = grupuj_pliki(pliki)
    komp = [komputerowy(n, p) for n, p in grupy]  # rozpoznanie raz — szybkie, bez sieci
    przez_ai = [not n.lower().endswith(".xlsx") and not k for (n, _), k in zip(grupy, komp)]
    bez_klucza = any(przez_ai) and not klucz_api.aktywny_klucz()
    wyniki: list[dict | None] = [None] * len(grupy)
    do_odczytu = []
    for i, (n, p) in enumerate(grupy):
        if bez_klucza and przez_ai[i]:  # skan bez klucza — reszta partii i tak się wczyta
            wyniki[i] = nieodczytany(n, p, BRAK_KLUCZA)
        else:
            do_odczytu.append(i)
    opis = "Czytam audyty (skan przez AI: ok. 1–3 min)" if any(przez_ai[i] for i in do_odczytu) else "Wczytuję audyty"
    postep = st.progress(0.0, text=f"{opis}: 0 z {len(do_odczytu)}…")
    with ThreadPoolExecutor(max_workers=ROWNOLEGLE_ODCZYTY) as pula:
        zadania = {pula.submit(odczytaj, grupy[i][0], grupy[i][1], komp[i]): i for i in do_odczytu}
        for gotowe, z in enumerate(as_completed(zadania), start=1):
            wyniki[zadania[z]] = z.result()
            postep.progress(gotowe / len(do_odczytu), text=f"{opis}: {gotowe} z {len(do_odczytu)}…")
    postep.empty()
    for a in wyniki:
        if a["dane"] is not None:
            policz(a)
    ss.audyty = wyniki
    ss.wersja = ss.get("wersja", 0) + 1
    pierwszy = nastepny(wyniki, -1)
    ss.skok_do = pierwszy if pierwszy is not None else 0


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


def do_recznego(a: dict) -> tuple[list[str], list[str]]:
    """(pola brakujące — trzeba wpisać, pola odczytane niepewnie — trzeba potwierdzić)."""
    if a["dane"] is None:
        return [], []
    braki = pola_do_uzupelnienia(a["dane"])
    niepewne = [k for k, zr in a["dane"].zrodla.items()
                if zr in NIEPEWNE_AI and a["dane"].get(k) is not None and k not in braki and k in POLA_WEJSCIOWE]
    niepewne += [k for k in zalozenia_kluczowe(a["dane"]) if k not in niepewne and k not in braki]
    return braki, niepewne


def status(a: dict) -> str:
    if a["zapisano"]:
        return "✅ zapisano"
    if a["dane"] is None:
        return "🔑 potrzebny klucz API" if a["blad"] == BRAK_KLUCZA else "❌ błąd odczytu"
    braki, niepewne = do_recznego(a)
    if braki:
        return f"✍ uzupełnij {len(braki)}"
    if niepewne:
        return f"👁 potwierdź {len(niepewne)}"
    if a["blad"]:
        return "❌ popraw dane"
    n = len(a["wynik"].ostrzezenia)
    return f"⚠ {n} ostrzeżeń" if n else "✔ gotowe"


def zapisz(a: dict) -> None:
    a["zapisano"] = str(zapisz_adres(KATALOG_ADRESOW, a["dane"], a["wynik"], a["pliki"], a["pytania"]))


def nastepny(audyty: list[dict], obecny: int) -> int | None:
    """Indeks kolejnego niezapisanego, odczytanego audytu (po obecnym, z zawinięciem); None, gdy nie ma."""
    n = len(audyty)
    for k in range(1, n + 1):
        j = (obecny + k) % n
        if not audyty[j]["zapisano"] and audyty[j]["dane"] is not None:
            return j
    return None


def nazwa_audytu(a: dict) -> str:
    return (a["dane"].get("adres") if a["dane"] else None) or a["nazwa"]


# ---------------------------------------------------------------------------
# Podgląd skanu
# ---------------------------------------------------------------------------

@st.cache_resource(max_entries=40, show_spinner=False)
def _strona(audyt_id: str, nr: int, _pliki):
    return jedna_strona(_pliki, nr)


def pokaz_miejsce(a: dict, miejsce: Miejsce | None, kolumna) -> None:
    if not a["pliki"]:
        kolumna.caption("Dane wczytane z Excela — brak skanu do podglądu.")
        return
    if not miejsce:
        kolumna.caption("Brak wskazanego miejsca w dokumencie — zajrzyj do podglądu całego dokumentu niżej.")
        return
    strona = _strona(a["id"], miejsce.strona, a["pliki"])
    if strona is None:
        kolumna.caption(f"Brak strony {miejsce.strona} w dokumencie.")
        return
    kolumna.image(wycinek(strona, miejsce), caption=f"Strona {miejsce.strona}", width="stretch")


def miejsce_pola(a: dict, klucz: str) -> Miejsce | None:
    if klucz in a["dane"].miejsca:
        return a["dane"].miejsca[klucz]
    return next((p.miejsce for p in a["pytania"] if klucz in p.klucze and p.miejsce), None)


# ---------------------------------------------------------------------------
# Formularze
# ---------------------------------------------------------------------------

def tekst(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:g}".replace(".", ",")
    return str(v)


def widget(p: Pole, dane: Dane, prefiks: str, kolumna, etykieta: str | None = None):
    k = p.klucz
    widoczna = "visible" if etykieta else "collapsed"
    if p.rodzaj == "list":
        opcje = [""] + opcje_listy(p)
        obecna = dane.get(k)
        return kolumna.selectbox(etykieta or p.etykieta, opcje, index=opcje.index(obecna) if obecna in opcje else 0,
                                 key=f"{prefiks}_{k}", label_visibility=widoczna, placeholder="Wybierz…",
                                 format_func=lambda o: o or "— wybierz —")
    return kolumna.text_input(etykieta or p.etykieta, value=tekst(dane.get(k)), key=f"{prefiks}_{k}",
                              label_visibility=widoczna, help=p.podpowiedz or None)


def stara_wartosc(p: Pole, dane: Dane) -> str:
    return (dane.get(p.klucz) or "") if p.rodzaj == "list" else tekst(dane.get(p.klucz))


def sekcja_do_recznego(a: dict, prefiks: str, braki: list[str], niepewne: list[str]) -> dict[str, str]:
    """Pola, których AI nie odczytało albo odczytało niepewnie — z wycinkiem skanu obok. Zwraca wpisane wartości."""
    wpisane: dict[str, str] = {}
    kluczowe = zalozenia_kluczowe(a["dane"])
    for tytul, klucze, opis in (
            ("✍ Do uzupełnienia", braki, "Tych danych zabrakło w audycie albo nie udało się ich odczytać — wpisz je."),
            ("👁 Do potwierdzenia", niepewne, "Te wartości są odczytane niepewnie albo wyliczone z założeniem — porównaj z wycinkiem i popraw.")):
        if not klucze:
            continue
        st.subheader(tytul)
        st.caption(opis)
        for k in klucze:
            p = POLA_WEJSCIOWE[k]
            with st.container(border=True):
                lewa, prawa = st.columns([2, 3])
                etykieta = etykieta_z_sekcja(k) + (f" [{p.jednostka}]" if p.jednostka else "")
                wpisane[k] = widget(p, a["dane"], prefiks, lewa, etykieta)
                if a["dane"].uwagi.get(k):
                    lewa.caption(a["dane"].uwagi[k])
                if k in kluczowe:
                    lewa.caption(f"⚠ Audyt nie podaje izolacji. Puste pole = przyjmę {kluczowe[k]:g} cm wełny mineralnej "
                                 "(bez ocieplenia ten strop/dach dawałby kilka kW strat więcej).")
                pokaz_miejsce(a, miejsce_pola(a, k), prawa)
    return wpisane


def formularz(dane: Dane, prefiks: str, pomin: set[str]) -> dict[str, str]:
    """Wszystkie pola sekcjami (bez tych z sekcji „do uzupełnienia”). Zwraca bieżące wartości."""
    wpisane: dict[str, str] = {}
    sekcje: list[tuple[str, list[Pole]]] = []
    for p in POLA:
        if isinstance(p, Sekcja):
            sekcje.append((p.tytul, []))
        elif p.rodzaj != "calc" and p.klucz not in pomin:
            sekcje[-1][1].append(p)
    for tytul, pola in sekcje:
        if not pola:
            continue
        niepewnych = sum(1 for p in pola if dane.zrodla.get(p.klucz) in NIEPEWNE and dane.get(p.klucz) is not None)
        with st.expander(tytul + (f"  —  {niepewnych} założeń/niepewnych" if niepewnych else "")):
            for p in pola:
                zrodlo = dane.zrodla.get(p.klucz, "")
                c1, c2, c3 = st.columns([3, 2, 4])
                c1.markdown(f"**{p.etykieta}**" + (f" [{p.jednostka}]" if p.jednostka else ""))
                if zrodlo:
                    c1.caption(zrodlo)
                wpisane[p.klucz] = widget(p, dane, prefiks, c2)
                if dane.uwagi.get(p.klucz):
                    c3.caption(dane.uwagi[p.klucz])
    return wpisane


def zastosuj(a: dict, wpisane: dict[str, str], potwierdzone: set[str]) -> None:
    """Przenosi wpisy z formularza do danych; pola zmienione lub obejrzane przez człowieka dostają jego źródło."""
    dane = a["dane"].kopia()
    kluczowe = zalozenia_kluczowe(a["dane"])
    for k, nowa in wpisane.items():
        p = POLA_WEJSCIOWE[k]
        if not nowa and k in potwierdzone and k in kluczowe:  # potwierdzone założenie domyślne
            nowa = tekst(kluczowe[k])
            material = k.removesuffix("_grubosc")
            if dane.get(material) is None:
                dane.wartosci[material] = wczytaj_konfiguracje()["zalozenia"]["izolacja_stropu_brak"]
                dane.zrodla[material] = ZRODLO_CZLOWIEK
        if nowa != stara_wartosc(p, a["dane"]) or k in potwierdzone:
            dane.wartosci[k] = nowa or None
            if nowa:
                dane.zrodla[k] = ZRODLO_CZLOWIEK
    a["dane"] = dane
    a["zapisano"] = None
    policz(a)


def sprawdzanie(a: dict, i: int) -> None:
    if a["dane"] is None:
        st.error(a["blad"])
        return
    braki, niepewne = do_recznego(a)
    if a["wynik"]:
        st.metric(f"OZC — {a['dane'].get('adres') or a['nazwa']}", f"{a['wynik'].phi_HL_kW:.2f} kW")
        if a["wynik"].ostrzezenia:
            st.warning("**Do sprawdzenia:**\n\n" + "\n".join(f"- {o}" for o in a["wynik"].ostrzezenia))
    elif not braki and a["blad"]:
        st.error(a["blad"])
    if a["podsumowanie"]:
        st.info(a["podsumowanie"])
    luzne = [p for p in a["pytania"] if not p.klucze]
    if luzne:
        st.warning("**Pytania do audytora:**\n\n" + "\n".join(f"- {p.tekst}" for p in luzne))

    prefiks = f"{ss.get('wersja', 0)}_{a['id']}"
    wpisane = sekcja_do_recznego(a, prefiks, braki, niepewne)
    if not braki and not niepewne:
        st.success("Wszystkie dane są odczytane albo potwierdzone.")

    if a["pliki"]:
        with st.expander("📄 Podgląd całego dokumentu"):
            n = liczba_stron(a["pliki"])
            nr = st.number_input("Strona", 1, n, 1, key=f"strona_{prefiks}")
            st.image(_strona(a["id"], nr, a["pliki"]), width="stretch")
    with st.expander("Wszystkie dane audytu"):
        wpisane |= formularz(a["dane"], prefiks, pomin=set(braki) | set(niepewne))

    st.caption("„Zatwierdź” przyjmuje wpisane wartości (i te do potwierdzenia), liczy OZC, zapisuje raport Word i PDF "
               "i przechodzi do następnego audytu. „Przelicz” tylko pokazuje wynik po zmianach.")
    c1, c2 = st.columns(2)
    if c1.button("✅ Zatwierdź i zapisz raport" if not a["zapisano"] else "✅ Zapisz ponownie",
                 key=f"zatwierdz_{i}", type="primary"):
        zastosuj(a, wpisane, potwierdzone=set(niepewne))
        braki_po, _ = do_recznego(a)
        if braki_po:
            ss.blad_zatwierdzenia = "Nie zapisano — uzupełnij: " + ", ".join(etykieta_z_sekcja(k) for k in braki_po)
        elif not a["wynik"]:
            ss.blad_zatwierdzenia = f"Nie zapisano — {a['blad'] or 'nie udało się policzyć OZC'}"
        else:
            with st.spinner("Tworzę raport Word i PDF…"):
                zapisz(a)
            ss.komunikat = ("success", f"Zapisano: {nazwa_audytu(a)} — {a['wynik'].phi_HL_kW:.2f} kW.")
            dalej = nastepny(ss.audyty, i)
            ss.skok_do = dalej if dalej is not None else i
        st.rerun()
    if c2.button("🔄 Przelicz", key=f"przelicz_{i}"):
        zastosuj(a, wpisane, potwierdzone=set())
        st.rerun()
    if "blad_zatwierdzenia" in ss:
        st.error(ss.pop("blad_zatwierdzenia"))
    if a["zapisano"]:
        st.success("Zapisano — raport jest w zakładce „Lista adresów”.")


# ---------------------------------------------------------------------------
# Strony
# ---------------------------------------------------------------------------

def strona_audyty() -> None:
    st.title("Audyty")
    st.markdown("**1.** Wrzuć audyty — **każdy PDF to osobny adres** (można wiele naraz). Działają wszystkie "
                "formaty: komputerowe audyty FlexiPower (czytane od razu), skany i zdjęcia protokołów odręcznych — "
                "stare i nowe wersje formularza (czyta je AI, potrzebny klucz w „Ustawieniach”) — oraz wypełniony "
                "szablon Excel. Zdjęcia stron jednego protokołu wrzuć razem, w osobnej partii.")
    pliki = st.file_uploader("Pliki audytów", type=["pdf", "jpg", "jpeg", "png", "webp", "xlsx"],
                             accept_multiple_files=True, label_visibility="collapsed",
                             key=f"wgrane_{ss.get('wersja', 0)}")
    if pliki and st.button(f"📄 Odczytaj ({len(grupuj_pliki(pliki))})", type="primary"):
        wczytaj_partie(pliki)
        st.rerun()

    audyty = ss.get("audyty")
    if not audyty:
        return

    komunikat = ss.pop("komunikat", None)
    if komunikat:
        getattr(st, komunikat[0])(komunikat[1])
    zapisane = sum(1 for a in audyty if a["zapisano"])
    bledy = sum(1 for a in audyty if a["dane"] is None)
    pozostale = len(audyty) - zapisane - bledy
    st.markdown(f"**2.** Wyniki: **{zapisane}** zapisanych, **{pozostale}** do sprawdzenia"
                + (f", **{bledy}** nieodczytanych" if bledy else "") + f" (razem {len(audyty)}).")
    if pozostale == 0 and zapisane:
        st.success("Wszystkie odczytane audyty są zapisane — raporty są w zakładce „Lista adresów”.")
    tabela = pd.DataFrame([{
        "Adres": nazwa_audytu(a),
        "OZC [kW]": f"{a['wynik'].phi_HL_kW:.2f}".replace(".", ",") if a["wynik"] else "—",
        "Status": status(a),
        "Plik": a["nazwa"],
    } for a in audyty])
    st.dataframe(tabela, hide_index=True, width="stretch")

    gotowe = [a for a in audyty if status(a) == "✔ gotowe"]
    c1, c2 = st.columns(2)
    if gotowe and c1.button(f"💾 Zapisz wszystkie gotowe ({len(gotowe)})"):
        with st.spinner("Tworzę raporty Word i PDF…"):
            for a in gotowe:
                zapisz(a)
        st.rerun()
    if c2.button("🗑 Wyczyść i zacznij nową partię"):
        ss.pop("audyty", None)
        ss.wersja = ss.get("wersja", 0) + 1
        st.rerun()

    st.markdown("**3.** Sprawdź audyt — po zatwierdzeniu program sam przejdzie do następnego.")
    if "skok_do" in ss:
        ss.wybrany_audyt = min(ss.pop("skok_do"), len(audyty) - 1)
    etykiety = [f"{i + 1}. {nazwa_audytu(a)} — {status(a)}" for i, a in enumerate(audyty)]
    i = st.selectbox("Audyt", range(len(audyty)), format_func=lambda j: etykiety[j], label_visibility="collapsed",
                     key="wybrany_audyt")
    sprawdzanie(audyty[min(i, len(audyty) - 1)], min(i, len(audyty) - 1))


def _excel_z_linkami(adresy: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "OZC"
    for j, t in enumerate(("Adres", "OZC [kW]", "Raport Word", "Raport PDF"), start=1):
        ws.cell(1, j, t).font = Font(bold=True)
    for i, a in enumerate(adresy, start=2):
        ws.cell(i, 1, a.get("adres"))
        ws.cell(i, 2, a.get("phi_HL_kW"))
        for j, klucz in ((3, "raport_docx"), (4, "raport_pdf")):
            if a.get(klucz):
                c = ws.cell(i, j, Path(a[klucz]).name)
                c.hyperlink = a[klucz]
                c.font = Font(color="0563C1", underline="single")
    for kol, szer in zip("ABCD", (45, 10, 60, 60)):
        ws.column_dimensions[kol].width = szer
    bufor = io.BytesIO()
    wb.save(bufor)
    return bufor.getvalue()


def strona_lista() -> None:
    st.title("Lista adresów")
    adresy = lista_adresow(KATALOG_ADRESOW)
    if not adresy:
        st.info("Nie zapisano jeszcze żadnego adresu.")
        return
    szukaj = st.text_input("Szukaj adresu", placeholder="np. Lipowa", label_visibility="collapsed")
    if szukaj:
        adresy = [a for a in adresy if szukaj.casefold() in (a.get("adres") or "").casefold()]

    naglowek = st.columns([5, 2, 2, 2])
    for kol, t in zip(naglowek, ("**Adres**", "**OZC [kW]**", "**Word**", "**PDF**")):
        kol.markdown(t)
    for i, a in enumerate(adresy):
        c = st.columns([5, 2, 2, 2])
        c[0].write(a.get("adres") or "—")
        c[1].write(f"{a.get('phi_HL_kW', 0):.2f}".replace(".", ","))
        docx, pdf = a.get("raport_docx"), a.get("raport_pdf")
        if docx and Path(docx).exists():
            if c[2].button("📄 Otwórz", key=f"docx_{i}"):
                os.startfile(docx)
        elif c[2].button("Utwórz raport", key=f"utworz_{i}"):
            with st.spinner("Tworzę raport…"):
                try:
                    raport_dla_folderu(Path(a["folder"]))
                except BladDanych as e:
                    st.error("Nie da się policzyć: " + "; ".join(e.problemy))
            st.rerun()
        if pdf and Path(pdf).exists():
            if c[3].button("📕 Otwórz", key=f"pdf_{i}"):
                os.startfile(pdf)
        elif docx:
            c[3].caption("brak Worda do PDF")
        if a.get("kopia_raportu_blad"):
            st.caption(f"⚠ {a['kopia_raportu_blad']}")

    st.divider()
    c1, c2 = st.columns(2)
    c1.download_button("Pobierz tabelę z linkami (.xlsx)", _excel_z_linkami(adresy), file_name="OZC_adresy.xlsx")
    folder = ustawienia.folder_raportow()
    if folder and folder.exists() and c2.button("📂 Otwórz folder raportów"):
        os.startfile(folder)


def strona_ustawienia() -> None:
    st.title("Ustawienia")
    st.subheader("Klucz API Anthropic")
    aktywny = klucz_api.aktywny_klucz()
    if aktywny:
        st.success(f"Klucz jest ustawiony: `{klucz_api.zamaskowany(aktywny)}` — odczyt PDF przez AI działa.")
    else:
        st.warning("Brak klucza — skany i zdjęcia protokołów nie zostaną odczytane. "
                   "Komputerowe audyty FlexiPower i pliki Excel działają bez klucza.")

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

    st.subheader("Folder na raporty OZC")
    obecny = ustawienia.folder_raportow()
    with st.form("folder"):
        nowy_folder = st.text_input(
            "Dodatkowy folder, do którego kopiowane są raporty Word i PDF (np. na Dysku współdzielonym)",
            value=str(obecny or ""),
            placeholder=r"G:\Dyski współdzielone\Dział Projektowy Sanitarny\24. Ślesin\PC powietrzne\OZC")
        if st.form_submit_button("Zapisz folder"):
            sciezka = nowy_folder.strip().strip('"')
            if sciezka and not Path(sciezka).exists():
                st.error("Taki folder nie istnieje — sprawdź ścieżkę.")
            else:
                ustawienia.ustaw("folder_raportow", sciezka)
                st.rerun()
    st.caption("Raporty zawsze zapisują się też w folderze adresu programu. Puste pole = bez dodatkowej kopii.")

    st.subheader("Jak to działa")
    st.markdown("""
- Komputerowe audyty FlexiPower program czyta sam; skany protokołów odręcznych (stare i nowe wersje formularza)
  czyta AI i przy każdej wartości wskazuje miejsce w dokumencie. Czego nie odczytano albo co jest szacunkiem,
  program pokazuje w sekcji „Do uzupełnienia / Do potwierdzenia” z wycinkiem dokumentu — wystarczy wpisać
  lub poprawić i kliknąć „Zatwierdź i zapisz raport”.
- Obliczenia: PN-EN 12831:2006 dla całego budynku; grunt wg PN-EN ISO 13370.
- Raport OZC (Word + PDF) w układzie FlexiPower Group. PDF tworzy zainstalowany Word.
- Koszt odczytu: ok. 0,1–0,3 USD za audyt.
""")
    st.caption(f"Wersja {__version__} · wyniki zapisują się w {KATALOG_ADRESOW}")


strony = {"Audyty": strona_audyty, "Lista adresów": strona_lista, "Ustawienia": strona_ustawienia}
wybrana = st.sidebar.radio("Menu", list(strony))
if not klucz_api.aktywny_klucz():
    st.sidebar.warning("Brak klucza API — wpisz go w „Ustawieniach”. Bez klucza działają komputerowe audyty "
                       "FlexiPower i pliki Excel; skany wymagają klucza.")
st.sidebar.divider()
if st.sidebar.button("⏻ Zamknij program"):
    st.sidebar.info("Program zamknięty — możesz zamknąć tę kartę przeglądarki.")
    threading.Timer(1.0, os._exit, [0]).start()
strony[wybrana]()
