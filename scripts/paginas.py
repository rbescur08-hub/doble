"""Genera las páginas que lee Google a partir de app.html y data/*.json.

- index.html: portada ("Básquet hoy"), con los partidos del día ya escritos en el HTML.
- /{slug}/index.html: una página por competencia, con próximos partidos, resultados y tabla.
- /fuentes/index.html, sitemap.xml y robots.txt.

La app reemplaza ese contenido apenas carga; el HTML escrito es para buscadores, vistas previas
y para quien abre la página con mala conexión. Se corre en GitHub Actions después de actualizar datos.
"""
import datetime as dt, html, json, os, re

RAIZ = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
CONF = json.load(open(os.path.join(RAIZ, "scripts", "sitio.json"), encoding="utf-8"))
BASE = CONF["base"].rstrip("/")
MARCA = CONF["marca"]
AR = dt.timezone(dt.timedelta(hours=-3))
HOY = dt.datetime.now(AR).date()
e = html.escape

COMPS = [  # id, slug, nombre corto, nombre para títulos
    ("lnb", "liga-nacional", "Liga Nacional", "Liga Nacional de Básquet"),
    ("la", "liga-argentina", "Liga Argentina", "Liga Argentina de Básquet"),
    ("lfb", "liga-femenina", "Liga Femenina", "Liga Femenina de Básquet"),
    ("sel", "seleccion-argentina", "Selección", "Selección Argentina de básquet"),
    ("lsb", "liga-sudamericana", "Liga Sudamericana", "Liga Sudamericana de básquet"),
    ("bcla", "bcl-americas", "BCL Americas", "BCL Americas"),
    ("el", "euroliga", "Euroliga", "Euroliga"),
    ("acb", "liga-endesa", "Liga Endesa", "Liga Endesa (ACB)"),
    ("nba", "nba", "NBA", "NBA"),
    ("ldd", "liga-de-desarrollo", "Liga de Desarrollo", "Liga de Desarrollo"),
    ("bbo", "bahia-blanca-lbb-oro", "Bahía Blanca · LBB Oro", "LBB Oro de Bahía Blanca"),
    ("bbp", "bahia-blanca-lbb-plata", "Bahía Blanca · LBB Plata", "LBB Plata de Bahía Blanca"),
    ("feb", "febamba", "FeBAMBA · Copa Oro", "FeBAMBA Copa Oro"),
    ("amb", "mar-del-plata", "Mar del Plata · AMB", "básquet de Mar del Plata (AMB)"),
]
DOW = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
UPPER = {"FSA", "FC", "MDP", "SDE", "NQN", "SN", "LP", "BB", "CC", "VT", "LR", "SL", "MZA", "CR", "SF", "CH", "LB"}
LOWER = {"DE", "LA", "DEL", "Y", "EL", "LAS", "LOS"}


def leer(n, d=None):
    p = os.path.join(RAIZ, "data", n)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


def pretty(n):
    if re.search(r"[a-záéíóúñ]", n):
        return n
    out = []
    for part in re.split(r"(\([^)]*\))", n):
        if part.startswith("("):
            inner = part[1:-1]
            out.append("(" + inner[0] + inner[1:].lower() + ")" if len(inner) > 3 else part.upper())
            continue
        ws = []
        for i, w in enumerate(part.split(" ")):
            bare = re.sub(r"[^A-ZÁÉÍÓÚÑÜ]", "", w, flags=re.I)
            if not w or bare in UPPER:
                ws.append(w)
            elif i > 0 and w in LOWER:
                ws.append(w.lower())
            else:
                ws.append(w[0] + w[1:].lower())
        out.append(" ".join(ws))
    return "".join(out)


def fecha_larga(d):
    return f"{DOW[d.weekday()]} {d.day} de {MES[d.month - 1]}"


