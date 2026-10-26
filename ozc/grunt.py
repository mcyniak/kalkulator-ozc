"""Przenikanie do gruntu — wzory PN-EN ISO 13370 (stan ustalony).

Wynik traktujemy jako U_equiv w równaniu PN-EN 12831:
    Φ_T,ig = fg1 · fg2 · A · U_equiv · G_w · (θint − θe)
"""
from __future__ import annotations

import math

RSI_PODLOGA = 0.17
RSI_SCIANA = 0.13
RSE = 0.04


def wymiar_charakterystyczny(pole: float, obwod: float) -> float:
    """B' = A / (0,5 · P)."""
    return pole / (0.5 * obwod)


def _dt(grubosc_scian: float, u_podlogi: float, lam: float) -> float:
    """Grubość równoważna podłogi d_t = w + λ (Rsi + Rf + Rse)."""
    rf = max(0.0, 1 / u_podlogi - RSI_PODLOGA - RSE)
    return grubosc_scian + lam * (RSI_PODLOGA + rf + RSE)


def _u_podloga(b: float, d: float, lam: float) -> float:
    if d < b:
        return 2 * lam / (math.pi * b + d) * math.log(math.pi * b / d + 1)
    return lam / (0.457 * b + d)


def u_plyty_na_gruncie(b_prim: float, grubosc_scian: float, u_podlogi: float, lam: float = 2.0) -> float:
    """ISO 13370 p. 9.1 — podłoga na gruncie."""
    return _u_podloga(b_prim, _dt(grubosc_scian, u_podlogi, lam), lam)


def u_podlogi_piwnicy(b_prim: float, grubosc_scian: float, u_podlogi: float, z: float, lam: float = 2.0) -> float:
    """ISO 13370 p. 9.3.2 — podłoga piwnicy ogrzewanej na głębokości z."""
    return _u_podloga(b_prim, _dt(grubosc_scian, u_podlogi, lam) + 0.5 * z, lam)


def u_scian_piwnicy(z: float, grubosc_scian: float, u_podlogi: float, u_sciany: float, lam: float = 2.0) -> float:
    """ISO 13370 p. 9.3.3 — ściany piwnicy ogrzewanej poniżej terenu."""
    if z <= 0:
        return 0.0
    dt = _dt(grubosc_scian, u_podlogi, lam)
    rw = max(0.0, 1 / u_sciany - RSI_SCIANA - RSE)
    dw = lam * (RSI_SCIANA + rw + RSE)
    d = min(dt, dw)
    return 2 * lam / (math.pi * z) * (1 + 0.5 * d / (d + z)) * math.log(z / dw + 1)
