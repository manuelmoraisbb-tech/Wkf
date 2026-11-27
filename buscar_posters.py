# buscar_posters.py
import re
import os
import json
import time
import requests

# COLA AQUI UMA DAS DUAS CHAVES:
# - API Key (v3) = 32 caracteres hex
# - API Read Access Token (v4) = token gigante com pontos eyJ...
TMDB_CREDENCIAL = "2b02175195bc36f6215e26c19959aa87"
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p/w500"

os.makedirs("posters", exist_ok=True)

def is_token_v4(cred):
    # Token v4 é JWT gigante com 2 pontos, Key v3 é 32 hex sem pontos
    return len(cred) > 50 and cred.count(".") >= 2

def tmdb(endpoint, params=None):
    params = params or {}
    headers = {"accept": "application/json"}

    if is_token_v4(TMDB_CREDENCIAL):
        # MÉTODO CERTO V4: Bearer no header, SEM api_key na URL
        headers["Authorization"] = f"Bearer {TMDB_CREDENCIAL}"
    else:
        # MÉTODO CERTO V3: api_key na URL
        params["api_key"] = TMDB_CREDENCIAL

    try:
        r = requests.get(f"{TMDB_BASE}{endpoint}", params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f" [ERRO HTTP {r.status_code} {r.json().get('status_message','')}] ", end="")
            return None
        return r.json()
    except Exception as e:
        print(f" [ERRO {e}] ", end="")
        return None

def limpar_nome(nome):
    nome = nome.strip()
    nome = re.sub(r'%3D.*$', '', nome, flags=re.I)  # tira %3D3, %3D54...
    nome = re.sub(r'\s*Todos Episodios.*$', '', nome, flags=re.I)
    nome = re.sub(r'\s*Filme\s*\d+.*$', '', nome, flags=re.I)
    nome = re.sub(r'\s*\(Dorama\)', '', nome, flags=re.I)
    nome = re.sub(r'\s*\( \)', '', nome)
    nome = re.sub(r'\s+', ' ', nome)
    return nome.strip()

def buscar(titulo):
    # Tenta multi primeiro, depois tv, depois movie
    tentativas = [
        ("/search/multi", {"query": titulo, "language": "en-US", "include_adult": "false", "page": 1}),
        ("/search/tv", {"query": titulo, "language": "en-US", "include_adult": "false", "page": 1}),
        ("/search/movie", {"query": titulo, "language": "en-US", "include_adult": "false", "page": 1}),
    ]
    for endpoint, params in tentativas:
        data = tmdb(endpoint, params)
        if not data or not data.get("results"):
            continue
        for r in data["results"]:
            if not r.get("poster_path"):
                continue
            if r.get("media_type") == "person":  # multi devolve pessoas também
                continue
            return {
                "id": r["id"],
                "tipo": r.get("media_type") or ("tv" if endpoint == "/search/tv" else "movie"),
                "titulo_tmdb": r.get("name") or r.get("title") or "",
                "titulo_original": r.get("original_name") or r.get("original_title") or "",
                "poster_path": r["poster_path"],
                "poster_url": TMDB_IMG + r["poster_path"],
                "sinopse": r.get("overview", ""),
                "nota": r.get("vote_average", 0),
                "ano": (r.get("first_air_date") or r.get("release_date") or "")[:4],
            }
        time.sleep(0.2)  # respeita rate limit do TMDb
    return None

# --- TESTE RÁPIDO ---
print("A testar a tua chave com 'Naruto'...")
teste = tmdb("/search/tv", {"query": "Naruto", "language": "en-US", "page": 1})
if teste and teste.get("results"):
    print(f"FUNCIONOU! Primeiro: {teste['results'][0]['name']}")
    print(f"Poster: {TMDB_IMG}{teste['results'][0]['poster_path']}\n")
else:
    print("ERRO - status_code 7 = trocaste as chaves. Vai a themoviedb.org > Settings > API e copia o OUTRO campo.")
    print("Se meteste a Key v3, tenta o Token v4, e vice-versa.\n")
    exit()

# --- MAIN ---
with open("sem_imagem.txt", encoding="utf-8", errors="ignore") as f:
    linhas = [l.strip() for l in f if l.strip()]

resultado = []
falhados = []

for i, original in enumerate(linhas, 1):
    limpo = limpar_nome(original)
    if not limpo:
        continue
    print(f"{i}/{len(linhas)} {limpo} ... ", end="", flush=True)
    info = buscar(limpo)
    if info:
        ficheiro = f"posters/{re.sub(r'[^a-zA-Z0-9-_]', '_', limpo)}.jpg"
        try:
            img = requests.get(info["poster_url"], timeout=15).content
            open(ficheiro, "wb").write(img)
        except:
            pass
        info["ficheiro_local"] = ficheiro
        info["nome_original"] = original
        info["nome_limpo"] = limpo
        resultado.append(info)
        print(f"OK - {info['titulo_tmdb']} ({info['ano']})")
    else:
        falhados.append(original)
        print("NAO ACHADO")

    # Guarda a cada 20 para não perder se parar
    if i % 20 == 0:
        with open("com_imagem.json", "w", encoding="utf-8") as out:
            json.dump(resultado, out, ensure_ascii=False, indent=2)

with open("com_imagem.json", "w", encoding="utf-8") as out:
    json.dump(resultado, out, ensure_ascii=False, indent=2)
with open("ainda_sem_imagem.txt", "w", encoding="utf-8") as out:
    out.write("\n".join(falhados))

print(f"\nFIM: {len(resultado)} encontrados, {len(falhados)} falhados")
print("Posters em: posters/ | JSON: com_imagem.json | Falhados: ainda_sem_imagem.txt")