class Liga:
    def __init__(self, k, doc, bp):
        self.k, self.doc = k, doc
        ok = doc.get("nombresOk")
        self.eq = {i: (v[0] if ok else pretty(v[0]), v[1] if len(v) > 1 else "") for i, v in (doc.get("equipos") or {}).items()}
        info = doc.get("info") or {}
        self.partidos = []
        for s in str(doc.get("partidos", "")).split(","):
            p = s.split(" ")
            if len(p) < 4:
                continue
            d = dt.date(2000 + int(p[0][:2]), int(p[0][2:4]), int(p[0][4:6]))
            ik = f"{p[0]}-{p[2]}-{p[3]}"
            r = (int(p[4]), int(p[5])) if len(p) >= 6 and p[4] and p[5] and int(p[4]) + int(p[5]) > 0 else None
            tv = (info.get(ik) or {}).get("tv") or doc.get("tvTodos") or ""
            if ik in bp and "Basquetpass" not in tv:
                tv = f"{tv} · Basquetpass" if tv else "Basquetpass"
            self.partidos.append({"d": d, "t": f"{p[1][:2]}:{p[1][2:]}" if p[1] else "", "h": p[2], "a": p[3], "r": r,
                                  "tv": tv or doc.get("tvSinConfirmar") or "Sin TV confirmada",
                                  "sede": (info.get(ik) or {}).get("sede") or (self.eq.get(p[2]) or ("", ""))[1]})
        self.partidos.sort(key=lambda m: (m["d"], m["t"] or "99"))

    def n(self, i):
        return (self.eq.get(i) or (i, ""))[0]


def fila(l, m, comp=None):
    res = f"<b>{m['r'][0]}–{m['r'][1]}</b>" if m["r"] else "vs"
    c = f" <small>{e(comp)}</small>" if comp else ""
    tv = "" if m["r"] else f" <small>· {e(m['tv'])}</small>"
    return f"<li><time>{e(m['t'] or '—')}</time> {e(l.n(m['h']))} {res} {e(l.n(m['a']))}{c}{tv}</li>"


def tabla(l, t):
    filas = [r.split(" ") for r in str(t.get("filas", "")).split(",") if r]
    if not filas:
        return ""
    vict = l.doc.get("tablaTipo") == "victorias"
    cab = "<tr><th>#</th><th>Equipo</th><th>PJ</th><th>PG</th><th>PP</th>" + ("" if vict else "<th>Pts</th>") + "</tr>"
    cuerpo = "".join(f"<tr><td>{i + 1}</td><td>{e(l.n(v[0]))}</td><td>{v[1]}</td><td>{v[2]}</td><td>{v[3]}</td>" + ("" if vict else f"<td>{v[6] if len(v) > 6 else ''}</td>") + "</tr>" for i, v in enumerate(filas))
    return f"<h3>{e(t.get('grupo') or 'Posiciones')}</h3><table>{cab}{cuerpo}</table>"


def jsonld(l, nombre, ms):
    ev = []
    for m in ms[:20]:
        if not m["t"]:
            continue
        x = {"@type": "SportsEvent", "name": f"{l.n(m['h'])} vs {l.n(m['a'])} · {nombre}", "sport": "Basketball",
             "startDate": f"{m['d'].isoformat()}T{m['t']}:00-03:00", "eventStatus": "https://schema.org/EventScheduled",
             "homeTeam": {"@type": "SportsTeam", "name": l.n(m["h"])}, "awayTeam": {"@type": "SportsTeam", "name": l.n(m["a"])}}
        if m["sede"]:
            x["location"] = {"@type": "Place", "name": pretty(m["sede"])}
        ev.append(x)
    if not ev:
        return ""
    return '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@graph": ev}, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def head(titulo, desc, path, extra=""):
    url = BASE + path
    return f"""<meta name="description" content="{e(desc)}">
<title>{e(titulo)}</title>
<link rel="canonical" href="{url}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#10243f">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(MARCA)}">
<meta property="og:locale" content="es_AR">
<meta property="og:title" content="{e(titulo)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{BASE}/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
{extra}"""


def pagina(app, titulo, desc, path, cuerpo, ruta="", extra=""):
    h = app.replace("<!--SEO-HEAD-->", head(titulo, desc, path, extra), 1)
    h = h.replace("<!--SEO-BODY-->", f'<div class="seo">{cuerpo}<p class="loading">Cargando…</p></div>', 1)
    if ruta:
        h = h.replace("<script>", f'<script>window.RUTA="{ruta}";</script>\n<script>', 1)
    return h


