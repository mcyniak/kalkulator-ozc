"""Definicja pól danych wejściowych — wspólna dla szablonu Excel, modułu AI i kalkulatora.

Kolejność i sekcje odpowiadają protokołowi audytu. Pola `calc` to podgląd
w Excelu (formuły); kalkulator liczy te wartości samodzielnie w Pythonie.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Pole:
    klucz: str
    etykieta: str
    rodzaj: str  # text | num | int | list | calc
    jednostka: str = ""
    lista: str | None = None  # nazwa listy z [listy] lub zakresu biblioteki
    zakres: tuple[float, float] | None = None
    podpowiedz: str = ""
    domyslna_z: str | None = None  # klucz w [zalozenia]
    formula: str | None = None  # dla rodzaj == "calc"
    format: str = "0.00"


@dataclass
class Sekcja:
    tytul: str


# --- fragmenty formuł -------------------------------------------------------

def r_izolacji(mat: str, d: str, drewno: str = "0") -> str:
    """Opór warstwy izolacji; `drewno` — wyrażenie 0/1: izolacja między belkami."""
    m = f"MATCH({mat},lst_mat_izol,0)"
    lam = f"INDEX(bib_mi_lambda,{m})"
    lam_eq = f"IF({drewno}=1,(1-udzial_drewna)*{lam}+udzial_drewna*lambda_drewna,{lam})"
    return (f'IF({mat}="Brak",0,IF(INDEX(bib_mi_R,{m})>0,INDEX(bib_mi_R,{m}),'
            f'{d}/100/({lam_eq})))')


def r_muru(mat: str, d: str) -> str:
    return f"{d}/100/INDEX(bib_mk_lambda,MATCH({mat},lst_mat_konstr,0))"


def r_stropu(konstr: str, d: str) -> str:
    m = f"MATCH({konstr},lst_stropy,0)"
    return f"IF(INDEX(bib_st_R,{m})>0,INDEX(bib_st_R,{m}),{d}/100/INDEX(bib_st_lambda,{m}))"


def drewniany(konstr: str) -> str:
    return f"INDEX(bib_st_drewn,MATCH({konstr},lst_stropy,0))"


def u_lub_reczne(reczne: str, wyrazenie: str, wymagane: list[str]) -> str:
    """U wpisane ręcznie albo wyliczone; "–", gdy brakuje któregoś z pól `wymagane`."""
    brak = "OR(" + ",".join(f"ISBLANK({w})" for w in wymagane) + ")"
    return f'=IFERROR(IF(ISNUMBER({reczne}),{reczne},IF({brak},"–",{wyrazenie})),"–")'


U_SCIANA = u_lub_reczne("sciana_U_reczne",
    "1/(Rsi_poziomy+Rse+R_tynki+" + r_muru("sciana_material", "sciana_grubosc") + "+"
    + r_izolacji("sciana_ocieplenie", "sciana_ocieplenie_grubosc") + ")",
    ["sciana_material", "sciana_grubosc", "sciana_ocieplenie"])
U_FUND = u_lub_reczne("fund_U_reczne",
    "1/(Rsi_poziomy+Rse+" + r_muru("fund_material", "fund_grubosc") + "+"
    + r_izolacji("fund_izolacja", "fund_izolacja_grubosc") + ")",
    ["fund_material", "fund_grubosc", "fund_izolacja"])
U_PODLOGA = u_lub_reczne("podloga_U_reczne",
    "1/(Rsi_w_dol+Rse+(podloga_wylewka+podloga_chudy_beton)/100/lambda_beton+"
    + r_izolacji("podloga_izolacja", "podloga_izolacja_grubosc") + ")",
    ["podloga_izolacja", "podloga_izolacja_grubosc"])
U_STROP = u_lub_reczne("strop_U_reczne",
    "1/(Rsi_w_gore+Rse_strych+" + r_stropu("strop_konstrukcja", "strop_grubosc") + "+"
    + r_izolacji("strop_izolacja", "strop_izolacja_grubosc", drewniany("strop_konstrukcja")) + ")",
    ["strop_konstrukcja", "strop_izolacja", "strop_izolacja_grubosc"])
U_DACH = u_lub_reczne("dach_U_reczne",
    "1/(Rsi_w_gore+Rse_went+R_wykonczenie_dachu+"
    + r_izolacji("dach_izolacja", "dach_izolacja_grubosc", "1") + ")",
    ["dach_izolacja", "dach_izolacja_grubosc"])
U_STROP_PIWN = u_lub_reczne("piwn_strop_U_reczne",
    "1/(Rsi_w_dol+Rse_piwnica+" + r_stropu("piwn_strop_konstrukcja", "piwn_strop_grubosc") + "+"
    + r_izolacji("piwn_strop_izolacja", "piwn_strop_izolacja_grubosc",
                 drewniany("piwn_strop_konstrukcja")) + ")",
    ["piwn_strop_konstrukcja", "piwn_strop_izolacja", "piwn_strop_izolacja_grubosc"])
U_OKNA = u_lub_reczne("okna_U_reczne",
    "INDEX(bib_U_tab,MATCH(okna_rok,bib_progi_lat,1),MATCH(okna_typ,bib_U_naglowki,0))"
    '+IF(okna_material="Aluminium",dodatek_alu,0)',
    ["okna_rok", "okna_typ"])
U_DRZWI = u_lub_reczne("drzwi_U_reczne",
    'INDEX(bib_U_tab,MATCH(drzwi_rok,bib_progi_lat,1),MATCH("drzwi",bib_U_naglowki,0))',
    ["drzwi_rok"])


# --- definicja szablonu -----------------------------------------------------

POLA: list[Pole | Sekcja] = [
    Sekcja("0. Identyfikacja"),
    Pole("nr_protokolu", "Nr protokołu", "text"),
    Pole("data_audytu", "Data audytu", "text", podpowiedz="RRRR-MM-DD"),
    Pole("adres", "Adres / identyfikator", "text"),

    Sekcja("A. Lokalizacja i komfort"),
    Pole("gmina", "Gmina / miejscowość", "text"),
    Pole("strefa", "Strefa klimatyczna", "list", lista="lst_strefy",
         podpowiedz="Wg mapy stref PN-EN 12831 NA"),
    Pole("theta_e", "Projektowa temp. zewnętrzna θe", "calc", "°C",
         formula='=IFERROR(INDEX(bib_theta_e,MATCH(strefa,lst_strefy,0)),"–")', format="0"),
    Pole("t_int", "Temperatura wewnętrzna θint", "num", "°C", zakres=(16, 24),
         domyslna_z="t_int", format="0.0",
         podpowiedz="Norma: 20°C. Życzenie klienta wpisz w sekcji H, nie tutaj."),

    Sekcja("B. Budynek (protokół pkt 2)"),
    Pole("rok_budowy", "Rok budowy", "int", zakres=(1800, 2100), format="0"),
    Pole("liczba_osob", "Liczba osób", "int", zakres=(1, 20), format="0"),
    Pole("pow_ogrz_dekl", "Powierzchnia ogrzewana (deklarowana)", "num", "m²",
         zakres=(20, 2000), format="0.0", podpowiedz="Tylko do kontroli — wynik liczony z obrysu"),
    Pole("typ_zabudowy", "Typ zabudowy", "list", lista="typ_zabudowy", domyslna_z="typ_zabudowy"),
    Pole("dl_sciany_wspolnej", "Długość ściany wspólnej z sąsiadem", "num", "m",
         zakres=(0, 50), format="0.0", podpowiedz="Tylko bliźniak / szeregowiec"),
    Pole("konstrukcja", "Typ konstrukcji (3A)", "list", lista="konstrukcja"),
    Pole("piwnica", "Piwnica", "list", lista="piwnica"),
    Pole("h_piwnicy", "Wysokość piwnicy", "num", "m", zakres=(1.5, 4), format="0.00"),
    Pole("h_parter", "Wysokość parteru (w świetle)", "num", "m", zakres=(2, 5), format="0.00"),
    Pole("liczba_pieter", "Liczba pięter (bez poddasza)", "int", zakres=(0, 5),
         domyslna_z="liczba_pieter", format="0"),
    Pole("h_pietra", "Wysokość piętra (w świetle)", "num", "m", zakres=(2, 5), format="0.00"),
    Pole("poddasze_uzytkowe", "Poddasze użytkowe (ogrzewane)", "list", lista="tak_nie"),
    Pole("h_poddasza", "Wysokość poddasza (do sufitu)", "num", "m", zakres=(2, 4), format="0.00"),
    Pole("h_kolanka", "Wysokość ścianki kolankowej", "num", "m", zakres=(0, 2.5),
         domyslna_z="h_kolanka", format="0.00", podpowiedz="BRAK W OBECNYM PROTOKOLE"),
    Pole("strych_nieogrzewany", "Nad poddaszem / ostatnią kondygnacją nieogrzewany strych",
         "list", lista="tak_nie"),
    Pole("garaz", "Garaż w bryle budynku", "list", lista="garaz"),
    Pole("pow_garazu", "Powierzchnia garażu", "num", "m²", zakres=(0, 100), format="0.0"),

    Sekcja("C. Obrys i dach (szkic z protokołu)"),
    Pole("obrys", "Kształt obrysu", "list", lista="obrys"),
    Pole("dl_budynku", "Długość budynku (zewn.)", "num", "m", zakres=(3, 60), format="0.00"),
    Pole("szer_budynku", "Szerokość budynku (zewn.)", "num", "m", zakres=(3, 60), format="0.00"),
    Pole("pole_zabudowy", "Pole zabudowy (gdy obrys inny)", "num", "m²", zakres=(10, 2000),
         format="0.0"),
    Pole("obwod", "Obwód zewnętrzny (gdy obrys inny)", "num", "m", zakres=(10, 300), format="0.0"),
    Pole("dach_rodzaj", "Rodzaj dachu", "list", lista="dach_rodzaj"),
    Pole("kat_dachu", "Kąt nachylenia dachu", "num", "°", zakres=(0, 60), format="0"),
    Pole("kalenica", "Kierunek kalenicy", "list", lista="kalenica", domyslna_z="kalenica"),

    Sekcja("D1. Ściana zewnętrzna (3D)"),
    Pole("sciana_material", "Materiał konstrukcyjny", "list", lista="lst_mat_konstr"),
    Pole("sciana_grubosc", "Grubość muru", "num", "cm", zakres=(5, 100), format="0"),
    Pole("sciana_ocieplenie", "Ocieplenie", "list", lista="lst_mat_izol"),
    Pole("sciana_ocieplenie_grubosc", "Grubość ocieplenia", "num", "cm", zakres=(0, 40), format="0"),
    Pole("sciana_U_reczne", "U wpisane ręcznie (opcjonalnie)", "num", "W/m²K",
         zakres=(0.05, 6), podpowiedz="Wypełnij tylko, gdy znasz U — nadpisuje wyliczenie"),
    Pole("sciana_U", "U ściany", "calc", "W/m²K", formula=U_SCIANA),

    Sekcja("D2. Ściana fundamentowa / piwnicy (3E)"),
    Pole("fund_material", "Materiał", "list", lista="lst_mat_konstr"),
    Pole("fund_grubosc", "Grubość", "num", "cm", zakres=(5, 100), format="0"),
    Pole("fund_izolacja", "Izolacja", "list", lista="lst_mat_izol"),
    Pole("fund_izolacja_grubosc", "Grubość izolacji", "num", "cm", zakres=(0, 40), format="0"),
    Pole("fund_U_reczne", "U wpisane ręcznie (opcjonalnie)", "num", "W/m²K", zakres=(0.05, 6)),
    Pole("fund_U", "U ściany fundamentowej", "calc", "W/m²K", formula=U_FUND),

    Sekcja("D3. Podłoga na gruncie (3F)"),
    Pole("podloga_wylewka", "Wylewka betonowa", "num", "cm", zakres=(0, 30), format="0"),
    Pole("podloga_izolacja", "Izolacja", "list", lista="lst_mat_izol", domyslna_z="podloga_izolacja",
         podpowiedz="Protokół nie podaje materiału izolacji podłogi"),
    Pole("podloga_izolacja_grubosc", "Grubość izolacji", "num", "cm", zakres=(0, 40), format="0"),
    Pole("podloga_chudy_beton", "Chudy beton", "num", "cm", zakres=(0, 30), format="0"),
    Pole("woda_gruntowa_plytko", "Woda gruntowa płycej niż 1 m", "list", lista="tak_nie",
         domyslna_z="woda_gruntowa_plytko"),
    Pole("podloga_U_reczne", "U wpisane ręcznie (opcjonalnie)", "num", "W/m²K", zakres=(0.05, 6)),
    Pole("podloga_U", "U konstrukcji podłogi (bez gruntu)", "calc", "W/m²K", formula=U_PODLOGA),

    Sekcja("D4. Strop pod nieogrzewanym strychem (3F)"),
    Pole("strop_konstrukcja", "Konstrukcja", "list", lista="lst_stropy"),
    Pole("strop_grubosc", "Grubość konstrukcji", "num", "cm", zakres=(0, 50), format="0"),
    Pole("strop_izolacja", "Izolacja", "list", lista="lst_mat_izol"),
    Pole("strop_izolacja_grubosc", "Grubość izolacji", "num", "cm", zakres=(0, 60), format="0"),
    Pole("strop_U_reczne", "U wpisane ręcznie (opcjonalnie)", "num", "W/m²K", zakres=(0.05, 6)),
    Pole("strop_U", "U stropu pod strychem", "calc", "W/m²K", formula=U_STROP),

    Sekcja("D5. Dach skośny nad poddaszem (3G)"),
    Pole("dach_izolacja", "Izolacja (między krokwiami)", "list", lista="lst_mat_izol",
         domyslna_z="dach_izolacja", podpowiedz="Protokół nie podaje materiału izolacji dachu"),
    Pole("dach_izolacja_grubosc", "Grubość izolacji", "num", "cm", zakres=(0, 60), format="0"),
    Pole("dach_U_reczne", "U wpisane ręcznie (opcjonalnie)", "num", "W/m²K", zakres=(0.05, 6)),
    Pole("dach_U", "U dachu", "calc", "W/m²K", formula=U_DACH),

    Sekcja("D6. Strop nad nieogrzewaną piwnicą"),
    Pole("piwn_strop_konstrukcja", "Konstrukcja", "list", lista="lst_stropy"),
    Pole("piwn_strop_grubosc", "Grubość konstrukcji", "num", "cm", zakres=(0, 50), format="0"),
    Pole("piwn_strop_izolacja", "Izolacja", "list", lista="lst_mat_izol"),
    Pole("piwn_strop_izolacja_grubosc", "Grubość izolacji", "num", "cm", zakres=(0, 40), format="0"),
    Pole("piwn_strop_U_reczne", "U wpisane ręcznie (opcjonalnie)", "num", "W/m²K", zakres=(0.05, 6)),
    Pole("piwn_strop_U", "U stropu nad piwnicą", "calc", "W/m²K", formula=U_STROP_PIWN),

    Sekcja("E. Okna (3H + tabela okien)"),
    Pole("okna_male", "Okna małe (do 1 m²) — suma elewacji", "int", "szt.", zakres=(0, 100), format="0"),
    Pole("okna_srednie", "Okna średnie (1–2 m²) — suma elewacji", "int", "szt.", zakres=(0, 100), format="0"),
    Pole("okna_duze", "Okna duże (pow. 2 m²) — suma elewacji", "int", "szt.", zakres=(0, 100), format="0"),
    Pole("okna_dachowe", "Okna dachowe", "int", "szt.", zakres=(0, 50), domyslna_z="okna_dachowe",
         format="0", podpowiedz="BRAK W OBECNYM PROTOKOLE — przy poddaszu użytkowym sprawdzić"),
    Pole("pow_okna_male", "Przyjęta pow. okna małego", "num", "m²", zakres=(0.1, 1.5),
         domyslna_z="pow_okna_male", format="0.00"),
    Pole("pow_okna_srednie", "Przyjęta pow. okna średniego", "num", "m²", zakres=(0.8, 2.5),
         domyslna_z="pow_okna_srednie", format="0.00"),
    Pole("pow_okna_duze", "Przyjęta pow. okna dużego", "num", "m²", zakres=(1.5, 8),
         domyslna_z="pow_okna_duze", format="0.00"),
    Pole("pow_okna_dachowe", "Przyjęta pow. okna dachowego", "num", "m²", zakres=(0.3, 3),
         domyslna_z="pow_okna_dachowe", format="0.00"),
    Pole("okna_typ", "Typ szyb", "list", lista="okna_typ"),
    Pole("okna_material", "Materiał ram", "list", lista="okna_material"),
    Pole("okna_rok", "Rok montażu okien", "int", zakres=(1900, 2100), format="0"),
    Pole("okna_U_reczne", "U wpisane ręcznie (opcjonalnie)", "num", "W/m²K", zakres=(0.5, 6)),
    Pole("okna_U", "U okien", "calc", "W/m²K", formula=U_OKNA),
    Pole("okna_pow", "Łączna powierzchnia okien", "calc", "m²", format="0.0",
         formula='=IFERROR(okna_male*pow_okna_male+okna_srednie*pow_okna_srednie'
                 '+okna_duze*pow_okna_duze+okna_dachowe*pow_okna_dachowe,"–")'),

    Sekcja("F. Drzwi zewnętrzne (3I)"),
    Pole("drzwi_ilosc", "Ilość", "int", "szt.", zakres=(0, 10), format="0"),
    Pole("drzwi_szer", "Szerokość", "num", "m", zakres=(0.6, 3), format="0.00"),
    Pole("drzwi_wys", "Wysokość", "num", "m", zakres=(1.8, 3), format="0.00"),
    Pole("drzwi_material", "Materiał", "list", lista="drzwi_material"),
    Pole("drzwi_rok", "Rok montażu", "int", zakres=(1900, 2100), format="0"),
    Pole("drzwi_U_reczne", "U wpisane ręcznie (opcjonalnie)", "num", "W/m²K", zakres=(0.5, 6)),
    Pole("drzwi_U", "U drzwi", "calc", "W/m²K", formula=U_DRZWI),
    Pole("drzwi_pow", "Łączna powierzchnia drzwi", "calc", "m²", format="0.0",
         formula='=IFERROR(drzwi_ilosc*drzwi_szer*drzwi_wys,"–")'),

    Sekcja("G. Wentylacja i szczelność (pkt 2, 3B, 3C)"),
    Pole("wentylacja", "Rodzaj wentylacji", "list", lista="wentylacja"),
    Pole("sprawnosc_odzysku", "Sprawność odzysku ciepła", "num", "%", zakres=(0, 95), format="0",
         podpowiedz="Tylko wentylacja z odzyskiem"),
    Pole("szczelnosc", "Stopień szczelności (3B)", "list", lista="szczelnosc"),
    Pole("oslonienie", "Klasa osłonięcia (3C)", "list", lista="oslonienie"),

    Sekcja("H. Kontrola i dane do doboru pompy (nie wpływa na Φ_HL)"),
    Pole("paliwo_rodzaj", "Obecne paliwo", "list", lista="paliwo"),
    Pole("paliwo_ilosc", "Roczne zużycie paliwa", "num", zakres=(0, 100000), format="0.0"),
    Pole("paliwo_jednostka", "Jednostka zużycia", "list", lista="jednostka"),
    Pole("moc_protokol", "Moc pompy wybrana w protokole", "num", "kW", zakres=(0, 50), format="0.0"),
    Pole("instalacja", "Instalacja c.o.", "list", lista="instalacja"),
    Pole("temp_zadana", "Temperatura żądana przez klienta", "num", "°C", zakres=(16, 26), format="0.0"),
    Pole("temp_cwu", "Temperatura c.w.u.", "num", "°C", zakres=(40, 65), format="0"),
    Pole("moc_przylacza", "Moc przyłączeniowa", "num", "kW", zakres=(0, 100), format="0.0"),
    Pole("uwagi", "Uwagi ogólne", "text"),
]



POLA_WEJSCIOWE: dict[str, Pole] = {p.klucz: p for p in POLA if isinstance(p, Pole) and p.rodzaj != "calc"}
