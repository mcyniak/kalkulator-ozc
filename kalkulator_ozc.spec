# Przepis PyInstallera: python -m PyInstaller kalkulator_ozc.spec  →  dist/Kalkulator OZC/Kalkulator OZC.exe
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = [
    ("app.py", "."),
    ("konfiguracja.toml", "."),
    ("szablony/szablon_OZC.xlsx", "szablony"),
]
binaries = []
hiddenimports = []
st_datas, st_binaries, st_hidden = collect_all("streamlit")
datas += st_datas + copy_metadata("streamlit")
binaries += st_binaries
hiddenimports += st_hidden

a = Analysis(["start.py"], pathex=["."], datas=datas, binaries=binaries, hiddenimports=hiddenimports)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Kalkulator OZC", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="Kalkulator OZC")
