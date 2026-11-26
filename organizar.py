"""Lê o nomes.json, troca cada nome pelo inglês e põe a capa do AniList (campo "imagem"),
SEM pedidos à internet: compara com o anilist_catalogo.json local. Demora segundos."""
import json, re, os, sys, unicodedata, difflib, collections

ENTRADA = sys.argv[1] if len(sys.argv) > 1 else "nomes.json"
CATALOGO = "anilist_catalogo.json"
MANUAIS = "nomes_manuais.json"      # opcional: {"nome original": "nome que queres"}
RELATORIO = "nomes_revisar.txt"
LIMIAR = 0.86                       # abaixo disto não troca o NOME
LIMIAR_IMAGEM = 0.72                # a imagem aceita palpites mais fracos (mesma franquia serve)
LIMPAR_IMAGENS_ANTIGAS = True       # sem correspondência -> imagem vazia (o site mostra um placeholder)
ROMANOS = {"II": 2, "III": 3, "IV": 4, "VI": 6, "VII": 7, "VIII": 8, "IX": 9}


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


def ordinal(k):
    if 10 <= k % 100 <= 13:
        return f"{k}th"
    return f"{k}" + {1: "st", 2: "nd", 3: "rd"}.get(k % 10, "th")


def limpar(nome):
    n = re.sub(r"\b(dublado|legendado|todos os epis[oó]dios|filme)\b", " ", nome, flags=re.I)
    n = re.sub(r"\(\s*(ONA|TV|OVA)?\s*\)", " ", n, flags=re.I)
    return re.sub(r"\s+", " ", n).strip(" -:–,")


def variantes(n):
    v = [n]
    m = re.search(r"\b(\d+)\s*[ªa°º]\s*temporada\b", n, re.I)
    if m:
        k = int(m.group(1))
        base = re.sub(r"\s+", " ", n[:m.start()] + " " + n[m.end():]).strip(" -:–,")
        v += [f"{base} {ordinal(k)} Season", f"{base} Season {k}", f"{base} {k}"]
        if k == 1:
            v.append(base)
    return list(dict.fromkeys(x for x in v if x))


class Catalogo:
    def __init__(self, itens):
        self.itens = itens
        self.nomes = []
        self.exato = collections.defaultdict(list)
        self.tokens = collections.defaultdict(set)
        for i, it in enumerate(itens):
            ns = [n for n in [it.get("r"), it.get("e")] + (it.get("s") or []) if n]
            self.nomes.append([(norm(n), n) for n in ns if norm(n)])
            for k, _ in self.nomes[i]:
                self.exato[k].append(i)
            for _, n in self.nomes[i]:
                for w in set(palavras(n)):
                    if len(w) >= 3:
                        self.tokens[w].add(i)

    def _melhor_exato(self, idxs):
        return sorted(idxs, key=lambda i: (self.itens[i].get("f") not in ("TV", "TV_SHORT"), self.itens[i]["i"]))[0]

    def buscar(self, nome):
        melhor, score = None, 0.0
        for v in variantes(limpar(nome)):
            k = norm(v)
            if not k:
                continue
            if k in self.exato:
                return self.itens[self._melhor_exato(self.exato[k])], 1.0
            conta = collections.Counter()
            for w in set(palavras(v)):
                if len(w) >= 3 and len(self.tokens.get(w, ())) < 3000:
                    for i in self.tokens.get(w, ()):
                        conta[i] += 1
            nv = numeros(v)
            for i, _ in conta.most_common(30):
                for kn, nn in self.nomes[i]:
                    sm = difflib.SequenceMatcher(None, k, kn)
                    if sm.real_quick_ratio() < 0.6 or sm.quick_ratio() < 0.6:
                        continue
                    s = sm.ratio()
                    if numeros(nn) != nv:
                        s *= 0.8
                    if s > score:
                        melhor, score = self.itens[i], s
        return melhor, score


def main():
    if not os.path.exists(CATALOGO):
        sys.exit("Falta o anilist_catalogo.json (corre primeiro o anilist_catalogo.py)")
    with open(CATALOGO, encoding="utf-8") as f:
        cat = Catalogo(json.load(f)["itens"])
    with open(ENTRADA, encoding="utf-8") as f:
        lista = json.load(f)
    manuais = {}
    if os.path.exists(MANUAIS):
        with open(MANUAIS, encoding="utf-8") as f:
            manuais = json.load(f)

    ok, com_img, revisar, sem_img = 0, 0, [], []
    for x in lista:
        orig = x.get("nome_original") or x["nome"]      # guarda sempre o nome de origem: pode correr várias vezes
        x["nome_original"] = orig
        if orig in manuais:
            x["nome"] = manuais[orig]
            continue
        item, score = cat.buscar(orig)
        if item and score >= LIMIAR_IMAGEM and item.get("c"):
            x["imagem"] = item["c"]
            com_img += 1
        elif LIMPAR_IMAGENS_ANTIGAS:
            x["imagem"] = ""
            sem_img.append(orig)
        if item and score >= LIMIAR:
            x["nome"] = item.get("e") or item.get("r")
            x["anilist"] = item["i"]
            ok += 1
        else:
            x["nome"] = orig
            guess = (item.get("e") or item.get("r")) if item else "-"
            revisar.append(f"{orig}   (melhor palpite: {guess}, {score:.2f})")

    with open(ENTRADA, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, separators=(",", ":"))
    with open(RELATORIO, "w", encoding="utf-8") as f:
        f.write("\n".join(revisar))
    with open("sem_imagem.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(sem_img))
    print(f"nomes atualizados: {ok}/{len(lista)} | imagens novas: {com_img}/{len(lista)}")
    print(f"sem imagem: {len(sem_img)} (ver sem_imagem.txt) | nomes a rever: {len(revisar)} ({RELATORIO})")


main()
