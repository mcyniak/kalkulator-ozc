"""Projektowe obciążenie cieplne całego budynku wg PN-EN 12831:2006 (jedna strefa).

Φ_HL = Φ_T + Φ_V (+ Φ_RH, domyślnie 0)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import grunt, przegrody
from .dane import ZRODLO_DOMYSLNE, BladDanych, Dane
from .dobor import kontrola_paliwa
from .geometria import Geometria, oblicz_geometrie
from .konfiguracja import wczytaj_konfiguracje
from .pola import POLA_WEJSCIOWE, SEKCJA_POLA


@dataclass
class Element:
    grupa: str
    A: float
    U: float
    dU_tb: float
    b: float
    phi: float = 0.0          # [W]
    uwaga: str = ""

    @property
    def H(self) -> float:
        return self.A * (self.U + self.dU_tb) * self.b


@dataclass
class Wynik:
    phi_HL: float                         # [W]
    phi_T: float
    phi_V: float
    phi_RH: float
    theta_int: float
    theta_e: float
    theta_me: float
    elementy: list[Element]
    geometria: Geometria
    wentylacja: dict
    U: dict
    kroki: list[str] = field(default_factory=list)
    ostrzezenia: list[str] = field(default_factory=list)
    zalozenia: list[str] = field(default_factory=list)
    kontrola_paliwa: dict | None = None
    pow_ogrzewana: float = 0.0            # [m²] podstawa wskaźników: deklarowana, a bez niej z obrysu

    @property
    def kubatura(self) -> float:
        """Kubatura przyjęta do obliczeń [m³] (wentylacja) — ta sama w raporcie i wskaźnikach."""
        return self.wentylacja["V"]

    @property
    def phi_HL_kW(self) -> float:
        return self.phi_HL / 1000

    def rozbicie(self) -> dict[str, float]:
        """Straty [W] zsumowane wg grupy przegród + wentylacja."""
        r: dict[str, float] = {}
        for e in self.elementy:
            r[e.grupa] = r.get(e.grupa, 0.0) + e.phi
        r["Wentylacja"] = self.phi_V
        if self.phi_RH:
            r["Nagrzewanie (Φ_RH)"] = self.phi_RH
        return r


# ---------------------------------------------------------------------------
# Kompletność danych
# ---------------------------------------------------------------------------

def _etykieta(klucz: str) -> str:
    return POLA_WEJSCIOWE[klucz].etykieta


def etykieta_z_sekcja(klucz: str) -> str:
    return f"{POLA_WEJSCIOWE[klucz].etykieta} ({SEKCJA_POLA[klucz]})"


def brakujace_pola(d: Dane) -> list[str]:
    """Klucze pól niezbędnych do obliczeń, których brakuje (puste = można liczyć)."""
    braki: list[str] = []

    def wymagaj(*klucze: str) -> None:
        for k in klucze:
            if d.get(k) is None and k not in braki:
                braki.append(k)

    def przegroda(u_reczne: str, *klucze: str, izolacja: str | None = None, grubosc: str | None = None) -> None:
        if d.get(u_reczne) is not None:
            return
        wymagaj(*klucze)
        if izolacja:
            wymagaj(izolacja)
            if d.get(izolacja) not in (None, "Brak", "Pustka powietrzna"):
                wymagaj(grubosc)

    wymagaj("strefa", "t_int", "h_parter")
    if str(d.get("obrys", "Prostokąt")).startswith("Inny"):
        wymagaj("pole_zabudowy", "obwod")
    else:
        wymagaj("dl_budynku", "szer_budynku")
    przegroda("sciana_U_reczne", "sciana_material", "sciana_grubosc", izolacja="sciana_ocieplenie",
              grubosc="sciana_ocieplenie_grubosc")
    if d.get("sciana_material_2") and d.get("sciana_U_reczne") is None:
        wymagaj("sciana_grubosc_2")

    # Brak informacji o oknach to nie „zero okien” — trzeba zapytać.
    okna = ("okna_male", "okna_srednie", "okna_duze", "okna_dachowe")
    if all(d.get(k) is None for k in okna[:3]):
        wymagaj(*okna[:3])
    if sum(d.get(k, 0) for k in okna) > 0 and d.get("okna_U_reczne") is None:
        wymagaj("okna_typ", "okna_rok")
    wymagaj("drzwi_ilosc")
    if d.get("drzwi_ilosc", 0) > 0:
        wymagaj("drzwi_szer", "drzwi_wys")
        if d.get("drzwi_U_reczne") is None:
            wymagaj("drzwi_rok")

    piwnica = d.get("piwnica", "Brak")
    if piwnica in ("Brak", "Ogrzewana"):
        przegroda("podloga_U_reczne", izolacja="podloga_izolacja", grubosc="podloga_izolacja_grubosc")
    if piwnica == "Nieogrzewana":
        przegroda("piwn_strop_U_reczne", "piwn_strop_konstrukcja", izolacja="piwn_strop_izolacja",
                  grubosc="piwn_strop_izolacja_grubosc")
    if piwnica == "Ogrzewana":
        wymagaj("h_piwnicy")
        przegroda("fund_U_reczne", "fund_material", "fund_grubosc", izolacja="fund_izolacja",
                  grubosc="fund_izolacja_grubosc")
    if d.get("liczba_pieter", 0) > 0:
        wymagaj("h_pietra")

    dach = d.get("dach_rodzaj", "Skośny dwuspadowy")
    poddasze = d.get("poddasze_uzytkowe") == "Tak"
    if poddasze:
        wymagaj("h_poddasza")
        if dach != "Płaski":
            wymagaj("kat_dachu")
            przegroda("dach_U_reczne", izolacja="dach_izolacja", grubosc="dach_izolacja_grubosc")
    if (poddasze and d.get("strych_nieogrzewany", "Tak") == "Tak") or not poddasze or dach == "Płaski":
        przegroda("strop_U_reczne", "strop_konstrukcja", izolacja="strop_izolacja",
                  grubosc="strop_izolacja_grubosc")
    return braki


def sprawdz_kompletnosc(d: Dane) -> list[str]:
    """Czytelne nazwy brakujących pól (puste = można liczyć)."""
    return [etykieta_z_sekcja(k) for k in brakujace_pola(d)]


def zalozenia_kluczowe(dane: Dane) -> dict[str, float]:
    """Założenia, które mocno zmieniają wynik i wymagają potwierdzenia człowieka: {klucz: przyjęta wartość}."""
    d = dane.kopia()
    _domysl_brakujace(d, [])
    poddasze = d.get("poddasze_uzytkowe") == "Tak"
    dach = d.get("dach_rodzaj", "Skośny dwuspadowy")
    strop_potrzebny = (poddasze and d.get("strych_nieogrzewany", "Tak") == "Tak") or not poddasze or dach == "Płaski"
    wynik = {}
    for k, potrzebny in (("strop_izolacja_grubosc", strop_potrzebny), ("dach_izolacja_grubosc", poddasze and dach != "Płaski")):
        if potrzebny and dane.get(k) is None and d.zrodla.get(k) == ZRODLO_DOMYSLNE:
            wynik[k] = d.get(k)
    return wynik


def pola_do_uzupelnienia(dane: Dane) -> list[str]:
    """Pola, które człowiek musi wpisać, zanim da się policzyć — po przyjęciu bezpiecznych założeń."""
    d = dane.kopia()
    _domysl_brakujace(d, [])
    return brakujace_pola(d)


def _domysl_brakujace(d: Dane, notatki: list[str]) -> None:
    """Rozstrzyga pola wyboru, których brak da się bezpiecznie założyć — zawsze z adnotacją."""
    def przyjmij(klucz: str, wartosc, powod: str) -> None:
        if d.get(klucz) is None:
            d.wartosci[klucz] = wartosc
            d.zrodla[klucz] = ZRODLO_DOMYSLNE
            notatki.append(f"Brak pola „{_etykieta(klucz)}” — przyjęto „{wartosc}” ({powod}).")

    przyjmij("piwnica", "Brak", "protokół nie zaznacza piwnicy")
    przyjmij("poddasze_uzytkowe", "Tak" if d.get("h_poddasza") else "Nie", "wg wysokości poddasza")
    if d.get("dach_rodzaj") is None:
        kat = d.get("kat_dachu")
        przyjmij("dach_rodzaj", "Płaski" if kat is not None and kat < 10 else "Skośny dwuspadowy", "wg kąta dachu")
    przyjmij("strych_nieogrzewany", "Tak", "typowo nad poddaszem jest nieogrzewany strych")
    przyjmij("wentylacja", "Grawitacyjna", "najczęstszy przypadek")
    przyjmij("szczelnosc", "Średni", "wartość środkowa")
    przyjmij("oslonienie", "Średnie", "wartość środkowa")
    if d.get("drzwi_ilosc") and d.get("drzwi_U_reczne") is None:
        rok = d.get("okna_rok") or d.get("rok_budowy")
        if rok:
            przyjmij("drzwi_rok", int(rok), "jak okna / rok budowy")

    # Strop / dach bez podanej izolacji: audyty często pomijają ocieplenie — założenie jawne, do potwierdzenia.
    zal = wczytaj_konfiguracje()["zalozenia"]
    for izol, grub, u_reczne in (("strop_izolacja", "strop_izolacja_grubosc", "strop_U_reczne"),
                                 ("dach_izolacja", "dach_izolacja_grubosc", "dach_U_reczne")):
        izolacja_podana = d.get(izol) is not None and d.zrodla.get(izol) != ZRODLO_DOMYSLNE
        if d.get(u_reczne) is None and d.get(grub) is None and not izolacja_podana:
            d.wartosci.pop(izol, None)
            przyjmij(izol, zal["izolacja_stropu_brak"], "audyt nie podaje izolacji")
            przyjmij(grub, zal["izolacja_stropu_brak_cm"], "audyt nie podaje izolacji")


# ---------------------------------------------------------------------------
# Obliczenia
# ---------------------------------------------------------------------------

def _u(d: Dane, reczne: str, licz) -> float:
    return d.get(reczne) if d.get(reczne) is not None else licz()


def wspolczynniki_U(d: Dane) -> dict[str, float]:
    U: dict[str, float] = {}
    if d.get("sciana_U_reczne") is not None or d.get("sciana_material"):
        U["sciana"] = _u(d, "sciana_U_reczne", lambda: przegrody.u_sciany(
            d.get("sciana_material"), d.get("sciana_grubosc"), d.get("sciana_ocieplenie"),
            d.get("sciana_ocieplenie_grubosc"), d.get("sciana_material_2"), d.get("sciana_grubosc_2")))
    if d.get("fund_U_reczne") is not None or d.get("fund_material"):
        U["fund"] = _u(d, "fund_U_reczne", lambda: przegrody.u_sciany_fundamentowej(
            d.get("fund_material"), d.get("fund_grubosc"), d.get("fund_izolacja", "Brak"),
            d.get("fund_izolacja_grubosc")))
    if d.get("podloga_U_reczne") is not None or d.get("podloga_izolacja"):
        U["podloga"] = _u(d, "podloga_U_reczne", lambda: przegrody.u_podlogi(
            d.get("podloga_wylewka"), d.get("podloga_izolacja"), d.get("podloga_izolacja_grubosc"),
            d.get("podloga_chudy_beton")))
    if d.get("strop_U_reczne") is not None or d.get("strop_konstrukcja"):
        U["strop"] = _u(d, "strop_U_reczne", lambda: przegrody.u_stropu_pod_strychem(
            d.get("strop_konstrukcja"), d.get("strop_grubosc"), d.get("strop_izolacja", "Brak"),
            d.get("strop_izolacja_grubosc")))
    if d.get("dach_U_reczne") is not None or d.get("dach_izolacja"):
        U["dach"] = _u(d, "dach_U_reczne", lambda: przegrody.u_dachu(
            d.get("dach_izolacja"), d.get("dach_izolacja_grubosc")))
    if d.get("piwn_strop_U_reczne") is not None or d.get("piwn_strop_konstrukcja"):
        U["piwn_strop"] = _u(d, "piwn_strop_U_reczne", lambda: przegrody.u_stropu_nad_piwnica(
            d.get("piwn_strop_konstrukcja"), d.get("piwn_strop_grubosc"), d.get("piwn_strop_izolacja", "Brak"),
            d.get("piwn_strop_izolacja_grubosc")))
    if d.get("okna_U_reczne") is not None or d.get("okna_typ"):
        U["okna"] = _u(d, "okna_U_reczne", lambda: przegrody.u_okien(
            d.get("okna_typ"), d.get("okna_rok"), d.get("okna_material")))
    if d.get("drzwi_U_reczne") is not None or d.get("drzwi_rok"):
        U["drzwi"] = _u(d, "drzwi_U_reczne", lambda: przegrody.u_drzwi(d.get("drzwi_rok")))
    # U okien/drzwi wpisane z audytu to zwykle wartości katalogowe — bez strat na osadzeniu.
    dodatek = wczytaj_konfiguracje()["norma"].get("dodatek_U_okna_drzwi", 0.0)
    for k, reczne in (("okna", "okna_U_reczne"), ("drzwi", "drzwi_U_reczne")):
        if k in U and d.get(reczne) is not None:
            U[k] += dodatek
    return U


def kontrole_wiarygodnosci(d: Dane, U: dict, geo: Geometria, a_okien: float, phi_HL: float, cfg: dict) -> list[str]:
    """Nietypowe wartości, które zwykle oznaczają błąd w audycie lub odczycie — do sprawdzenia przez człowieka."""
    k = cfg["kontrola"]
    uwagi = []
    u_sc = U.get("sciana")
    rok = d.get("rok_budowy")
    if u_sc and u_sc > k["U_sciany_max"]:
        uwagi.append(f"Ściana o U = {u_sc:.2f} W/m²K (praktycznie bez ocieplenia)"
                     + (f" w budynku z {rok:.0f} r." if rok else "")
                     + " — sprawdź warstwy ściany w audycie, to częsty błąd danych.")
    pow_ = d.get("pow_ogrz_dekl") or geo.pow_ogrzewana
    if pow_ and a_okien:
        udzial = a_okien / pow_
        lo, hi = k["udzial_okien"]
        if not lo <= udzial <= hi:
            uwagi.append(f"Okna to {udzial:.0%} powierzchni ogrzewanej (typowo {lo:.0%}–{hi:.0%}) — sprawdź liczbę "
                         "i wielkość okien.")
    if pow_:
        wsk = phi_HL / pow_
        lo, hi = k["W_na_m2"]
        if not lo <= wsk <= hi:
            uwagi.append(f"Wynik {wsk:.0f} W/m² jest nietypowy dla domu jednorodzinnego (zwykle {lo}–{hi} W/m²) — "
                         "sprawdź dane wejściowe.")
    return uwagi


def oblicz(dane: Dane) -> Wynik:
    """Liczy Φ_HL. `dane` muszą być znormalizowane (ozc.dane.normalizuj)."""
    cfg = wczytaj_konfiguracje()
    n = cfg["norma"]
    d = dane.kopia()
    notatki: list[str] = []
    _domysl_brakujace(d, notatki)
    braki = sprawdz_kompletnosc(d)
    if braki:
        raise BladDanych([f"Brak danych: {b}" for b in braki])

    strefa = next(s for s in cfg["strefy"] if s["nazwa"] == d.get("strefa"))
    th_i, th_e, th_me = d.get("t_int"), strefa["theta_e"], strefa["theta_me"]
    dT = th_i - th_e
    kroki = [
        "### 1. Dane klimatyczne",
        f"- Strefa {strefa['nazwa']}: θe = {th_e} °C, θm,e = {th_me} °C, θint = {th_i:g} °C",
        f"- ΔT = θint − θe = {th_i:g} − ({th_e}) = **{dT:g} K**",
    ]

    U = wspolczynniki_U(d)
    geo = oblicz_geometrie(d, cfg)
    notatki.extend(geo.notatki)
    kroki += ["", "### 2. Geometria",
              f"- Obrys zewn. {geo.dlugosc:.2f} × {geo.szerokosc:.2f} m, grubość ścian {geo.grubosc_scian:.2f} m",
              f"- Rzut w świetle ścian: {geo.pole_wewn:.1f} m², obwód zewn. (bez ścian wspólnych) {geo.obwod_zewn:.2f} m"]
    for nazwa, pole, kub in geo.kondygnacje:
        kroki.append(f"- {nazwa}: pow. {pole:.1f} m², kubatura {kub:.1f} m³")
    kroki.append(f"- **Kubatura ogrzewana V = {geo.kubatura:.1f} m³**, pow. ogrzewana ≈ {geo.pow_ogrzewana:.1f} m² "
                 "(PN-ISO 9836: poddasze 100% przy h ≥ 2,2 m, 50% przy 1,4–2,2 m)")

    # --- okna i drzwi ---
    a_okna_pion = sum(d.get(f"okna_{r}", 0) * d.get(f"pow_okna_{r}", 0) for r in ("male", "srednie", "duze"))
    a_okna_dach = d.get("okna_dachowe", 0) * d.get("pow_okna_dachowe", 0)
    a_drzwi = d.get("drzwi_ilosc", 0) * d.get("drzwi_szer", 0) * d.get("drzwi_wys", 0)
    if a_okna_dach and not geo.dach_skos:
        notatki.append("Okna dachowe bez dachu skośnego nad częścią ogrzewaną — doliczono je do okien w ścianach.")
        a_okna_pion, a_okna_dach = a_okna_pion + a_okna_dach, 0.0
    a_sciany = geo.sciany_brutto - a_okna_pion - a_drzwi
    if a_sciany <= 0:
        raise BladDanych(["Powierzchnia okien i drzwi przekracza powierzchnię ścian — sprawdź obrys i okna."])

    dU = n["delta_U_tb"]
    b_sas = (th_i - n["sasiad"]["theta_sasiad"]) / dT
    elementy: list[Element] = []

    def dodaj(grupa: str, A: float, U_: float | None, dU_: float = dU, b: float = 1.0, uwaga: str = "") -> None:
        if A > 0:
            if U_ is None:
                raise BladDanych([f"Brak danych do wyznaczenia U: {grupa} ({A:.1f} m²)"])
            elementy.append(Element(grupa, A, U_, dU_, b, uwaga=uwaga))

    dodaj("Ściany zewnętrzne", a_sciany, U["sciana"])
    dodaj("Okna", a_okna_pion + a_okna_dach, U.get("okna"))
    dodaj("Drzwi", a_drzwi, U.get("drzwi"))
    dodaj("Dach skośny", geo.dach_skos - a_okna_dach, U.get("dach"))
    dodaj("Strop pod strychem", geo.strop_strych, U.get("strop"), b=n["b_u"]["strych"],
          uwaga="b_u strych")
    dodaj("Stropodach", geo.stropodach, U.get("strop"))
    dodaj("Strop nad piwnicą", geo.strop_piwnica, U.get("piwn_strop"), b=n["b_u"]["piwnica"],
          uwaga="b_u piwnica")
    dodaj("Ściany piwnicy nad terenem", geo.piwnica_sciany_nad_terenem, U.get("fund"))
    dodaj("Ściany do sąsiada", geo.sciany_sasiad, U["sciana"], dU_=0.0, b=b_sas,
          uwaga=f"θ sąsiada {n['sasiad']['theta_sasiad']:g} °C")
    for e in elementy:
        e.phi = e.H * dT

    kroki += ["", "### 3. Przenikanie przez przegrody (bez gruntu)",
              f"Φ = A · (U + ΔU_tb) · b · ΔT, ΔU_tb = {dU} W/m²K (mostki, metoda uproszczona)", "",
              "| Przegroda | A [m²] | U [W/m²K] | ΔU_tb | b | H [W/K] | Φ [W] |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for e in elementy:
        kroki.append(f"| {e.grupa} | {e.A:.1f} | {e.U:.3f} | {e.dU_tb:.2f} | {e.b:.2f} | {e.H:.1f} | {e.phi:.0f} |")
    kroki.append(f"\nPowierzchnia ścian netto = {geo.sciany_brutto:.1f} (brutto) − {a_okna_pion:.1f} (okna) "
                 f"− {a_drzwi:.1f} (drzwi) = {a_sciany:.1f} m²")

    # --- grunt ---
    fg2 = (th_i - th_me) / dT
    G_w = n["G_w_plytko"] if d.get("woda_gruntowa_plytko") == "Tak" else n["G_w"]
    lam = n["lambda_grunt"]
    wsp = n["fg1"] * fg2 * G_w
    b_prim = grunt.wymiar_charakterystyczny(geo.pole_wewn, geo.obwod_wewn_eksponowany)
    grunt_kroki = []
    if geo.podloga_grunt:
        u_eq = grunt.u_plyty_na_gruncie(b_prim, geo.grubosc_scian, U["podloga"], lam)
        e = Element("Podłoga na gruncie", geo.podloga_grunt, u_eq, 0.0, wsp)
        e.phi = e.H * dT
        elementy.append(e)
        grunt_kroki.append(f"- Podłoga: U konstrukcji {U['podloga']:.3f} → U_equiv = {u_eq:.3f} W/m²K "
                           f"(ISO 13370, płyta na gruncie), A = {geo.podloga_grunt:.1f} m², Φ = {e.phi:.0f} W")
    if geo.piwnica_podloga:
        u_bf = grunt.u_podlogi_piwnicy(b_prim, geo.grubosc_scian, U["podloga"], geo.piwnica_z, lam)
        u_bw = grunt.u_scian_piwnicy(geo.piwnica_z, geo.grubosc_scian, U["podloga"], U["fund"], lam)
        for grupa, A, u_eq in (("Podłoga piwnicy", geo.piwnica_podloga, u_bf),
                               ("Ściany piwnicy w gruncie", geo.piwnica_sciany_grunt, u_bw)):
            e = Element(grupa, A, u_eq, 0.0, wsp)
            e.phi = e.H * dT
            elementy.append(e)
            grunt_kroki.append(f"- {grupa}: U_equiv = {u_eq:.3f} W/m²K, A = {A:.1f} m², Φ = {e.phi:.0f} W")
    if grunt_kroki:
        kroki += ["", "### 4. Przenikanie do gruntu",
                  "Φ = fg1 · fg2 · A · U_equiv · G_w · ΔT",
                  f"- fg1 = {n['fg1']}, fg2 = (θint − θm,e)/(θint − θe) = ({th_i:g} − {th_me})/{dT:g} = {fg2:.3f}, "
                  f"G_w = {G_w}",
                  f"- B' = A / (0,5·P) = {geo.pole_wewn:.1f} / (0,5 · {geo.obwod_wewn_eksponowany:.2f}) = {b_prim:.2f} m",
                  *grunt_kroki]

    phi_T = sum(e.phi for e in elementy)

    # --- wentylacja ---
    V = geo.kubatura
    dekl = d.get("pow_ogrz_dekl")
    if cfg["geometria"].get("kubatura_z_deklaracji") and dekl and geo.pow_ogrzewana:
        # Wymiary ścian obejmują często części nieogrzewane (garaż, ganek, poddasze nieużytkowe) —
        # wentylowana jest tylko powierzchnia ogrzewana z audytu, przy wysokości wynikającej z geometrii.
        V = geo.kubatura * dekl / geo.pow_ogrzewana
        kroki += ["", f"Kubatura wentylowana z powierzchni deklarowanej: {geo.kubatura:.0f} m³ × {dekl:g} / "
                      f"{geo.pow_ogrzewana:.0f} m² = {V:.0f} m³"]
    n50 = n["n50"][d.get("szczelnosc")]
    e_osl = n["e_oslonienie"][d.get("oslonienie")]
    eps = (n["epsilon_do_10m"] if geo.wysokosc <= 10 else
           n["epsilon_10_30m"] if geo.wysokosc <= 30 else n["epsilon_ponad_30m"])
    v_inf = 2 * V * n50 * e_osl * eps
    v_inf_bud = n["wsp_infiltracji_budynek"] * v_inf
    v_min = n["n_min"] * V
    went = d.get("wentylacja")
    if went == "Grawitacyjna":
        v_obl = max(v_inf_bud, v_min)
        opis_v = (f"V̇ = max(0,5·V̇_inf ; V̇_min) = max({v_inf_bud:.1f} ; {v_min:.1f}) = {v_obl:.1f} m³/h")
        eta = 0.0
    else:
        eta = (d.get("sprawnosc_odzysku", 0) / 100) if went == "Mechaniczna z odzyskiem" else 0.0
        v_obl = v_inf_bud + v_min * (1 - eta)
        opis_v = (f"V̇ = 0,5·V̇_inf + V̇_nawiew·(1 − η) = {v_inf_bud:.1f} + {v_min:.1f}·(1 − {eta:.2f}) "
                  f"= {v_obl:.1f} m³/h (nawiew = n_min·V)")
    phi_V = 0.34 * v_obl * dT
    wentylacja = {"V": V, "n50": n50, "e": e_osl, "epsilon": eps, "V_inf": v_inf, "V_min": v_min,
                  "V_obl": v_obl, "eta": eta, "rodzaj": went}
    kroki += ["", "### 5. Wentylacja",
              f"- Rodzaj: {went}; n50 = {n50} 1/h (szczelność „{d.get('szczelnosc')}”), "
              f"e = {e_osl} (osłonięcie „{d.get('oslonienie')}”), ε = {eps}",
              f"- V̇_inf = 2 · V · n50 · e · ε = 2 · {V:.1f} · {n50} · {e_osl} · {eps} = {v_inf:.1f} m³/h",
              f"- V̇_min = n_min · V = {n['n_min']} · {V:.1f} = {v_min:.1f} m³/h",
              f"- {opis_v}",
              f"- Φ_V = 0,34 · V̇ · ΔT = 0,34 · {v_obl:.1f} · {dT:g} = **{phi_V:.0f} W**"]

    pow_ref = d.get("pow_ogrz_dekl") or geo.pow_ogrzewana
    phi_RH = n["f_RH"] * pow_ref
    phi_HL = phi_T + phi_V + phi_RH
    kroki += ["", "### 6. Wynik",
              f"- Φ_T = {phi_T:.0f} W, Φ_V = {phi_V:.0f} W, Φ_RH = {phi_RH:.0f} W",
              f"- **Φ_HL = {phi_HL:.0f} W = {phi_HL / 1000:.2f} kW** "
              f"({phi_HL / pow_ref:.0f} W/m² pow. ogrzewanej {pow_ref:.0f} m², {phi_HL / V:.1f} W/m³)"]

    # --- kontrole ---
    # Ostrzeżenia = tylko sytuacje, które zwykle oznaczają błąd danych. Przyjęte założenia trafiają do „zalozenia”.
    ostrzezenia: list[str] = []
    dekl = d.get("pow_ogrz_dekl")
    if dekl:
        roznica = (geo.pow_ogrzewana - dekl) / dekl
        opis = (f"Powierzchnia ogrzewana z obrysu ≈ {geo.pow_ogrzewana:.0f} m² różni się od deklarowanej "
                f"{dekl:g} m² o {roznica:+.0%}")
        if abs(roznica) > cfg["geometria"]["rozbieznosc_ostrzezenie"]:
            ostrzezenia.append(opis + " — prawdopodobnie błąd wymiarów lub liczby kondygnacji, sprawdź.")
        elif abs(roznica) > cfg["geometria"]["rozbieznosc_powierzchni"]:
            notatki.append(opis + " (zwykle część bryły jest nieogrzewana; wentylację liczono z powierzchni deklarowanej).")
    for e in elementy:
        if e.grupa in ("Strop pod strychem", "Dach skośny", "Stropodach") and e.U > 1.0:
            ostrzezenia.append(f"{e.grupa} bez ocieplenia (U = {e.U:.2f}) daje {e.phi / 1000:.1f} kW strat — "
                               "sprawdź, czy audyt nie pominął izolacji.")
    ostrzezenia += kontrole_wiarygodnosci(d, U, geo, a_okna_pion + a_okna_dach, phi_HL, cfg)
    if d.get("garaz", "Nie") != "Nie":
        ostrzezenia.append("Garaż w bryle budynku nie jest jeszcze uwzględniany osobno — policzono go jak część ogrzewaną "
                           "(wynik lekko zawyżony).")
    zalozenia = notatki + [f"{_etykieta(k)}: {d.get(k)} — {zr}" for k, zr in d.zrodla.items()
                 if k in POLA_WEJSCIOWE and zr in (ZRODLO_DOMYSLNE, "protokół – odczyt niepewny", "AI – do sprawdzenia", "wyliczone z audytu")
                 and d.get(k) is not None]

    wynik = Wynik(phi_HL, phi_T, phi_V, phi_RH, th_i, th_e, th_me, elementy, geo, wentylacja, U,
                  kroki, ostrzezenia, zalozenia, pow_ogrzewana=pow_ref)
    wynik.kontrola_paliwa = kontrola_paliwa(d, phi_HL / 1000, cfg)
    if wynik.kontrola_paliwa and wynik.kontrola_paliwa.get("ostrzezenie"):
        wynik.ostrzezenia.append(wynik.kontrola_paliwa["ostrzezenie"])
    return wynik
