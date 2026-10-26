"""Grunt — PN-EN ISO 13370, przeliczone ręcznie."""
import math

import pytest

from ozc import grunt


def test_wymiar_charakterystyczny():
    assert grunt.wymiar_charakterystyczny(184.0, 54.52) == pytest.approx(6.75, abs=0.01)


def test_plyta_dt_mniejsze_od_B():
    # protokół 24: B' = 6,75, w = 0,51, U podłogi 0,357
    rf = 1 / 0.357 - 0.17 - 0.04
    dt = 0.51 + 2.0 * (0.17 + rf + 0.04)
    assert dt < 6.75
    oczekiwane = 2 * 2.0 / (math.pi * 6.75 + dt) * math.log(math.pi * 6.75 / dt + 1)
    assert grunt.u_plyty_na_gruncie(6.75, 0.51, 0.357) == pytest.approx(oczekiwane)
    assert oczekiwane == pytest.approx(0.219, abs=0.001)


def test_plyta_dt_wieksze_od_B():
    # dobrze ocieplona podłoga, mały budynek: d_t ≥ B' → U = λ / (0,457 B' + d_t)
    rf = 1 / 0.15 - 0.21
    dt = 0.4 + 2.0 * (0.21 + rf)
    assert dt >= 3.0
    assert grunt.u_plyty_na_gruncie(3.0, 0.4, 0.15) == pytest.approx(2.0 / (0.457 * 3.0 + dt))


def test_piwnica_glebiej_to_mniejsze_U_podlogi():
    assert grunt.u_podlogi_piwnicy(5, 0.5, 0.5, 2.0) < grunt.u_plyty_na_gruncie(5, 0.5, 0.5)


def test_sciany_piwnicy():
    u_bez = grunt.u_scian_piwnicy(2.0, 0.5, 0.5, 2.0)
    u_z = grunt.u_scian_piwnicy(2.0, 0.5, 0.5, 0.3)
    assert 0 < u_z < u_bez
    assert grunt.u_scian_piwnicy(0, 0.5, 0.5, 2.0) == 0
