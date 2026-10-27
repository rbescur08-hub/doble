"""Actualización automática de Doble (corre en GitHub Actions, sin Claude).

- NBA: partidos, resultados, TV en Argentina y tablas desde la API pública de ESPN -> data/nba.json
- Basquetpass: qué partidos de la base transmite -> data/bp.json
- Fotos de noticias: imagen de cada nota de data/noticias.json -> data/fotos.json
- Estado de cada paso -> data/estado.json

Cada paso es independiente: si uno falla, los demás siguen y el error queda en estado.json.
"""
import base64, datetime as dt, html, io, json, os, re, sys, traceback, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from nombres import best  # noqa: E402

RAIZ = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(RAIZ, "data")
AR = dt.timezone(dt.timedelta(hours=-3))
AHORA = dt.datetime.now(AR)
HOY = AHORA.date()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def leer(nombre, defecto=None):
    p = os.path.join(DATA, nombre)
    if not os.path.exists(p):
        return defecto
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def guardar(nombre, obj):
    p = os.path.join(DATA, nombre)
    nuevo = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if os.path.exists(p) and open(p, encoding="utf-8").read() == nuevo:
        return False
    with open(p, "w", encoding="utf-8") as f:
        f.write(nuevo)
    return True


def get(url, binario=False, timeout=25, headers=None):
    h = {"User-Agent": UA, "Accept-Language": "es-AR,es;q=0.9,en;q=0.8"}
    h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        b = r.read()
        return b if binario else b.decode(r.headers.get_content_charset() or "utf-8", "replace")


def get_json(url, intentos=3):
    import time
    for i in range(intentos):
        try:
            return json.loads(get(url, headers={"Accept": "application/json"}))
        except Exception:
            if i == intentos - 1:
                raise
            time.sleep(3 * (i + 1))


def iso_ar(s):
    """'2026-10-28T00:00Z' -> datetime en hora argentina"""
    s = s.replace("Z", "+00:00")
    if re.search(r"T\d\d:\d\d\+", s):
        s = s.replace("+", ":00+", 1)
    return dt.datetime.fromisoformat(s).astimezone(AR)


def ymd(d):
    return d.strftime("%y%m%d")


# ---------------------------------------------------------------- NBA
TV_NBA = [  # (contiene, canal en Argentina)
    (("NBC", "Peacock"), "HBO Max · TNT Sports"),
    (("ESPN", "ABC"), "ESPN · Disney+ Premium"),
    (("Prime Video", "Prime"), "Prime Video"),
    (("NBA TV",), "NBA TV"),
]
IGNORAR_TV = ("NBCSN",)
CONF = {"Eastern Conference": "Conferencia Este", "Western Conference": "Conferencia Oeste"}


def tv_ar(comp):
    out = []
    for b in comp.get("geoBroadcasts") or []:
        if (b.get("market") or {}).get("type") != "National":
            continue
        n = (b.get("media") or {}).get("shortName") or ""
        if not n or n in IGNORAR_TV:
            continue
        for claves, canal in TV_NBA:
            if any(k in n for k in claves) and canal not in out:
                out.append(canal)
                break
    return " · ".join(out)


