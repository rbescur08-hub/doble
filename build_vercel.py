import json, glob, os, sys
src = sys.argv[1]; out = sys.argv[2]
def coll(name):
    r = {}
    for p in sorted(glob.glob(f"{src}/{name}/*.json")):
        r[os.path.basename(p)[:-5]] = json.load(open(p))
    return r
D = f"{out}/data"; os.makedirs(D, exist_ok=True)
def w(n, o): json.dump(o, open(f"{D}/{n}.json","w"), ensure_ascii=False, separators=(",",":"))
w("ligas", coll("ligas"))
w("noticias", coll("noticias"))
w("fotos", {k:v["img"] for k,v in coll("fotos").items() if v.get("img")})
w("escudos", {k:v.get("eq",{}) for k,v in coll("escudos").items()})
ex = coll("extra")
lg = ex.get("logos", {})
w("logos", {"comp":lg.get("comp",{}),"tv":lg.get("tv",{}),"flag":lg.get("flag",{})})
w("extra", {"argentinos":ex.get("argentinos"),"formativas":ex.get("formativas")})
html = open("/home/claude/doble.html").read()
a = html.index("// ---------- datos ----------"); b = html.index("})();", a) + 5
loader = """// ---------- datos (versión estática: /data/*.json) ----------
render();
(async ()=>{
  canEdit = false; db = null;
  const get = n => fetch("data/"+n+".json", {cache:"no-cache"}).then(r=>{ if(!r.ok) throw new Error(n); return r.json(); });
  try{
    const [ligas, noticias, logos, escudos, fotos, extra] = await Promise.all(
      ["ligas","noticias","logos","escudos","fotos","extra"].map(get));
    const next = {};
    for(const id in ligas){ if(COMP[id]) next[id] = parseLiga(id, ligas[id]); }
    const eq = {};
    for(const l in escudos){ const m = escudos[l] || {}; for(const id in m) eq[l+":"+id] = m[id]; }
    DATA = next; NEWS = noticias; FOTOS = fotos;
    LOGOS = {eq, comp:logos.comp||{}, tv:logos.tv||{}, flag:logos.flag||{}};
    ARG = extra.argentinos || null; FORM = extra.formativas || null;
    loaded = true; render();
  }catch(e){ dbOk = false; loaded = false; render(); }
})();"""
html = html[:a] + loader + html[b:]
open(f"{out}/index.html","w").write(html)
