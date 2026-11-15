"""Pre Federal: arma data/prefederal.json (lo que lee la página) desde data/prefederal_fuente.json.

La fuente es legible y la edita la tarea diaria de Claude con lo que publica la prensa de cada provincia.
Acá se valida cada torneo y se pasa al mismo formato compacto de data/ligas.json:
    {"actualizado": ISO, "torneos": {"pf-<id>": {nombre, equipos, partidos, info, tablas, ...}}, "pendientes": [...]}
Si un torneo tiene un error, se avisa y se conserva la versión anterior de ese torneo: nunca frena al resto.
"""
import datetime as dt, json, os, re, sys

RAIZ = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
FUENTE = os.path.join(RAIZ, "data", "prefederal_fuente.json")
SALIDA = os.path.join(RAIZ, "data", "prefederal.json")


def compilar(t, orden):
    """Un torneo de la fuente -> documento compacto. Lanza ValueError con el motivo si algo está mal."""
    tid = str(t.get("id") or "")
    if not re.fullmatch(r"[a-z0-9]{2,8}", tid):
        raise ValueError(f"id inválido: {tid!r}")
    prov = (t.get("provincia") or "").strip()
    if not prov:
        raise ValueError("falta provincia")
    eq = {}
    for k, v in (t.get("equipos") or {}).items():
        if not re.fullmatch(r"[A-Z0-9]{2,5}", k):
            raise ValueError(f"id de equipo inválido: {k!r}")
        nombre, ciudad = (v + [""])[:2] if isinstance(v, list) else (v, "")
        if not str(nombre).strip():
            raise ValueError(f"equipo {k} sin nombre")
        eq[k] = [str(nombre).strip(), str(ciudad or "").strip()]
    if len(eq) < 2:
        raise ValueError("menos de dos equipos")
    partidos, info, vistos = [], {}, set()
    for p in t.get("partidos") or []:
        if len(p) < 4:
            raise ValueError(f"partido incompleto: {p}")
        f, h, loc, vis = p[0], p[1] or "", p[2], p[3]
        pl, pv = (p[4] if len(p) > 4 else None), (p[5] if len(p) > 5 else None)
        fase, sede = (p[6] if len(p) > 6 else "") or "", (p[7] if len(p) > 7 else "") or ""
        d = dt.date.fromisoformat(f)
        if h and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", h):
            raise ValueError(f"hora inválida en {p}")
        if loc not in eq or vis not in eq or loc == vis:
            raise ValueError(f"equipos inválidos en {p}")
        if (pl is None) != (pv is None):
            raise ValueError(f"resultado a medias en {p}")
        if pl is not None and (not isinstance(pl, int) or not isinstance(pv, int) or pl == pv or min(pl, pv) < 10 or max(pl, pv) > 200):
            raise ValueError(f"resultado raro en {p}")
        ik = f"{d:%y%m%d}-{loc}-{vis}"
        if ik in vistos:
            raise ValueError(f"partido repetido: {ik}")
        vistos.add(ik)
        s = f"{d:%y%m%d} {h.replace(':', '')} {loc} {vis}"
        if pl is not None:
            s += f" {pl} {pv}"
        partidos.append((f"{d:%y%m%d}{h or '99:99'}", s))
        x = {}
        if fase:
            x["fase"] = fase
        if sede:
            x["sede"] = sede
        if x:
            info[ik] = x
    tablas, solo_gp = [], True
    for tb in t.get("tablas") or []:
        filas = []
        for r in tb.get("filas") or []:
            if r[0] not in eq:
                raise ValueError(f"equipo desconocido en tabla: {r[0]}")
            n = [int(x) for x in r[1:]]
            if len(n) == 2:      # [PG, PP]
                n = [n[0] + n[1], n[0], n[1], 0, 0, 0]
            elif len(n) == 6:    # [PJ, PG, PP, PF, PC, Pts]
                solo_gp = False
            else:
                raise ValueError(f"fila de tabla inválida: {r}")
            if n[0] != n[1] + n[2] or min(n) < 0:
                raise ValueError(f"fila de tabla que no cierra: {r}")
            filas.append(" ".join([r[0]] + [str(x) for x in n]))
        if filas:
            tablas.append({"grupo": tb.get("grupo") or "Posiciones", "filas": ",".join(filas)})
    doc = {"nombre": f"Pre Federal · {prov}", "temporada": str(t.get("temporada") or ""), "ambito": "prefederal", "orden": 100 + orden,
           "nombresOk": True, "provincia": prov, "equipos": eq,
           "partidos": ",".join(s for _, s in sorted(partidos)), "tablas": tablas}
    if info:
        doc["info"] = info
    if tablas and solo_gp:
        doc["tablaTipo"] = "victorias"
    doc["tablaNota"] = t.get("tablaNota") or "Posiciones según la prensa local"
    for k in ("organiza", "etapa", "plazas", "formato", "playoffs", "tv", "fuente", "fuenteNombre"):
        if t.get(k):
            doc[k] = t[k]
    return "pf-" + tid, doc


def main():
    if not os.path.exists(FUENTE):
        print("prefederal: no hay fuente")
        return 0
    try:
        src = json.load(open(FUENTE, encoding="utf-8"))
    except Exception as e:  # un JSON roto no debe frenar el resto de la actualización
        print(f"prefederal: ERROR la fuente no es JSON válido: {e}")
        return 0
    viejo = {}
    if os.path.exists(SALIDA):
        try:
            viejo = json.load(open(SALIDA, encoding="utf-8")).get("torneos") or {}
        except Exception:
            viejo = {}
    torneos, errores = {}, []
    for i, t in enumerate(src.get("torneos") or []):
        try:
            k, doc = compilar(t, i)
            if k in torneos:
                raise ValueError("id repetido")
            doc["actualizado"] = src.get("actualizado") or ""
            torneos[k] = doc
        except Exception as e:
            k = "pf-" + str(t.get("id"))
            errores.append(f"{k}: {e}")
            if k in viejo:
                torneos[k] = viejo[k]
    out = {"actualizado": src.get("actualizado") or "", "torneos": torneos,
           "pendientes": [{"provincia": p.get("provincia", ""), "nota": p.get("nota", "")} for p in src.get("pendientes") or [] if p.get("provincia")]}
    if errores:
        out["errores"] = errores
    txt = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    if not os.path.exists(SALIDA) or open(SALIDA, encoding="utf-8").read() != txt:
        open(SALIDA, "w", encoding="utf-8").write(txt)
    print(f"prefederal: {len(torneos)} torneos, {sum(len([s for s in d['partidos'].split(',') if s]) for d in torneos.values())} partidos" + ("".join("\n  ERROR " + e for e in errores)))
    return 1 if errores and "--estricto" in sys.argv else 0


if __name__ == "__main__":
    sys.exit(main())