def escribir(rel, txt):
    p = os.path.join(RAIZ, rel)
    os.makedirs(os.path.dirname(p) or RAIZ, exist_ok=True)
    if os.path.exists(p) and open(p, encoding="utf-8").read() == txt:
        return
    open(p, "w", encoding="utf-8").write(txt)


def main():
    app = open(os.path.join(RAIZ, "app.html"), encoding="utf-8").read()
    ligas = leer("ligas.json", {}) or {}
    nba = leer("nba.json")
    if nba:
        ligas["nba"] = nba
    bp = {k: set(v) for k, v in (leer("bp.json", {}) or {}).items()}
    L = {k: Liga(k, ligas[k], bp.get(k, set())) for k, *_ in COMPS if k in ligas}
    urls = ["/"]

    # ---- portada
    hoy, ayer = [], []
    for k, slug, corto, _ in COMPS:
        if k not in L:
            continue
        for m in L[k].partidos:
            if m["d"] == HOY:
                hoy.append((m["t"] or "99", fila(L[k], m, corto)))
            elif m["d"] == HOY - dt.timedelta(days=1) and m["r"]:
                ayer.append((m["t"] or "99", fila(L[k], m, corto)))
    hoy.sort(); ayer.sort()
    notas = []
    for f, dia in sorted((leer("noticias.json", {}) or {}).items(), reverse=True)[:2]:
        for it in sorted((dia or {}).get("items") or [], key=lambda x: -(x.get("imp") or 1))[:6]:
            notas.append(f'<li><a href="{e(it.get("u", ""))}" rel="noopener">{e(it.get("t", ""))}</a> <small>{e(it.get("f", ""))}</small></li>')
    links = " · ".join(f'<a href="/{slug}/">{e(corto)}</a>' for k, slug, corto, _ in COMPS if k in L)
    cuerpo = (f"<h1>Básquet hoy, {fecha_larga(HOY)}: partidos, resultados y dónde verlos</h1>"
              f"<p>Todos los partidos de básquet de hoy en hora argentina, con el canal o plataforma para verlos: Liga Nacional, Liga Argentina, Liga Femenina, Euroliga, Liga Endesa, NBA, Selección y ligas zonales.</p>"
              f"<h2>Partidos de hoy</h2><ul>{''.join(x for _, x in hoy) or '<li>Hoy no hay partidos programados.</li>'}</ul>"
              + (f"<h2>Resultados de ayer</h2><ul>{''.join(x for _, x in ayer)}</ul>" if ayer else "")
              + (f"<h2>Noticias</h2><ul>{''.join(notas[:8])}</ul>" if notas else "")
              + f"<nav><h2>Competencias</h2>{links}</nav>")
    escribir("index.html", pagina(app, f"{MARCA} · Básquet hoy: partidos, resultados y dónde verlos",
                                  "Partidos de básquet de hoy y dónde verlos en Argentina: Liga Nacional, Liga Argentina, NBA, Euroliga, Liga Endesa y más. Resultados, fixture y tablas en hora argentina.",
                                  "/", cuerpo))

    # ---- competencias
    for k, slug, corto, largo in COMPS:
        if k not in L:
            continue
        l, doc = L[k], ligas[k]
        temp = doc.get("temporada") or ""
        prox = [m for m in l.partidos if not m["r"] and HOY <= m["d"] <= HOY + dt.timedelta(days=10)]
        res = [m for m in l.partidos if m["r"] and m["d"] >= HOY - dt.timedelta(days=10)][::-1]
        def bloque(ms, titulo):
            if not ms:
                return ""
            out, ult = [f"<h2>{titulo}</h2>"], None
            for m in ms:
                if m["d"] != ult:
                    out.append(("</ul>" if ult else "") + f"<h3>{fecha_larga(m['d']).capitalize()}</h3><ul>")
                    ult = m["d"]
                out.append(fila(l, m))
            return "".join(out) + "</ul>"
        tablas = "".join(tabla(l, t) for t in doc.get("tablas") or [])
        cuerpo = (f"<h1>{e(largo)} {e(temp)}: resultados, fixture, tabla y dónde ver</h1>"
                  f"<p>Todos los partidos de {e(largo)}: resultados, fixture y posiciones en hora argentina, con el canal para ver cada partido en Argentina.</p>"
                  + bloque(prox, "Próximos partidos") + bloque(res, "Últimos resultados")
                  + (f"<h2>Tabla de posiciones</h2>{tablas}" if tablas else "")
                  + f'<p><a href="/">Ver todos los partidos de hoy</a></p>')
        desc = f"{largo} {temp}: partidos de hoy, resultados, fixture y tabla de posiciones, con el canal para verlos en Argentina. En hora argentina."
        escribir(f"{slug}/index.html", pagina(app, f"{corto} {temp}: resultados, tabla y dónde ver | {MARCA}", desc, f"/{slug}/", cuerpo, k, jsonld(l, corto, prox)))
        urls.append(f"/{slug}/")

    # ---- fuentes
    fuentes = """<h1>Fuentes y contacto</h1>
<p>{m} junta en un solo lugar los partidos de básquet que se juegan en Argentina y los que se pueden ver desde acá. Todos los horarios están en hora argentina.</p>
<h2>De dónde salen los datos</h2><ul>
<li><b>Liga Nacional, Liga Argentina, Liga Femenina y Liga de Desarrollo:</b> Asociación de Clubes (laliganacional.com.ar).</li>
<li><b>Selección, Liga Sudamericana y BCL Americas:</b> FIBA y la Confederación Argentina de Básquetbol.</li>
<li><b>Euroliga:</b> Euroleague Basketball. <b>Liga Endesa:</b> ACB (acb.com).</li>
<li><b>NBA:</b> calendario y resultados de ESPN; los canales en Argentina salen de las transmisiones nacionales de cada partido.</li>
<li><b>Bahía Blanca:</b> Asociación Bahiense de Básquetbol. <b>FeBAMBA:</b> febamba.com. <b>Mar del Plata:</b> medios locales.</li>
<li><b>Dónde ver:</b> grilla de Basquetpass y programación de cada señal. Si un partido no tiene un canal confirmado por una fuente, figura como «Sin TV confirmada».</li>
</ul>
<h2>Noticias</h2><p>Las noticias son resúmenes propios con link a la nota original. Las marcadas como «Oficial» vienen de una liga, federación o club. Un dato duro (resultado, lesión, fichaje) se publica solo si lo confirma una fuente oficial o dos medios distintos.</p>
<h2>Escudos y logos</h2><p>Los escudos, logos y marcas pertenecen a cada club, liga y señal; se usan solo para identificarlos.</p>
<p><a href="/">Volver a los partidos de hoy</a></p>""".format(m=e(MARCA))
    escribir("fuentes/index.html", f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{head(f"Fuentes y contacto | {MARCA}", f"De dónde salen los resultados, tablas, canales y noticias de {MARCA}.", "/fuentes/")}
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Roboto+Condensed:wght@400;700&display=swap">
<style>body{{margin:0;background:#e9ebee;color:#15191f;font:16px/1.55 "Roboto Condensed",system-ui,sans-serif}}
header{{background:#10243f;padding:14px 16px}}header a{{color:#fff;text-decoration:none;font-weight:700;font-size:24px;letter-spacing:-.02em}}
header i{{display:inline-block;width:.62em;height:.62em;margin-left:.08em;border-radius:50%;background:#e8742a}}
main{{max-width:760px;margin:20px auto;background:#fff;padding:8px 24px 24px;border-radius:4px}}
@media (max-width:600px){{main{{margin:0;border-radius:0;padding:4px 16px 20px}}}}
h1{{font-size:28px}}h2{{font-size:19px;margin-top:26px}}a{{color:#0b56b3}}li{{margin:6px 0}}</style></head>
<body><header><a href="/">la naranja<i></i></a></header><main>{fuentes}</main></body></html>
""")
    urls.append("/fuentes/")

    escribir("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
             + "".join(f"<url><loc>{BASE}{u}</loc><lastmod>{HOY.isoformat()}</lastmod><changefreq>{'hourly' if u == '/' else 'daily'}</changefreq></url>\n" for u in urls)
             + "</urlset>\n")
    escribir("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")
    print("páginas:", len(urls))


if __name__ == "__main__":
    main()
