"""Lê o nomes.json e, para cada anime, faz UMA pesquisa no AniList (como o teu ani.py/img.py)
e guarda o nome em inglês + a capa. Guarda o progresso no próprio nomes.json (a cada 10 animes
e ao ser interrompido): se parar, corre outra vez e continua de onde ficou.

Uso:  python nomes_e_imagens.py [nomes.json] [--refazer]
  --refazer  tenta outra vez os que não tiveram correspondência"""
import json, re, os, sys, time, signal, unicodedata, difflib, urllib.request, urllib.error

try:
    import requests
except ImportError:
    requests = None

ARQ = next((a for a in sys.argv[1:] if not a.startswith("--")), "nomes.json")
REFAZER = "--refazer" in sys.argv
MANUAIS = "nomes_manuais.json"            # opcional: {"nome original": "nome que queres"}
RELATORIO, SEM_IMAGEM = "nomes_revisar.txt", "sem_imagem.txt"
LIMIAR = 0.86                              # nome: só troca acima disto
LIMIAR_IMAGEM = 0.72                       # imagem: aceita palpites mais fracos
ORCAMENTO_MIN = int(os.environ.get("ORCAMENTO_MIN", "300"))   # pára sozinho antes do limite do GitHub
GUARDAR_A_CADA = 10
URL = "https://graphql.anilist.co"
QUERY = """query($q:String){Page(perPage:5){media(search:$q,type:ANIME,sort:SEARCH_MATCH){
id format title{romaji english} synonyms coverImage{extraLarge large}}}}"""
ROMANOS = {"II": 2, "III": 3, "IV": 4, "VI": 6, "VII": 7, "VIII": 8, "IX": 9}


class Parar(Exception):
    pass


def _sinal(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, _sinal)      # cancelamento do GitHub Actions


# ---------- rede ----------
def post(payload):
    """devolve (json, cabeçalhos). Usa requests se existir (como os teus scripts), senão urllib."""
    if requests:
        r = requests.post(URL, json=payload, timeout=20,
                          headers={"User-Agent": "Mozilla/5.0 (compatible; animes-organizar/1.0)"})
        if r.status_code == 429:
            raise urllib.error.HTTPError(URL, 429, "limite", r.headers, None)
        r.raise_for_status()
        return r.json(), r.headers
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; animes-organizar/1.0)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r), r.headers


pausa = 2.2


def pesquisar(texto):
    """1 pedido ao AniList; repete com calma se der limite ou erro de rede."""
    global pausa
    ultimo = ""
    for t in range(6):
        try:
            d, h = post({"query": QUERY, "variables": {"q": texto}})
            try:                              # ajusta a velocidade ao limite real do AniList
                pausa = max(0.7, 60.0 / int(h.get("X-RateLimit-Limit", 30)) * 1.15)
            except Exception:
                pass
            if d.get("errors"):
                msg = json.dumps(d["errors"], ensure_ascii=False)[:300]
                if "Not Found" in msg:        # sem resultados
                    return []
                raise Parar("AniList recusou o pedido: " + msg)
            return d["data"]["Page"]["media"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                espera = int(e.headers.get("Retry-After", 60)) + 2
                print(f"  limite atingido, a esperar {espera}s", flush=True)
                time.sleep(espera)
                continue
            ultimo = f"HTTP {e.code}"
        except (KeyboardInterrupt, Parar):
            raise
        except Exception as e:
            ultimo = f"{type(e).__name__}: {e}"
        print(f"  tentativa {t + 1}/6 falhou: {ultimo}", flush=True)
        time.sleep(5 * (t + 1))
    raise Parar("sem resposta do AniList. Último erro: " + ultimo)


# ---------- comparação de nomes ----------
def sem_acentos(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()


def palavras(t):
    return re.findall(r"[a-z0-9]+", sem_acentos(t).lower())


def norm(t):
    return "".join(palavras(t))


def numeros(t):
    out = set()
    for w in palavras(t):
        m = re.fullmatch(r"(\d{1,2})(st|nd|rd|th|a)?", w)
        if m:
            out.add(int(m.group(1)))
        elif w.upper() in ROMANOS:
            out.add(ROMANOS[w.upper()])
    return out


def limpar(nome):
    n = re.sub(r"\b(dublado|legendado|todos os epis[oó]dios|filme)\b", " ", nome, flags=re.I)
    n = re.sub(r"\(\s*(ONA|TV|OVA)?\s*\)", " ", n, flags=re.I)
    return re.sub(r"\s+", " ", n).strip(" -:–,")


def melhor(nome, medias):
    q = norm(nome)
    nq = numeros(nome)
    best, score = None, 0.0
    for m in medias:
        nomes = [m["title"].get("romaji"), m["title"].get("english")] + (m.get("synonyms") or [])
        for n in nomes:
            if not n or not norm(n):
                continue
            s = 1.0 if norm(n) == q else difflib.SequenceMatcher(None, q, norm(n)).ratio()
            if numeros(n) != nq:
                s *= 0.8                      # "Hero Academia 2" não pode apanhar a temporada 1
            if s > score:
                best, score = m, s
    return best, score


# ---------- ficheiros ----------
def guardar(lista):
    tmp = ARQ + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, ARQ)                      # troca atómica: nunca fica um ficheiro a meio


def relatorios(lista):
    rev = [f"{x['nome_original']}   (palpite: {x.get('palpite', '-')}, {x.get('score', 0):.2f})"
           for x in lista if x.get("feito") and not x.get("anilist")]
    sem = [x["nome_original"] for x in lista if x.get("feito") and not x.get("imagem")]
    with open(RELATORIO, "w", encoding="utf-8") as f:
        f.write("\n".join(rev))
    with open(SEM_IMAGEM, "w", encoding="utf-8") as f:
        f.write("\n".join(sem))
    return len(rev), len(sem)


def saida(completo):
    print("COMPLETO=" + str(completo).lower())
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"completo={str(completo).lower()}\n")


