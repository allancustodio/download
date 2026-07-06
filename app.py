import os
import json
import queue
import threading
import time
import subprocess
import sys
from flask import Flask, render_template, request, jsonify, Response

# ── Configuração de Diretórios ────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR   = os.path.join(BASE_DIR, "downloads")
SESSION_DIR  = os.path.join(BASE_DIR, "sessions")
os.makedirs(OUTPUT_DIR,  exist_ok=True)
os.makedirs(SESSION_DIR, exist_ok=True)

app   = Flask(__name__)
log_q = queue.Queue()

state = {
    "busy"     : False,
    "last_dir" : None,
    "user"     : None,
}

def emit(msg: str):
    print(msg)
    log_q.put(msg)

# ── Sessões salvas ─────────────────────────────────────────────────

def humanize_age(seconds: float) -> str:
    """Converte segundos em um rótulo tipo 'há 3 dias' / '⚠ há 2 meses'."""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    if hours < 1:
        return "agora há pouco"
    days = int(seconds // 86400)
    if days < 1:
        return f"há {hours}h"
    if days == 1:
        return "há 1 dia"
    if days < 30:
        return f"há {days} dias"
    months = days // 30
    unidade = "mês" if months == 1 else "meses"
    return f"⚠ há {months} {unidade} — considere renovar"

def list_sessions() -> list[dict]:
    """
    Retorna as sessões salvas com um rótulo de idade (baseado na data de
    modificação do arquivo de cookies), para o usuário saber quando o
    token foi salvo/atualizado pela última vez.
    """
    result = []
    now = time.time()
    for f in os.listdir(SESSION_DIR):
        if f.startswith("cookies_") and f.endswith(".txt"):
            username = f.replace("cookies_", "").replace(".txt", "")
            path = os.path.join(SESSION_DIR, f)
            try:
                mtime = os.path.getmtime(path)
                age_label = humanize_age(now - mtime)
            except OSError:
                age_label = "sessão salva"
            result.append({"username": username, "age_label": age_label})
    result.sort(key=lambda x: x["username"].lower())
    return result

def task_cookie_login(cookie_string: str):
    state["busy"] = True
    try:
        emit("🍪 Convertendo cookies para yt-dlp e gallery-dl...")
        import http.cookies
        simple_cookie = http.cookies.SimpleCookie(cookie_string)
        if "sessionid" not in simple_cookie:
            emit("❌ Cookie inválido (sem sessionid).")
            emit("__LOGIN_FAIL__")
            return
        logged_user = "user_autenticado"
        if "ds_user_id" in simple_cookie:
            logged_user = simple_cookie["ds_user_id"].value
        cookie_file_content = "# Netscape HTTP Cookie File\n"
        for name, morsel in simple_cookie.items():
            if morsel.value:
                cookie_file_content += f".instagram.com\tTRUE\t/\tTRUE\t2147483647\t{name}\t{morsel.value}\n"
                emit(f"   ✔ {name}")
        path = os.path.join(SESSION_DIR, f"cookies_{logged_user}.txt")
        with open(path, "w") as f: f.write(cookie_file_content)
        with open(os.path.join(SESSION_DIR, "cookies.txt"), "w") as f: f.write(cookie_file_content)
        state["user"] = logged_user
        emit(f"✅ Cookies salvos e prontos!")
        time.sleep(0.5)
        emit(f"__LOGIN_OK__{logged_user}")
    except Exception as e:
        emit(f"❌ Erro: {e}")
        emit("__LOGIN_FAIL__")
    finally:
        state["busy"] = False

def task_playwright_login():
    state["busy"] = True
    try:
        emit("🤖 Iniciando navegador para Login Automático...")
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            emit("⏳ Aguardando você realizar o login no navegador aberto...")
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://www.instagram.com/accounts/login/")

            # Espera pelo cookie sessionid por até 3 minutos
            logged_user = "user_autenticado"
            timeout = 180
            start_time = time.time()
            found_session = False

            while time.time() - start_time < timeout:
                cookies = context.cookies("https://www.instagram.com")
                cookie_dict = {c['name']: c['value'] for c in cookies}

                if "sessionid" in cookie_dict:
                    found_session = True
                    if "ds_user_id" in cookie_dict:
                        logged_user = cookie_dict["ds_user_id"]
                    break
                time.sleep(1)

            if found_session:
                emit("✅ Login detectado com sucesso no navegador!")
                cookies = context.cookies("https://www.instagram.com")
                cookie_file_content = "# Netscape HTTP Cookie File\n"
                for c in cookies:
                    expires = int(c.get('expires', 2147483647))
                    if expires == -1: expires = 2147483647
                    cookie_file_content += f".instagram.com\tTRUE\t/\tTRUE\t{expires}\t{c['name']}\t{c['value']}\n"

                path = os.path.join(SESSION_DIR, f"cookies_{logged_user}.txt")
                with open(path, "w") as f: f.write(cookie_file_content)
                with open(os.path.join(SESSION_DIR, "cookies.txt"), "w") as f: f.write(cookie_file_content)
                state["user"] = logged_user
                emit(f"✅ Sessão salva!")
                time.sleep(0.5)
                emit(f"__LOGIN_OK__{logged_user}")
            else:
                emit("❌ Tempo esgotado (3 minutos) ou login não realizado.")
                emit("__LOGIN_FAIL__")

            browser.close()
    except Exception as e:
        emit(f"❌ Erro no Playwright: {e}")
        emit("__LOGIN_FAIL__")
    finally:
        state["busy"] = False

def task_use_session(username: str):
    """Ativa uma sessão já salva (copia cookies_<user>.txt para cookies.txt)."""
    state["busy"] = True
    try:
        src = os.path.join(SESSION_DIR, f"cookies_{username}.txt")
        if not os.path.exists(src):
            emit(f"❌ Sessão de @{username} não encontrada.")
            emit("__LOGIN_FAIL__")
            return
        with open(src, "r", encoding="utf-8") as fsrc:
            content = fsrc.read()
        with open(os.path.join(SESSION_DIR, "cookies.txt"), "w", encoding="utf-8") as fdst:
            fdst.write(content)
        state["user"] = username
        emit(f"✅ Sessão de @{username} ativada!")
        time.sleep(0.3)
        emit(f"__LOGIN_OK__{username}")
    except Exception as e:
        emit(f"❌ Erro ao ativar sessão: {e}")
        emit("__LOGIN_FAIL__")
    finally:
        state["busy"] = False

def run_cmd(cmd):
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in process.stdout:
            if line.strip(): emit(f"   {line.strip()}")
        process.wait()
        return process.returncode == 0
    except Exception as e:
        emit(f"❌ Erro executando subprocesso: {e}")
        return False

def get_base_args():
    cookie_path = os.path.join(SESSION_DIR, "cookies.txt")
    if not os.path.exists(cookie_path):
        emit("⚠ Nenhum cookie encontrado. Tentando sem login...")
        return []
    return ["--cookies", cookie_path]

_FFMPEG_LOCATION_CACHE = {"checked": False, "path": None}

def get_ffmpeg_location():
    """
    Tenta localizar o ffmpeg automaticamente, nesta ordem:
    1) Pacote 'imageio-ffmpeg' (se instalado via `pip install imageio-ffmpeg`),
       que baixa e gerencia o binário sozinho — não precisa mexer no PATH.
    2) ffmpeg já instalado no sistema e disponível no PATH do Windows.
    Retorna None se não encontrar (yt-dlp então tentará mesclar sem ffmpeg,
    e pode falhar/deixar vídeo e áudio separados nesses casos).
    """
    if _FFMPEG_LOCATION_CACHE["checked"]:
        return _FFMPEG_LOCATION_CACHE["path"]

    path = None
    try:
        import imageio_ffmpeg
        path = imageio_ffmpeg.get_ffmpeg_exe()
        emit(f"🎬 ffmpeg encontrado via imageio-ffmpeg: {path}")
    except Exception:
        import shutil
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            path = system_ffmpeg
            emit(f"🎬 ffmpeg encontrado no PATH do sistema: {path}")
        else:
            emit("⚠ ffmpeg não encontrado. Rode 'pip install imageio-ffmpeg' "
                 "ou instale o ffmpeg manualmente para evitar áudio/vídeo separados.")

    _FFMPEG_LOCATION_CACHE["checked"] = True
    _FFMPEG_LOCATION_CACHE["path"] = path
    return path

def ytdlp_merge_args() -> list:
    """
    Monta os argumentos de mesclagem do yt-dlp: aponta para o ffmpeg
    (se encontrado) e força o formato final em mp4 com vídeo+áudio juntos.
    """
    args = []
    ffmpeg_path = get_ffmpeg_location()
    if ffmpeg_path:
        args += ["--ffmpeg-location", ffmpeg_path]
    args += ["--merge-output-format", "mp4"]
    return args

def gdl_directory_opt(*parts) -> list:
    """
    Monta os argumentos -o para o gallery-dl definir a estrutura de pastas
    usando campos de metadados reais (ex: {username}).

    IMPORTANTE #1: a flag --directory do gallery-dl é um caminho LITERAL
    (não expande {campos}). Para ter pastas dinâmicas com o nome real do
    autor, é preciso sobrescrever a opção de config via
    "-o extractor.instagram.directory=[...]", que sim aceita os campos
    de metadados do item sendo baixado.

    IMPORTANTE #2: por padrão, o gallery-dl prefixa TODO destino com
    "./gallery-dl/" (config "extractor.base-directory"). A flag --directory
    ignora esse prefixo automaticamente, mas o "-o directory=..." (usado
    acima) não — por isso é preciso zerar também o base-directory aqui,
    senão os arquivos caem em "gallery-dl/downloads/..." em vez de
    "downloads/...", ficando separados do que o yt-dlp salva.
    """
    return [
        "-o", "extractor.base-directory=./",
        "-o", f"extractor.instagram.directory={json.dumps(list(parts))}",
    ]

def gdl_ytdl_merge_opt() -> list:
    """
    Configura o downloader interno do gallery-dl (usado quando ele encontra
    um vídeo dentro de um post) para também usar o ffmpeg e mesclar em mp4.

    Isso evita ter que chamar o yt-dlp separadamente para o vídeo — o que
    causava pastas diferentes, pois o yt-dlp identifica o autor por um
    campo diferente (uploader/uploader_id/channel, que varia e às vezes
    vem como nome de exibição ou até um ID numérico) do que o gallery-dl
    ({username}). Com o gallery-dl cuidando de tudo (foto + vídeo), o
    nome da pasta é sempre o mesmo, vindo da mesma fonte de metadados.
    """
    raw_options = {"merge_output_format": "mp4"}
    ffmpeg_path = get_ffmpeg_location()
    if ffmpeg_path:
        raw_options["ffmpeg_location"] = ffmpeg_path
    return ["-o", f"downloader.ytdl.raw-options={json.dumps(raw_options)}"]

def task_url(url: str, dtype: str, metadata: bool):
    state["busy"] = True
    try:
        emit(f"🔗 Iniciando download do {'Vídeo' if dtype=='video' else 'Carrossel'}")
        args = get_base_args()
        old = os.getcwd()
        os.chdir(BASE_DIR)

        if dtype == "video":
            emit("⏳ Executando yt-dlp...")
            cmd = [sys.executable, "-m", "yt_dlp"] + args
            if metadata: cmd.append("--write-info-json")
            cmd += ytdlp_merge_args()
            cmd += ["-o", f"downloads/%(uploader_id,uploader,channel_id,channel)s/post_%(id)s/%(title)s.%(ext)s", url]
            success = run_cmd(cmd)
        else:
            emit("⏳ Executando gallery-dl (fotos e vídeo juntos)...")
            cmd = [sys.executable, "-m", "gallery_dl"] + args
            if metadata: cmd.append("--write-metadata")
            cmd += gdl_directory_opt("downloads", "{username}", "post_{post_shortcode}")
            cmd += gdl_ytdl_merge_opt()
            cmd.append(url)
            success = run_cmd(cmd)

        os.chdir(old)
        if success: emit(f"✅ Download concluído!")
        else: emit(f"❌ Erro no download")
        emit("__DONE__")
    except Exception as e:
        emit(f"❌ Erro inesperado: {e}")
    finally:
        state["busy"] = False

def task_profile(username: str, opcao: int, date_after: str, metadata: bool, limit: int = 0):
    """
    Baixa conteúdo de um perfil/stories.
    limit: quando > 0, corta a quantidade de itens baixados
           (--range para gallery-dl, --playlist-end para yt-dlp).
           Quando 0 (ou não informado), baixa tudo sem corte.

    Como o username já é conhecido aqui (veio do campo do formulário),
    a pasta de destino usa o valor literal em Python (f-string), sem
    depender da expansão de metadados do gallery-dl.
    """
    state["busy"] = True
    try:
        emit(f"🔎 Baixando perfil/stories: @{username}" + (f" (limite: {limit})" if limit else ""))
        args = get_base_args()
        old = os.getcwd()
        os.chdir(BASE_DIR)

        success = False

        if opcao == 5:
            # Stories
            url = f"https://www.instagram.com/stories/{username}/"
            emit("⏳ Executando gallery-dl para baixar Stories...")
            cmd = [sys.executable, "-m", "gallery_dl"] + args
            if metadata: cmd.append("--write-metadata")
            if date_after: cmd += ["--date-after", date_after]
            if limit: cmd += ["--range", f"1-{limit}"]
            cmd += ["--directory", f"downloads/{username}/stories", url]
            success = run_cmd(cmd)

        elif opcao in [1, 2]:
            url = f"https://www.instagram.com/{username}/"
            emit("⏳ Executando yt-dlp para baixar vídeos/Reels...")
            cmd = [sys.executable, "-m", "yt_dlp"] + args
            if metadata: cmd.append("--write-info-json")
            if date_after: cmd += ["--dateafter", date_after.replace("-", "")]
            if limit: cmd += ["--playlist-end", str(limit)]
            cmd += ytdlp_merge_args()
            cmd += ["-o", f"downloads/%(uploader_id,uploader,channel_id,channel)s/reels/%(title)s_%(id)s.%(ext)s", url]
            success = run_cmd(cmd)

        else:
            url = f"https://www.instagram.com/{username}/"
            emit("⏳ Executando gallery-dl para baixar feed (fotos e vídeos)...")
            cmd = [sys.executable, "-m", "gallery_dl"] + args
            if metadata: cmd.append("--write-metadata")
            if date_after: cmd += ["--date-after", date_after]
            if limit: cmd += ["--range", f"1-{limit}"]
            cmd += ["--directory", f"downloads/{username}/feed"]
            cmd += gdl_ytdl_merge_opt()
            cmd.append(url)
            success = run_cmd(cmd)

        os.chdir(old)
        if success: emit(f"✅ Perfil finalizado!")
        else: emit(f"❌ Erro ao baixar perfil")
        emit("__DONE__")
    except Exception as e:
        emit(f"❌ Erro: {e}")
    finally:
        state["busy"] = False

def task_hashtag(tag: str, date_after: str, metadata: bool, limit: int = 0):
    """
    Baixa posts de uma hashtag.
    Como cada post pode ser de um autor diferente, o nome da subpasta
    precisa vir dos metadados de cada item — por isso usamos a opção
    -o extractor.instagram.directory=[...] (que expande {username}),
    e não o --directory literal.
    limit: quando > 0, corta a quantidade de itens via --range no gallery-dl.
           Quando 0 (ou não informado), baixa tudo sem corte.
    """
    state["busy"] = True
    try:
        emit(f"🔎 Baixando hashtag: #{tag}" + (f" (limite: {limit})" if limit else ""))
        args = get_base_args()
        old = os.getcwd()
        os.chdir(BASE_DIR)

        url = f"https://www.instagram.com/explore/tags/{tag}/"
        emit("⏳ Executando gallery-dl para baixar hashtag (fotos e vídeos)...")

        cmd = [sys.executable, "-m", "gallery_dl"] + args
        if metadata: cmd.append("--write-metadata")
        if date_after: cmd += ["--date-after", date_after]
        if limit: cmd += ["--range", f"1-{limit}"]
        cmd += gdl_directory_opt("downloads", f"hashtag_{tag}", "{username}")
        cmd += gdl_ytdl_merge_opt()
        cmd.append(url)

        success = run_cmd(cmd)
        os.chdir(old)

        if success: emit(f"✅ Hashtag finalizada!")
        else: emit(f"❌ Erro ao baixar hashtag")
        emit("__DONE__")
    except Exception as e:
        emit(f"❌ Erro: {e}")
    finally:
        state["busy"] = False

def task_download_selected(urls: list, metadata: bool):
    """
    Baixa uma lista de URLs de posts individuais (resultado da seleção na grade).

    Usa só o gallery-dl (fotos e vídeo pelo mesmo comando), com o ffmpeg
    configurado no downloader interno dele (--ytdl.raw-options). Assim
    fotos e vídeo do mesmo post sempre caem na mesma pasta, pois usam o
    mesmo campo de metadados ({username}) — diferente de antes, quando o
    yt-dlp separado identificava o autor por um campo diferente (às vezes
    nome de exibição, às vezes um ID numérico), criando pastas duplicadas.
    """
    state["busy"] = True
    try:
        emit(f"📥 Baixando {len(urls)} post(s) selecionado(s)...")
        args = get_base_args()
        old = os.getcwd()
        os.chdir(BASE_DIR)

        ok = 0
        fail = 0
        for url in urls:
            emit(f"⏳ Baixando: {url}")
            cmd = [sys.executable, "-m", "gallery_dl"] + args
            if metadata: cmd.append("--write-metadata")
            cmd += gdl_directory_opt("downloads", "{username}", "post_{post_shortcode}")
            cmd += gdl_ytdl_merge_opt()
            cmd.append(url)

            r = run_cmd(cmd)
            if r: ok += 1
            else: fail += 1

        os.chdir(old)
        emit(f"✅ Concluído: {ok} baixados, {fail} erros.")
        emit("__DONE__")
    except Exception as e:
        emit(f"❌ Erro: {e}")
    finally:
        state["busy"] = False

def get_preview(source_url: str, limit: int) -> list:
    """
    Usa gallery-dl --dump-json para obter metadados de posts sem baixar.
    Retorna lista de dicts: {title, url, thumbnail, uploader, id}
    """
    cookie_path = os.path.join(SESSION_DIR, "cookies.txt")
    cmd = [sys.executable, "-m", "gallery_dl", "--dump-json"]
    if os.path.exists(cookie_path):
        cmd += ["--cookies", cookie_path]
    cmd += ["--range", f"1-{limit}"]
    cmd.append(source_url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=60)
        raw = result.stdout.strip()
        if not raw or raw == "null":
            print(f"[preview] sem output. stderr: {result.stderr[:300]}")
            return []

        all_items = json.loads(raw)
        posts = []
        seen = set()

        for entry in all_items:
            # gallery-dl emite: [type_id, url_or_metadata, optional_extra]
            # type 2 = metadata do arquivo (o que queremos)
            # type 3 = URL do arquivo real
            # type 6 = metadata da coleção/galeria (ignorar)
            if not isinstance(entry, list) or len(entry) < 2:
                continue
            type_id = entry[0]
            payload  = entry[1]
            if type_id != 2 or not isinstance(payload, dict):
                continue

            post_id = payload.get("post_id") or payload.get("post_shortcode") or ""
            if post_id in seen:
                continue
            seen.add(post_id)

            thumb = (payload.get("display_url") or
                     payload.get("thumbnail_url") or
                     payload.get("thumbnail") or "")
            title = (payload.get("description") or
                     payload.get("title") or "")[:60]
            url   = payload.get("post_url") or ""
            upl   = payload.get("username") or payload.get("fullname") or ""

            if url:
                posts.append({"title": title, "url": url,
                              "thumbnail": thumb, "uploader": upl, "id": post_id})

        return posts
    except Exception as ex:
        print(f"Erro no preview: {ex}")
        return []

# ── Rotas Flask ───────────────────────────────────────────────────

@app.route("/")
def index(): return render_template("index.html")

@app.route("/stream")
def stream():
    def generate():
        while True:
            try:
                msg = log_q.get(timeout=30)
                yield f"data: {msg}\n\n"
            except queue.Empty:
                yield "data: __PING__\n\n"
    return Response(generate(), mimetype="text/event-stream")

@app.route("/status")
def status():
    return jsonify({
        "busy"     : state["busy"],
        "last_dir" : state["last_dir"],
        "user"     : state["user"],
        "sessions" : list_sessions(),
    })

@app.route("/auth/login", methods=["POST"])
def auth_login():
    emit("❌ Login de usuário/senha foi desativado. Use a aba Cookie.")
    return jsonify({"ok": False, "error": "Use login por cookie."})

@app.route("/auth/playwright", methods=["POST"])
def auth_playwright():
    threading.Thread(target=task_playwright_login, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/auth/cookie", methods=["POST"])
def auth_cookie():
    data = request.get_json() or {}
    cookie_string = data.get("cookie_string", "").strip()
    threading.Thread(target=task_cookie_login, args=(cookie_string,), daemon=True).start()
    return jsonify({"ok": True})

@app.route("/auth/session", methods=["POST"])
def auth_session():
    """Ativa uma sessão já salva anteriormente (reutiliza o cookie sem precisar colar de novo)."""
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"ok": False, "error": "Username não informado."})
    threading.Thread(target=task_use_session, args=(username,), daemon=True).start()
    return jsonify({"ok": True})

