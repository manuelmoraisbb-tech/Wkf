"""Descarrega UMA vez o catálogo de animes do AniList (~500 pedidos) e guarda em
anilist_catalogo.json. Guarda o progresso a cada 5 páginas e também ao ser interrompido
(Ctrl+C, cancelamento ou limite de tempo do GitHub): basta correr outra vez para retomar."""
import json, os, signal, sys, time, urllib.request, urllib.error

ARQ = "anilist_catalogo.json"
ORCAMENTO_MIN = int(os.environ.get("ORCAMENTO_MIN", "150"))   # pára sozinho antes de estourar
VALIDADE_DIAS = 30
PAUSA = 2.3   # segundos entre pedidos (seguro mesmo com o limite reduzido do AniList)
GUARDAR_A_CADA = 5

QUERY = """query($p:Int){Page(page:$p,perPage:50){
pageInfo{hasNextPage}
media(type:ANIME,sort:ID,format_in:[TV,TV_SHORT,MOVIE,OVA,ONA,SPECIAL]){
id format title{romaji english} synonyms coverImage{extraLarge large}}}}"""


def _interromper(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, _interromper)   # cancelamento do GitHub Actions


def pedir(pagina):
    body = json.dumps({"query": QUERY, "variables": {"p": pagina}}).encode()
    req = urllib.request.Request(
        "https://graphql.anilist.co", data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"})
    for t in range(8):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)["data"]["Page"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                espera = int(e.headers.get("Retry-After", "60")) + 2
                print(f"  limite atingido, a esperar {espera}s", flush=True)
                time.sleep(espera)
            else:
                time.sleep(5 * (t + 1))
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            time.sleep(5 * (t + 1))
    return None


def guardar(est):
    vistos = {}
    for it in est["itens"]:            # sem duplicados, mesmo que uma página se repita
        vistos[it["i"]] = it
    est["itens"] = list(vistos.values())
    tmp = ARQ + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(est, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, ARQ)               # troca atómica: nunca fica um ficheiro a meio


def saida(completo):
    print("COMPLETO=" + str(completo).lower())
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"completo={str(completo).lower()}\n")


def main():
    est = {"pagina": 0, "completo": False, "atualizado": 0, "itens": []}
    if os.path.exists(ARQ):
        with open(ARQ, encoding="utf-8") as f:
            est = json.load(f)
        idade = (time.time() - est.get("atualizado", 0)) / 86400
        if est["completo"] and idade < VALIDADE_DIAS:
            print(f"Catálogo já completo ({len(est['itens'])} animes, {idade:.0f} dias). Nada a fazer.")
            return saida(True)
        if est["completo"]:            # velho: recomeça
            est = {"pagina": 0, "completo": False, "atualizado": 0, "itens": []}
        else:
            print(f"A retomar da página {est['pagina'] + 1} ({len(est['itens'])} animes já guardados)")

    inicio = time.time()
    try:
        while True:
            if (time.time() - inicio) / 60 > ORCAMENTO_MIN:
                print("Orçamento de tempo atingido: progresso guardado, corre outra vez para continuar.")
                break
            pagina = est["pagina"] + 1
            pg = pedir(pagina)
            if pg is None:
                print("Falha repetida: progresso guardado, corre outra vez para continuar.")
                break
            novos = [{
                "i": m["id"], "f": m["format"], "r": m["title"].get("romaji"), "e": m["title"].get("english"),
                "s": m.get("synonyms") or [],
                "c": (m.get("coverImage") or {}).get("extraLarge") or (m.get("coverImage") or {}).get("large"),
            } for m in pg["media"]]
            est["itens"].extend(novos)
            est["pagina"] = pagina
            if not pg["pageInfo"]["hasNextPage"]:
                est["completo"] = True
                est["atualizado"] = time.time()
                break
            if pagina % GUARDAR_A_CADA == 0:
                guardar(est)
                print(f"página {pagina}  ({len(est['itens'])} animes)", flush=True)
            time.sleep(PAUSA)
    except KeyboardInterrupt:
        print("Interrompido: a guardar o progresso...")
    finally:
        guardar(est)

    print(f"{len(est['itens'])} animes no catálogo, página {est['pagina']}, completo={est['completo']}")
    saida(est["completo"])


main()
