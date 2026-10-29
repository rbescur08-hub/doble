import re, unicodedata
STOP = {"club","atletico","atlético","de","del","la","el","los","las","y","social","deportivo","sportivo","cultural","basquet","basket","basketball","bc","cd","ca","c","a","sc","fc","football"}
ALIAS = {"crvena":"estrella roja","zvezda":"","mdp":"mar del plata","caba":"","cr":"comodoro rivadavia","munich":"munich","paris":"paris"}
# abreviaturas que usa la AdC en los nombres oficiales ("SOC. ESPAÑOLA (SL)", "DEP. BERAZATEGUI")
ABREV = {"soc":"sociedad","dep":"deportivo","gim":"gimnasia","ind":"independiente","inst":"instituto"}
def norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii","ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return [w for w in (ABREV.get(w, w) for w in s.split()) if w not in STOP]
def score(a, b):
    A, B = set(norm(a)), set(norm(b))
    if not A or not B: return 0
    inter = len(A & B)
    # prefijos (Gimnasia ~ Gimn., Corrientes ~ Ctes)
    for x in A - B:
        for y in B - A:
            if len(x) >= 4 and len(y) >= 4 and (x.startswith(y) or y.startswith(x)): inter += 0.8
    return inter / min(len(A), len(B))
def best(name, equipos):
    """equipos: {id: [NOMBRE, ESTADIO]} -> (id, score)"""
    r = sorted(((score(name, v[0]), k) for k, v in equipos.items()), reverse=True)
    if not r: return None, 0
    if len(r) > 1 and r[0][0] == r[1][0]: return None, r[0][0]
    return r[0][1], r[0][0]
