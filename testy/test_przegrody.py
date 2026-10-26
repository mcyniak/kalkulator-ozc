"""U przegród — wartości policzone ręcznie i zgodne z podglądem w Excelu (protokół 24)."""
import pytest

from ozc import przegrody


def test_sciana_pustak_ze_styropianem():
    # 1 / (0,13 + 0,04 + 0,03 + 0,40/0,40 + 0,08/0,040) = 1 / 3,2
    assert przegrody.u_sciany("Pustak keramzytobetonowy", 40, "Styropian EPS", 8) == pytest.approx(0.3125)


def test_sciana_bez_izolacji_i_z_pustka():
    # cegła 38 cm: 1 / (0,20 + 0,38/0,77)
    assert przegrody.u_sciany("Cegła ceramiczna pełna", 38, "Brak", None) == pytest.approx(1 / (0.2 + 0.38 / 0.77))
    # pustka ma stały opór 0,18 niezależnie od grubości
    assert przegrody.u_sciany("Cegła ceramiczna pełna", 38, "Pustka powietrzna", 5) == pytest.approx(
        1 / (0.2 + 0.38 / 0.77 + 0.18))


def test_podloga():
    # 1 / (0,17 + 0,04 + 0,15/1,7 + 0,10/0,040)
    assert przegrody.u_podlogi(10, "Styropian EPS", 10, 5) == pytest.approx(1 / (0.21 + 0.15 / 1.7 + 2.5))


def test_strop_drewniany_z_welna_miedzy_belkami():
    lam_eq = 0.9 * 0.040 + 0.1 * 0.13  # 0,049
    oczekiwane = 1 / (0.10 + 0.10 + 0.10 + 0.25 / lam_eq)
    assert przegrody.u_stropu_pod_strychem("Drewniany", 5, "Wełna mineralna", 25) == pytest.approx(oczekiwane)
    assert oczekiwane == pytest.approx(0.185, abs=0.001)


def test_strop_zelbetowy_bez_wplywu_drewna():
    oczekiwane = 1 / (0.10 + 0.10 + 0.14 / 2.3 + 0.05 / 0.040)
    assert przegrody.u_stropu_pod_strychem("Żelbetowy monolityczny", 14, "Styropian EPS", 5) == pytest.approx(oczekiwane)


def test_dach():
    lam_eq = 0.9 * 0.040 + 0.1 * 0.13
    assert przegrody.u_dachu("Wełna mineralna", 25) == pytest.approx(1 / (0.10 + 0.10 + 0.05 + 0.25 / lam_eq))


@pytest.mark.parametrize("typ, rok, material, U", [
    ("dwuszybowe", 2000, "Plastik", 2.0),
    ("dwuszybowe", 1999, "Plastik", 2.6),
    ("dwuszybowe", 2010, "Drewno", 1.4),
    ("dwuszybowe", 2005, "Aluminium", 2.3),
    ("trzyszybowe", 2020, "Plastik", 0.9),
    ("jednoszybowe", 1970, "Drewno", 5.0),
])
def test_okna_wg_roku(typ, rok, material, U):
    assert przegrody.u_okien(typ, rok, material) == pytest.approx(U)


def test_drzwi():
    assert przegrody.u_drzwi(2000) == 2.6
    assert przegrody.u_drzwi(2018) == 1.3
