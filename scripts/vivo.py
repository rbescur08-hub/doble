"""Resultados del día (data/vivo.json) sobre la base (data/ligas.json).

data/vivo.json lo escribe GitHub Actions cada ~30 min con los partidos y tablas oficiales
de los últimos días (Liga Nacional, Liga Argentina, Liga Femenina, Liga de Desarrollo y Euroliga):
    {"lnb": {"p": ["261028 2030 88 80 58 80", ...], "tablas": [...], "act": "ISO"}, ...}

La base la sigue cargando Claude de noche; esto solo adelanta lo que pasó en el día.
La misma lógica está copiada en app.html (función aplicarVivo): si cambiás una, cambiá la otra.
"""
import datetime as dt


def _dia(s):
    return dt.date(2000 + int(s[:2]), int(s[2:4]), int(s[4:6]))


def aplicar(ligas, vivo):
    for l, v in (vivo or {}).items():
        doc = ligas.get(l)
        if not doc or not isinstance(v, dict):
            continue
        eq = doc.get("equipos") or {}
        arr = [s for s in str(doc.get("partidos") or "").split(",") if s.strip()]
        partes = [s.split(" ") for s in arr]
        info = doc.get("info") or {}
        for linea in v.get("p") or []:
            p = linea.split(" ")
            if len(p) < 4 or p[2] not in eq or p[3] not in eq:
                continue
            idx = next((i for i, q in enumerate(partes) if q[0] == p[0] and q[2] == p[2] and q[3] == p[3]), -1)
            if idx < 0:  # reprogramado: mismo cruce, sin resultado, a menos de 20 días
                idx = next((i for i, q in enumerate(partes)
                            if q[2] == p[2] and q[3] == p[3] and len(q) < 6
                            and abs((_dia(q[0]) - _dia(p[0])).days) <= 20), -1)
            if idx < 0:
                arr.append(linea); partes.append(p)
                continue
            q = partes[idx]
            if len(q) >= 6 and len(p) < 6:  # nunca se borra un resultado cargado
                continue
            if not p[1] and q[1]:
                p[1] = q[1]
            viejo, nuevo = f"{q[0]}-{q[2]}-{q[3]}", f"{p[0]}-{p[2]}-{p[3]}"
            if viejo != nuevo and viejo in info:
                info[nuevo] = info.pop(viejo)
            arr[idx] = " ".join(p); partes[idx] = p
        orden = sorted(zip(arr, partes), key=lambda x: (x[1][0], x[1][1] or "9999"))
        doc["partidos"] = ",".join(a for a, _ in orden)
        if info:
            doc["info"] = info
        if v.get("tablas"):
            base = {t.get("grupo"): t for t in doc.get("tablas") or []}
            doc["tablas"] = [{**base.get(t.get("grupo"), {}), **t} for t in v["tablas"]]
    return ligas
