"""Pasa la base del artifact de Doble (exportada con ArtifactData list) a data/*.json.

Uso: python3 scripts/exportar_db.py CARPETA_EXPORT
CARPETA_EXPORT tiene subcarpetas ligas/, noticias/, extra/, escudos/ con un .json por documento.
No toca data/nba.json, data/bp.json ni data/fotos.json: esos los mantiene GitHub Actions.
"""
import glob, json, os, sys

src = sys.argv[1]
D = os.path.join(os.path.dirname(__file__), "..", "data")


def coll(name):
    r = {}
    for p in sorted(glob.glob(f"{src}/{name}/*.json")):
        r[os.path.basename(p)[:-5]] = json.load(open(p, encoding="utf-8"))
    return r


def w(n, o):
    if not o:
        print("vacío, no se escribe:", n); return
    json.dump(o, open(os.path.join(D, n + ".json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("ok", n)


w("ligas", coll("ligas"))
w("noticias", coll("noticias"))
w("escudos", {k: v.get("eq", {}) for k, v in coll("escudos").items()})
ex = coll("extra")
lg = ex.get("logos") or {}
if lg:
    w("logos", {"comp": lg.get("comp", {}), "tv": lg.get("tv", {}), "flag": lg.get("flag", {})})
if ex.get("argentinos") or ex.get("formativas"):
    w("extra", {"argentinos": ex.get("argentinos"), "formativas": ex.get("formativas")})
