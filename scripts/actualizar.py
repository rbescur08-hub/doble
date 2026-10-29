"""Actualización automática de Doble (corre en GitHub Actions, sin Claude).

- Resultados del día: Liga Nacional, Liga Argentina, Liga Femenina, Liga de Desarrollo (AdC) y Euroliga
  (API oficial) -> data/vivo.json; la página los aplica sobre la base (scripts/vivo.py y app.html)
- NBA: partidos, resultados, TV en Argentina y tablas desde la API pública de ESPN -> data/nba.json
- Basquetpass: qué partidos de la base transmite -> data/bp.json
- Escudos de equipos nuevos (AdC, Euroliga, ESPN) -> data/escudos_auto.json
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
    url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")  # URLs con ñ o tildes
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


# ---------------------------------------------------------------- Resultados del día
ADC = "https://www.laliganacional.com.ar"
ADC_LIGAS = {"lnb": "laliga", "la": "laligaargentina", "lfb": "lfb", "ldd": "ligaproximo"}
ESCUDOS_ADC = {}  # liga -> {idClub: url del escudo}, lo usa el paso de escudos
FINAL_TRAS = dt.timedelta(hours=2)  # la AdC no marca "final": un marcador cuenta 2 h después del inicio


def _limpio(s):
    return html.unescape(re.sub(r"<[^>]+>|\s+", " ", s)).strip()


def adc_partidos(liga, slug):
    desde, hasta = HOY - dt.timedelta(days=3), HOY + dt.timedelta(days=14)
    h = get(f"{ADC}/{slug}/fixture?handler=ProximosPartidos&fechaInicio={desde}&fechaFin={hasta}")
    filas = re.findall(r'<tr class="fila-tabla-calendarios.*?</tr>', h, re.S)
    if not filas and "tabla-calendarios" not in h:
        raise RuntimeError(f"{slug}: la página del fixture cambió")
    out = []
    for r in filas:
        ids = re.findall(r'/equipo/(\d+)/', r)
        pts = [_limpio(x) for x in re.findall(r'<td class="resultados">(.*?)</td>', r, re.S)]
        m = re.search(r'class="fecha-campo[^"]*">\s*<strong>\s*(\d\d)/(\d\d)/(\d{4})\s*(\d\d:\d\d)?', r)
        for i, src in re.findall(r'src="/escudos/(\d+)/(\d+)"', r):
            ESCUDOS_ADC.setdefault(liga, {})[i] = f"{ADC}/escudos/{i}/{src}"
        if len(ids) < 2 or not m:
            continue
        hora = (m.group(4) or "").replace(":", "")
        if hora == "0000":  # la AdC muestra 00:00 cuando todavía no hay horario
            hora = ""
        linea = f"{m.group(3)[2:]}{m.group(2)}{m.group(1)} {hora} {ids[0]} {ids[-1]}"
        if len(pts) == 2 and pts[0].isdigit() and pts[1].isdigit() and (pts[0], pts[1]) != ("0", "0") and hora:
            inicio = dt.datetime.strptime(linea[:11], "%y%m%d %H%M").replace(tzinfo=AR)
            if AHORA - inicio >= FINAL_TRAS:
                linea += f" {pts[0]} {pts[1]}"
        out.append(linea)
    return out


def adc_tablas(liga, slug, doc):
    tablas = []
    for t in doc.get("tablas") or []:
        if not t.get("faseId") or not t.get("grupoId"):
            return None
        h = get(f"{ADC}/{slug}/tabla-posiciones?handler=Clasificacion&faseId={t['faseId']}&grupoId={t['grupoId']}")
        filas = []
        for r in re.findall(r'<tr class="datos-estadisticos">(.*?)</tr>', h, re.S):
            i = re.search(r'/equipo/(\d+)/', r)
            n = [_limpio(x) for x in re.findall(r"<td>(.*?)</td>", r, re.S)]
            for e_id, src in re.findall(r'src="/escudos/(\d+)/(\d+)"', r):
                ESCUDOS_ADC.setdefault(liga, {})[e_id] = f"{ADC}/escudos/{e_id}/{src}"
            # columnas: posición, PJ, PG, PP, PF, PC, PTOS, %VICT
            if i and len(n) >= 7 and all(x.isdigit() for x in n[1:7]):
                filas.append(f"{i.group(1)} {' '.join(n[1:7])}")
        if not filas:
            return None  # una tabla vacía: mejor dejar la de la base
        tablas.append({"grupo": t.get("grupo"), "filas": ",".join(filas)})
    return tablas or None


def euroliga():
    j = get_json("https://api-live.euroleague.net/v2/competitions/E/seasons/E2026/games")
    desde, hasta = HOY - dt.timedelta(days=3), HOY + dt.timedelta(days=14)
    out, ultima = [], 0
    for g in j.get("data") or []:
        try:
            f = iso_ar(g["utcDate"])
        except Exception:
            continue
        if g.get("played"):
            ultima = max(ultima, int(g.get("round") or 0))
        if not (desde <= f.date() <= hasta):
            continue
        h, a = g["local"]["club"]["code"], g["road"]["club"]["code"]
        linea = f"{ymd(f)} {f:%H%M} {h} {a}" if g.get("confirmedHour", True) else f"{ymd(f)}  {h} {a}"
        if g.get("played"):
            linea += f" {int(g['local']['score'])} {int(g['road']['score'])}"
        out.append(linea)
    tablas = None
    if ultima:
        st = get_json(f"https://api-live.euroleague.net/v3/competitions/E/seasons/E2026/rounds/{ultima}/basicstandings")
        filas = [f"{t['club']['code']} {t['gamesPlayed']} {t['gamesWon']} {t['gamesLost']} {t['pointsFor']} {t['pointsAgainst']} {t['gamesWon']}"
                 for t in sorted(st.get("teams") or [], key=lambda t: t.get("position") or 99)]
        if len(filas) >= 18:
            tablas = filas
    return out, tablas


def vivo(estado):
    ligas = leer("ligas.json", {})
    viejo = leer("vivo.json", {}) or {}
    nuevo, errores, resultados = {}, [], 0
    for liga, slug in ADC_LIGAS.items():
        if liga not in ligas:
            continue
        try:
            p = adc_partidos(liga, slug)
            v = {"p": p}
            try:
                t = adc_tablas(liga, slug, ligas[liga])
                if t:
                    v["tablas"] = t
            except Exception as e:
                errores.append(f"{liga} tabla: {str(e)[:80]}")
            nuevo[liga] = v
            resultados += sum(1 for s in p if len(s.split(" ")) >= 6)
        except Exception as e:
            errores.append(f"{liga}: {str(e)[:80]}")
            if liga in viejo:
                nuevo[liga] = viejo[liga]  # si falla, queda lo último que se leyó bien
    if "el" in ligas:
        try:
            p, filas = euroliga()
            v = {"p": p}
            grupos = ligas["el"].get("tablas") or []
            if filas and len(grupos) == 1:
                v["tablas"] = [{"grupo": grupos[0].get("grupo"), "filas": ",".join(filas)}]
            nuevo["el"] = v
            resultados += sum(1 for s in p if len(s.split(" ")) >= 6)
        except Exception as e:
            errores.append(f"el: {str(e)[:80]}")
            if "el" in viejo:
                nuevo["el"] = viejo["el"]
    if not nuevo:
        raise RuntimeError("no respondió ninguna fuente: " + "; ".join(errores[:3]))
    for v in nuevo.values():
        v.setdefault("act", AHORA.isoformat(timespec="seconds"))
    # "act" cambia siempre: se compara sin él para no subir cambios de más
    sin_act = lambda d: {k: {x: y for x, y in v.items() if x != "act"} for k, v in d.items()}
    cambio = sin_act(nuevo) != sin_act(viejo) and guardar("vivo.json", nuevo)
    estado["vivo"] = {"ok": True, "ligas": sorted(nuevo), "resultados": resultados, "avisos": errores[:5]}
    return cambio


# ---------------------------------------------------------------- Escudos de equipos nuevos
ESC_LADO = 56


def sin_fondo_negro(im):
    """Fondo negro conectado al borde -> transparente (los escudos de la AdC son JPG con fondo negro)."""
    from collections import deque
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    visto = bytearray(w * h)
    cola = deque()
    for x in range(w):
        cola.append((x, 0)); cola.append((x, h - 1))
    for y in range(h):
        cola.append((0, y)); cola.append((w - 1, y))
    while cola:
        x, y = cola.popleft()
        if visto[y * w + x]:
            continue
        visto[y * w + x] = 1
        r, g, b, a = px[x, y]
        m = max(r, g, b)
        if m > 110:
            continue
        px[x, y] = (r, g, b, 0 if m <= 48 else int(a * (m - 48) / 62))
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not visto[ny * w + nx]:
                cola.append((nx, ny))
    return im


def a_escudo(b):
    from PIL import Image
    im = Image.open(io.BytesIO(b))
    transparente = im.mode in ("RGBA", "LA", "P") and im.convert("RGBA").getextrema()[3][0] < 250
    im = im.convert("RGBA") if transparente else sin_fondo_negro(im)
    caja = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if caja:
        im = im.crop(caja)
    w, h = im.size
    k = ESC_LADO / max(w, h)
    im = im.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "WEBP", quality=88)
    return "data:image/webp;base64," + base64.b64encode(out.getvalue()).decode()


def escudos(estado):
    ligas = leer("ligas.json", {})
    nba_doc = leer("nba.json")
    if nba_doc:
        ligas["nba"] = nba_doc
    base = leer("escudos.json", {}) or {}
    auto = leer("escudos_auto.json", {}) or {}
    # lo que ya cargó la base no hace falta repetirlo
    auto = {l: {i: v for i, v in m.items() if i not in (base.get(l) or {})} for l, m in auto.items()}
    faltan = {}
    for l in list(ADC_LIGAS) + ["el", "nba"]:
        for i in (ligas.get(l) or {}).get("equipos") or {}:
            if i not in (base.get(l) or {}) and i not in (auto.get(l) or {}):
                faltan.setdefault(l, []).append(i)
    cargados, fallas = [], []
    if faltan:
        urls = {}
        for l in ADC_LIGAS:
            urls[l] = ESCUDOS_ADC.get(l, {})
            if any(i not in urls[l] for i in faltan.get(l, [])):  # la tabla lista a todos los equipos
                try:
                    h = get(f"{ADC}/{ADC_LIGAS[l]}/tabla-posiciones")
                    for i, src in re.findall(r'src="/escudos/(\d+)/(\d+)"', h):
                        urls[l].setdefault(i, f"{ADC}/escudos/{i}/{src}")
                except Exception as e:
                    fallas.append(f"{l}: {str(e)[:60]}")
        if "el" in faltan:
            try:
                for c in get_json("https://api-live.euroleague.net/v2/competitions/E/seasons/E2026/clubs").get("data") or []:
                    if (c.get("images") or {}).get("crest"):
                        urls.setdefault("el", {})[c["code"]] = c["images"]["crest"]
            except Exception as e:
                fallas.append(f"el: {str(e)[:60]}")
        if "nba" in faltan:
            try:
                j = get_json("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams")
                for s in j.get("sports") or []:
                    for lg in s.get("leagues") or []:
                        for t in lg.get("teams") or []:
                            t = t.get("team") or {}
                            if t.get("logos"):
                                urls.setdefault("nba", {})[t["abbreviation"]] = t["logos"][0]["href"]
            except Exception as e:
                fallas.append(f"nba: {str(e)[:60]}")
        for l, ids in faltan.items():
            for i in ids:
                u = (urls.get(l) or {}).get(i)
                if not u:
                    fallas.append(f"{l} {i}: sin escudo en la fuente")
                    continue
                try:
                    auto.setdefault(l, {})[i] = a_escudo(get(u, binario=True))
                    cargados.append(f"{l} {i}")
                except Exception as e:
                    fallas.append(f"{l} {i}: {str(e)[:60]}")
    auto = {l: m for l, m in auto.items() if m}
    cambio = guardar("escudos_auto.json", auto)
    estado["escudos"] = {"ok": True, "nuevos": cargados[:20], "fallas": fallas[:10]}
    return cambio


# ---------------------------------------------------------------- main
def main():
    pasos = sys.argv[1:] or ["vivo", "nba", "basquetpass", "escudos", "fotos"]
    estado = leer("estado.json", {}) or {}
    for nombre in pasos:
        fn = {"vivo": vivo, "nba": nba, "basquetpass": basquetpass, "escudos": escudos, "fotos": fotos}[nombre]
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
