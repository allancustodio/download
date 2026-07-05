import os
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

def list_sessions() -> list[str]:
    files = []
    for f in os.listdir(SESSION_DIR):
        if f.startswith("cookies_") and f.endswith(".txt"):
            files.append(f.replace("cookies_", "").replace(".txt", ""))
    return sorted(files)

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
            cmd += ["-o", f"downloads/%(uploader)s/post_%(id)s/%(title)s.%(ext)s", url]
        else:
            emit("⏳ Executando gallery-dl...")
            cmd = [sys.executable, "-m", "gallery_dl"] + args
            if metadata: cmd.append("--write-metadata")
            cmd += ["--directory", "downloads/{author}/post_{shortcode}", url]
            
        success = run_cmd(cmd)
        os.chdir(old)
        
        if success: emit(f"✅ Download concluído!")
        else: emit(f"❌ Erro no download")
        emit("__DONE__")
    except Exception as e:
        emit(f"❌ Erro inesperado: {e}")
    finally:
        state["busy"] = False

def task_profile(username: str, opcao: int, date_after: str, metadata: bool):
    state["busy"] = True
    try:
        emit(f"🔎 Baixando perfil/stories: @{username}")
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
            cmd += ["--directory", "downloads/{author}/stories", url]
            success = run_cmd(cmd)
            
        elif opcao in [1, 2]:
            url = f"https://www.instagram.com/{username}/"
            emit("⏳ Executando yt-dlp para baixar vídeos/Reels...")
            cmd = [sys.executable, "-m", "yt_dlp"] + args
            if metadata: cmd.append("--write-info-json")
            if date_after: cmd += ["--dateafter", date_after.replace("-", "")]
            cmd += ["-o", f"downloads/%(uploader)s/reels/%(title)s_%(id)s.%(ext)s", url]
            success = run_cmd(cmd)
            
        else:
            url = f"https://www.instagram.com/{username}/"
            emit("⏳ Executando gallery-dl para baixar feed/álbuns...")
            cmd = [sys.executable, "-m", "gallery_dl"] + args
            if metadata: cmd.append("--write-metadata")
            if date_after: cmd += ["--date-after", date_after]
            cmd += ["--directory", "downloads/{author}/feed", url]
            success = run_cmd(cmd)

        os.chdir(old)
        if success: emit(f"✅ Perfil finalizado!")
        else: emit(f"❌ Erro ao baixar perfil")
        emit("__DONE__")
    except Exception as e:
        emit(f"❌ Erro: {e}")
    finally:
        state["busy"] = False

def task_hashtag(tag: str, date_after: str, metadata: bool):
    state["busy"] = True
    try:
        emit(f"🔎 Baixando hashtag: #{tag}")
        args = get_base_args()
        old = os.getcwd()
        os.chdir(BASE_DIR)

        url = f"https://www.instagram.com/explore/tags/{tag}/"
        emit("⏳ Executando gallery-dl para baixar hashtag...")
        
        cmd = [sys.executable, "-m", "gallery_dl"] + args
        if metadata: cmd.append("--write-metadata")
        if date_after: cmd += ["--date-after", date_after]
        cmd += ["--directory", f"downloads/hashtag_{tag}/{{author}}", url]
        
        success = run_cmd(cmd)
        os.chdir(old)
        
        if success: emit(f"✅ Hashtag finalizada!")
        else: emit(f"❌ Erro ao baixar hashtag")
        emit("__DONE__")
    except Exception as e:
        emit(f"❌ Erro: {e}")
    finally:
        state["busy"] = False

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
    threading.Thread(target=task_profile, args=(u, o, date_after, metadata), daemon=True).start()
    return jsonify({"ok": True})

@app.route("/download/hashtag", methods=["POST"])
def download_hashtag():
    data = request.get_json() or {}
    tag = data.get("tag", "").strip().lstrip("#")
    date_after = data.get("date_after", "").strip()
    metadata = bool(data.get("metadata", False))
    threading.Thread(target=task_hashtag, args=(tag, date_after, metadata), daemon=True).start()
    return jsonify({"ok": True})

if __name__ == "__main__":
    print("\n🚀 Instagram Downloader (Fase 2) rodando em http://localhost:5000\n")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)