def nba(estado):
    doc = leer("nba.json") or (leer("ligas.json", {}) or {}).get("nba")
    if not doc:
        raise RuntimeError("no hay documento base de la NBA")
    partidos = {}
    for s in str(doc.get("partidos", "")).split(","):
        p = s.split(" ")
        if len(p) >= 4:
            partidos[f"{p[0]}-{p[2]}-{p[3]}"] = s
    info = dict(doc.get("info") or {})
    vistos, nuevos, errores = set(), 0, []
    for k in range(-3, 25):
        dia = HOY + dt.timedelta(days=k)
        try:
            sb = get_json(f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={dia:%Y%m%d}")
        except Exception as e:  # un día que falla no frena el resto
            errores.append(f"{dia}: {e}")
            continue
        for ev in sb.get("events") or []:
            comp = (ev.get("competitions") or [{}])[0]
            cs = {c.get("homeAway"): c for c in comp.get("competitors") or []}
            if "home" not in cs or "away" not in cs:
                continue
            h, a = cs["home"]["team"]["abbreviation"], cs["away"]["team"]["abbreviation"]
            for c in (cs["home"], cs["away"]):
                t = c["team"]
                if t["abbreviation"] not in doc["equipos"]:
                    doc["equipos"][t["abbreviation"]] = [t.get("displayName") or t["abbreviation"], ((comp.get("venue") or {}).get("fullName") or "") if c is cs["home"] else ""]
            f = iso_ar(ev["date"])
            ik = f"{ymd(f)}-{h}-{a}"
            linea = f"{ymd(f)} {f:%H%M} {h} {a}"
            if ((ev.get("status") or {}).get("type") or {}).get("completed"):
                linea += f" {int(float(cs['home'].get('score') or 0))} {int(float(cs['away'].get('score') or 0))}"
            if partidos.get(ik) != linea:
                nuevos += 1
            partidos[ik] = linea
            vistos.add(ik)
            tv = tv_ar(comp)
            if tv:
                info.setdefault(ik, {})["tv"] = tv
    if len(errores) > 10:
        raise RuntimeError("ESPN no respondió: " + "; ".join(errores[:3]))
    # partidos del rango consultado que ya no figuran (postergados o reprogramados)
    desde, hasta = ymd(HOY - dt.timedelta(days=2)), ymd(HOY + dt.timedelta(days=23))
    for ik in list(partidos) if not errores else []:  # si falló algún día, no se borra nada
        d = ik[:6]
        if desde <= d <= hasta and ik not in vistos and len(partidos[ik].split(" ")) < 6:
            del partidos[ik]
            info.pop(ik, None)

    # tablas
    try:
        st = get_json("https://site.api.espn.com/apis/v2/sports/basketball/nba/standings")
        pf, pc = {}, {}
        for s in partidos.values():
            p = s.split(" ")
            if len(p) >= 6 and p[4] and p[5]:
                pf[p[2]] = pf.get(p[2], 0) + int(p[4]); pc[p[2]] = pc.get(p[2], 0) + int(p[5])
                pf[p[3]] = pf.get(p[3], 0) + int(p[5]); pc[p[3]] = pc.get(p[3], 0) + int(p[4])
        tablas = []
        for ch in st.get("children") or []:
            filas = []
            for en in (ch.get("standings") or {}).get("entries") or []:
                stats = {x.get("name"): x.get("value") for x in en.get("stats") or []}
                w, l = int(stats.get("wins") or 0), int(stats.get("losses") or 0)
                ab = en["team"]["abbreviation"]
                filas.append((w / (w + l) if w + l else 0, w, ab, f"{ab} {w + l} {w} {l} {pf.get(ab, 0)} {pc.get(ab, 0)} {w}"))
            filas.sort(key=lambda x: (-x[0], -x[1], x[2]))
            if filas:
                tablas.append({"grupo": CONF.get(ch.get("name"), ch.get("name")), "filas": ",".join(f[3] for f in filas)})
        if len(tablas) == 2:
            doc["tablas"] = tablas
    except Exception as e:
        errores.append(f"tablas: {e}")

    orden = sorted(partidos.values(), key=lambda s: (s.split(" ")[0], s.split(" ")[1] or "9999"))
    doc["partidos"] = ",".join(orden)
    doc["info"] = {k: v for k, v in info.items() if k in partidos}
    doc["actualizado"] = AHORA.isoformat(timespec="seconds")
    cambio = guardar("nba.json", doc)
    estado["nba"] = {"ok": True, "cambios": nuevos, "partidos": len(orden), "avisos": errores[:5]}
    return cambio


# ---------------------------------------------------------------- Basquetpass
TORNEOS = {"1": "lnb", "2": "la", "3": "lfb", "11": "ldd", "29": "lsb", "98": "acb", "102": "el", "40": "bcla", "45": "sel"}


def basquetpass(estado):
    ligas = leer("ligas.json", {})
    mapa = json.load(open(os.path.join(os.path.dirname(__file__), "bp_map.json"), encoding="utf-8"))
    j = get_json("https://static.tbcast.com/content_AR_AR.json")
    d = j.get("d", j)
    desde = AHORA.timestamp() - 2 * 86400
    marcados, sin_match = {}, []
    for e in d.get("content") or []:
        liga = TORNEOS.get(str(e.get("tournament")))
        if not liga or not e.get("team_1_name") or liga not in ligas:
            continue
        try:
            ts = int(e["date"])
        except Exception:
            continue
        if ts < desde:
            continue
        doc = ligas[liga]
        eq = doc.get("equipos") or {}

        def idde(bid, nombre):
            i = (mapa.get(liga) or {}).get(str(bid))
            if i:
                return i
            i, s = best(nombre, eq)
            return i if s >= 1 else None

        h, a = idde(e.get("team_1"), e["team_1_name"]), idde(e.get("team_2"), e["team_2_name"])
        f = dt.datetime.fromtimestamp(ts, AR)
        ok = None
        if h and a:
            for s in str(doc.get("partidos", "")).split(","):
                p = s.split(" ")
                if len(p) < 4 or p[2] != h or p[3] != a:
                    continue
                if p[0] != ymd(f) and p[0] != ymd(f + dt.timedelta(hours=2)):
                    continue
                if p[1]:
                    t = dt.datetime.strptime(p[0] + p[1], "%y%m%d%H%M").replace(tzinfo=AR)
                    if abs((t - f).total_seconds()) > 2 * 3600:
                        continue
                ok = f"{p[0]}-{h}-{a}"
                break
        if ok:
            marcados.setdefault(liga, [])
            if ok not in marcados[liga]:
                marcados[liga].append(ok)
        else:
            sin_match.append(f"{liga} {f:%d/%m %H:%M} {e['team_1_name']} vs {e['team_2_name']}")
    cambio = guardar("bp.json", {k: sorted(v) for k, v in sorted(marcados.items())})
    estado["basquetpass"] = {"ok": True, "marcados": sum(len(v) for v in marcados.values()), "sin_partido_en_base": sin_match[:15]}
    return cambio


# ---------------------------------------------------------------- Fotos
def fnv(s):
    h = 0x811C9DC5
    for ch in s:
        for unit in ([ord(ch)] if ord(ch) < 0x10000 else [0xD800 + ((ord(ch) - 0x10000) >> 10), 0xDC00 + ((ord(ch) - 0x10000) & 0x3FF)]):
            h ^= unit
            h = (h * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


EVITAR = ("logo", "banner", "icon", "facebook", "avatar", "sprite")


def imagen_de(url, pagina):
    for pat in (r'<meta[^>]+property=["\']og:image(?::url)?["\'][^>]*content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*property=["\']og:image',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)'):
        m = re.search(pat, pagina, re.I)
        if m:
            return urllib.parse.urljoin(url, html.unescape(m.group(1)))
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+\.(?:jpe?g|png|webp)[^"\']*)', pagina, re.I):
        src = m.group(1)
        if not any(x in src.lower() for x in EVITAR):
            return urllib.parse.urljoin(url, html.unescape(src))
    return None


def a_webp(b):
    from PIL import Image
    im = Image.open(io.BytesIO(b)).convert("RGB")
    w, h = im.size
    if w / h > 16 / 9:
        nw = int(h * 16 / 9); x = (w - nw) // 2
        im = im.crop((x, 0, x + nw, h))
    else:
        nh = int(w * 9 / 16); y = int((h - nh) * 0.3)
        im = im.crop((0, y, w, y + nh))
    im = im.resize((480, 270), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "WEBP", quality=72)
    return "data:image/webp;base64," + base64.b64encode(out.getvalue()).decode()


def fotos(estado):
    noticias = leer("noticias.json", {})
    fs = leer("fotos.json", {})
    # formato: hash -> [fecha, dataURI]  (las viejas pueden ser solo dataURI)
    fs = {k: (v if isinstance(v, list) else [HOY.isoformat(), v]) for k, v in fs.items()}
    limite = (HOY - dt.timedelta(days=3)).isoformat()
    cargadas, fallas = 0, []
    for fecha, dia in sorted(noticias.items()):
        if fecha < limite:
            continue
        for it in (dia or {}).get("items") or []:
            u = (it.get("u") or "").split("#")[0]
            if not u:
                continue
            k = fnv(u)
            if k in fs:
                continue
            try:
                src = imagen_de(u, get(u))
                if not src:
                    raise RuntimeError("sin imagen")
                fs[k] = [fecha, a_webp(get(src, binario=True, headers={"Referer": u}))]
                cargadas += 1
            except Exception as e:
                fallas.append(f"{urllib.parse.urlparse(u).netloc}: {str(e)[:60]}")
    viejo = (HOY - dt.timedelta(days=14)).isoformat()
    fs = {k: v for k, v in fs.items() if v[0] >= viejo}
    cambio = guardar("fotos.json", fs)
    estado["fotos"] = {"ok": True, "cargadas": cargadas, "total": len(fs), "fallas": fallas[:15]}
    return cambio


# ---------------------------------------------------------------- main
def main():
    pasos = sys.argv[1:] or ["nba", "basquetpass", "fotos"]
    estado = leer("estado.json", {}) or {}
    for nombre in pasos:
        fn = {"nba": nba, "basquetpass": basquetpass, "fotos": fotos}[nombre]
        try:
            fn(estado)
        except Exception as e:
            traceback.print_exc()
            estado[nombre] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
        estado[nombre]["hora"] = AHORA.isoformat(timespec="seconds")
        print(nombre, json.dumps(estado[nombre], ensure_ascii=False)[:400])
    guardar("estado.json", estado)


if __name__ == "__main__":
    main()
