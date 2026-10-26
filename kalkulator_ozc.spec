# Przepis PyInstallera: python -m PyInstaller kalkulator_ozc.spec  →  dist/Kalkulator OZC/Kalkulator OZC.exe
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

datas = [
    ("app.py", "."),
    ("konfiguracja.toml", "."),
    ("szablony/szablon_OZC.xlsx", "szablony"),
    ("assets/logo_flexipower.png", "assets"),
]
binaries = []
# app.py importuje moduły ozc w czasie działania — PyInstaller ich nie widzi, więc dołączamy cały pakiet.
hiddenimports = collect_submodules("ozc")
for pakiet in ("streamlit", "pypdfium2", "pypdfium2_raw"):
    p_datas, p_binaries, p_hidden = collect_all(pakiet)
    datas += p_datas
    binaries += p_binaries
    hiddenimports += p_hidden
datas += copy_metadata("streamlit") + collect_data_files("docx")  # domyślny szablon python-docx

a = Analysis(["start.py"], pathex=["."], datas=datas, binaries=binaries, hiddenimports=hiddenimports)
pyz = PYZ(a.pure)
# Bez okna konsoli: jego przypadkowe zamknięcie wyłączało program („Connection error” w przeglądarce).
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Kalkulator OZC", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Kalkulator OZC")