@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    state["user"] = None
    cookie_path = os.path.join(SESSION_DIR, "cookies.txt")
    if os.path.exists(cookie_path): os.remove(cookie_path)
    return jsonify({"ok": True})

@app.route("/download/url", methods=["POST"])
def download_url():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    dtype = data.get("type", "video")
    metadata = bool(data.get("metadata", False))
    threading.Thread(target=task_url, args=(url, dtype, metadata), daemon=True).start()
    return jsonify({"ok": True})

@app.route("/download/profile", methods=["POST"])
def download_profile():
    data = request.get_json() or {}
    u = data.get("username", "").strip().lstrip("@")
    o = int(data.get("opcao", 1))
    date_after = data.get("date_after", "").strip()
    metadata = bool(data.get("metadata", False))
    limit = int(data.get("limit", 0) or 0)
    threading.Thread(target=task_profile, args=(u, o, date_after, metadata, limit), daemon=True).start()
    return jsonify({"ok": True})

@app.route("/download/hashtag", methods=["POST"])
def download_hashtag():
    data = request.get_json() or {}
    tag = data.get("tag", "").strip().lstrip("#")
    date_after = data.get("date_after", "").strip()
    metadata = bool(data.get("metadata", False))
    limit = int(data.get("limit", 0) or 0)
    threading.Thread(target=task_hashtag, args=(tag, date_after, metadata, limit), daemon=True).start()
    return jsonify({"ok": True})

@app.route("/preview", methods=["POST"])
def preview():
    data = request.get_json() or {}
    source = data.get("source", "").strip()   # 'profile' ou 'hashtag'
    target = data.get("target", "").strip()   # username ou tag
    limit  = int(data.get("limit", 12))

    if source == "profile":
        url = f"https://www.instagram.com/{target.lstrip('@')}/posts/"
    elif source == "hashtag":
        url = f"https://www.instagram.com/explore/tags/{target.lstrip('#')}/"
    else:
        return jsonify({"ok": False, "posts": []})

    posts = get_preview(url, limit)
    return jsonify({"ok": True, "posts": posts})

@app.route("/download/selected", methods=["POST"])
def download_selected():
    data = request.get_json() or {}
    urls = data.get("urls", [])
    metadata = bool(data.get("metadata", False))
    if not urls:
        return jsonify({"ok": False, "error": "Nenhuma URL selecionada."})
    threading.Thread(target=task_download_selected, args=(urls, metadata), daemon=True).start()
    return jsonify({"ok": True})

if __name__ == "__main__":
    print("\n🚀 Instagram Downloader (Fase 2) rodando em http://localhost:5000\n")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)