def main():
    with open(ARQ, encoding="utf-8") as f:
        lista = json.load(f)
    manuais = {}
    if os.path.exists(MANUAIS):
        with open(MANUAIS, encoding="utf-8") as f:
            manuais = json.load(f)

    for x in lista:
        x.setdefault("nome_original", x["nome"])
        if x["nome_original"] in manuais:
            x["nome"], x["feito"] = manuais[x["nome_original"]], True
        if REFAZER and x.get("feito") and not x.get("anilist") and x["nome_original"] not in manuais:
            x["feito"] = False

    por_fazer = [x for x in lista if not x.get("feito")]
    print(f"{len(lista)} animes | já feitos: {len(lista) - len(por_fazer)} | por fazer: {len(por_fazer)}")

    inicio, n = time.time(), 0
    try:
        for x in por_fazer:
            if (time.time() - inicio) / 60 > ORCAMENTO_MIN:
                print("Orçamento de tempo atingido: progresso guardado, corre outra vez para continuar.")
                break
            orig = x["nome_original"]
            limpo = limpar(orig)
            m, score = melhor(limpo, pesquisar(limpo))
            time.sleep(pausa)
            x["score"] = round(score, 2)
            x["palpite"] = (m["title"].get("english") or m["title"].get("romaji")) if m else "-"
            cover = (m.get("coverImage") or {}) if m else {}
            capa = cover.get("extraLarge") or cover.get("large")
            x["imagem"] = capa if (m and score >= LIMIAR_IMAGEM and capa) else ""
            if m and score >= LIMIAR:
                x["nome"], x["anilist"] = x["palpite"], m["id"]
            else:
                x["nome"] = orig
            x["feito"] = True
            n += 1
            print(f"[{n}/{len(por_fazer)}] {orig}  ->  {x['nome']}  ({score:.2f})", flush=True)
            if n % GUARDAR_A_CADA == 0:
                guardar(lista)
    except KeyboardInterrupt:
        print("Interrompido: a guardar o progresso...")
    except Parar as e:
        print("ERRO:", e, "\nProgresso guardado. Corre outra vez para continuar.")
    finally:
        guardar(lista)

    rev, sem = relatorios(lista)
    falta = sum(1 for x in lista if not x.get("feito"))
    print(f"\nfeitos: {len(lista) - falta}/{len(lista)} | a rever: {rev} ({RELATORIO}) | sem imagem: {sem} ({SEM_IMAGEM})")
    saida(falta == 0)


main()
