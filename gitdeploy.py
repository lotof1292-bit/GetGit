"""
GetGit — Pastilla flotante instaladora de repos GitHub
Plataforma: Windows | Stack: Python 3.x + PyQt6
"""
import sys, os, json, shutil, subprocess, re
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlparse, urlunparse, unquote, parse_qs

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFileDialog,
    QProgressBar, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint, QTimer, QEvent
from PyQt6.QtGui import QTextCursor

# ── Rutas ─────────────────────────────────────────────────────────────────────
HISTORY_FILE = Path(__file__).parent / "history.json"
CONFIG_FILE  = Path(__file__).parent / "config.json"
MAX_HISTORY  = 10
DEFAULT_DEST = str(Path.home())

def load_config() -> dict:
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}

def save_config(data: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass

def load_history() -> list:
    try:
        if HISTORY_FILE.exists():
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []

def save_history(url: str, history: list) -> list:
    try:
        if url in history: history.remove(url)
        history.insert(0, url)
        history = history[:MAX_HISTORY]
        HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except Exception:
        pass
    return history

# ── Mapa herramientas → winget ────────────────────────────────────────────────
TOOL_INSTALL = {
    "git":    ("Git",     "Git.Git"),
    "npm":    ("Node.js", "OpenJS.NodeJS.LTS"),
    "node":   ("Node.js", "OpenJS.NodeJS.LTS"),
    "pip":    ("Python",  "Python.Python.3.12"),
    "python": ("Python",  "Python.Python.3.12"),
    "cargo":  ("Rust",    "Rustlang.Rustup"),
    "go":     ("Go",      "GoLang.Go"),
    "mvn":    ("Maven",   "Apache.Maven"),
    "yarn":   ("Yarn",    "Yarn.Yarn"),
    "make":   ("Make",    "GnuWin32.Make"),
    "bash":   ("Git Bash","Git.Git"),
}

# ── Diagnóstico del sistema ──────────────────────────────────────────────────
import shutil as _shutil

REQUIRED_TOOLS = [
    ("git",    "Git",       "Git.Git",              "Control de versiones — necesario para clonar"),
    ("npm",    "Node.js",   "OpenJS.NodeJS.LTS",     "Proyectos JavaScript/TypeScript"),
    ("pip",    "Python/pip","Python.Python.3.12",    "Proyectos Python"),
    ("cargo",  "Rust",      "Rustlang.Rustup",       "Proyectos Rust"),
    ("go",     "Go",        "GoLang.Go",             "Proyectos Go"),
    ("mvn",    "Maven",     "Apache.Maven",          "Proyectos Java/Maven"),
    ("yarn",   "Yarn",      "Yarn.Yarn",             "Proyectos Node con Yarn"),
]

def scan_tools() -> list:
    """Retorna lista de (cmd, name, winget_id, desc, installed:bool)"""
    results = []
    for cmd, name, wid, desc in REQUIRED_TOOLS:
        installed = _shutil.which(cmd) is not None
        results.append((cmd, name, wid, desc, installed))
    return results

# ── Detectores ecosistema ─────────────────────────────────────────────────────
DETECTORS = [
    ("requirements.txt", ["pip", "install", "-r", "requirements.txt"]),
    ("pyproject.toml",   ["pip", "install", "-e", "."]),
    ("setup.py",         ["pip", "install", "-e", "."]),
    ("package.json",     ["npm", "install"]),
    ("yarn.lock",        ["yarn", "install"]),
    ("pom.xml",          ["mvn", "install", "-q"]),
    ("Cargo.toml",       ["cargo", "build"]),
    ("go.mod",           ["go", "mod", "download"]),
    ("Makefile",         ["make", "install"]),
    ("install.ps1",      ["powershell", "-ExecutionPolicy", "Bypass", "-File", "install.ps1"]),
    ("install.sh",       ["bash", "install.sh"]),
    ("install.bat",      ["cmd", "/c", "install.bat"]),
]

OS_FILES = {
    "windows": [".sln", ".vcxproj", "install.bat", "setup.exe"],
    "linux":   ["CMakeLists.txt", "configure", "Makefile", "install.sh", ".deb", ".rpm"],
    "macos":   [".xcodeproj", ".xcworkspace", "Brewfile"],
    "cross":   ["Dockerfile", "docker-compose.yml", "requirements.txt",
                "package.json", "Cargo.toml", "go.mod", "pyproject.toml"],
}
OS_BADGES = {"windows":"🪟 Windows","linux":"🐧 Linux","macos":"🍎 macOS","cross":"🌐 Cross-platform"}

def detect_os(files: list, topics: list) -> str:
    t = " ".join(topics).lower()
    if "cross-platform" in t or "multiplatform" in t: return "cross"
    if "windows" in t and "linux" not in t: return "windows"
    if "linux" in t and "windows" not in t: return "linux"
    if "macos" in t or "mac-os" in t: return "macos"
    scores = {k: 0 for k in OS_FILES}
    for f in files:
        for k, markers in OS_FILES.items():
            if any(f.endswith(m) or f == m for m in markers):
                scores[k] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "cross"

def detect_installers(folder: Path) -> list:
    for filename, cmd in DETECTORS:
        if (folder / filename).exists():
            return [(filename, cmd)]
    return []

def resolve_url(raw: str) -> str:
    """Desenvuelve l.facebook.com, limpia fbclid y query params."""
    raw = raw.strip()
    if not raw: return raw
    p = urlparse(raw)
    # Caso l.facebook.com/l.php?u=...
    if "facebook.com" in p.netloc and "/l.php" in p.path:
        qs = parse_qs(p.query)
        if "u" in qs:
            raw = unquote(qs["u"][0])
            p = urlparse(raw)
    # Limpiar query params y fragment
    clean = urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", "", ""))
    if "github.com" in clean and not clean.endswith(".git"):
        clean += ".git"
    return clean

def extract_readme_sections(readme_b64: str) -> dict:
    """
    Extrae del README:
      - 'steps': pasos de instalación/prerequisites (listas numeradas o con bullet)
      - 'usage': bloques de código de uso
    """
    import base64
    result = {"steps": [], "usage": []}
    try:
        text = base64.b64decode(readme_b64).decode("utf-8", errors="replace")
    except Exception:
        return result

    next_h_pat  = re.compile(r"^#{1,3}\s+", re.MULTILINE)
    code_pat    = re.compile(r"[\x60]{3}(?:\w+)?\n(.*?)[\x60]{3}", re.DOTALL)
    step_pat    = re.compile(r"^\s*(?:\d+[.)\s]|[-*]\s)(.+)", re.MULTILINE)

    prereq_pat  = re.compile(
        r"^#{1,3}\s*(prerequisite|requirement|before|depend|setup|configurar|antes de|instalar|pasos)",
        re.IGNORECASE | re.MULTILINE)
    usage_pat   = re.compile(
        r"^#{1,3}\s*(usage|quick.?start|getting.?started|uso|run|running|how.?to|cómo usar|ejecutar|comandos|example)",
        re.IGNORECASE | re.MULTILINE)

    def get_section(pat):
        m = pat.search(text)
        if not m: return ""
        start = m.end()
        nxt = next_h_pat.search(text, start)
        return text[start: nxt.start() if nxt else start + 2000]

    # Pasos de instalación
    prereq_section = get_section(prereq_pat)
    if prereq_section:
        steps = step_pat.findall(prereq_section)
        result["steps"] = [s.strip() for s in steps[:8] if s.strip()]
        # También incluir bloques de código de esa sección
        for block in code_pat.findall(prereq_section)[:2]:
            for line in block.strip().splitlines()[:4]:
                l = line.strip()
                if l: result["steps"].append(f"$ {l}")

    # Comandos de uso
    usage_section = get_section(usage_pat)
    if usage_section:
        blocks = code_pat.findall(usage_section)
        result["usage"] = [b.strip() for b in blocks[:4] if b.strip()]
    if not result["usage"]:
        blocks = code_pat.findall(text)
        result["usage"] = [b.strip() for b in blocks[:3] if b.strip()]

    return result

# kept for compat
def extract_usage(readme_b64: str) -> list:
    return extract_readme_sections(readme_b64)["usage"]


def check_internet() -> bool:
    try:
        urlopen(Request("https://github.com", method="HEAD"), timeout=5)
        return True
    except Exception:
        return False

# ── Worker instalador ─────────────────────────────────────────────────────────
class InstallerWorker(QThread):
    sig_output       = pyqtSignal(str, str)
    sig_progress     = pyqtSignal(int)
    sig_done         = pyqtSignal(bool, str)
    sig_missing_tool = pyqtSignal(str, str, str)  # cmd, nombre, winget_id

    def __init__(self, url, dest, token=""):
        super().__init__()
        self.url, self.dest, self.token = url, dest, token.strip()
        self._missing_tool_emitted = False

    def run_cmd(self, cmd, cwd) -> int:
        try:
            proc = subprocess.Popen(cmd, cwd=str(cwd),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace")
            for line in proc.stdout:
                l = line.rstrip()
                if l: self.sig_output.emit(l, "info")
            proc.wait()
            return proc.returncode
        except FileNotFoundError:
            tool = cmd[0]
            if tool in TOOL_INSTALL:
                name, wid = TOOL_INSTALL[tool]
                self.sig_output.emit(f"✗ '{tool}' no instalado — se requiere {name}", "err")
                self.sig_missing_tool.emit(tool, name, wid)
                self._missing_tool_emitted = True
            else:
                self.sig_output.emit(f"✗ Comando no encontrado: {tool}", "err")
            return -1
        except PermissionError:
            # install.ps1 necesita admin — relanzar con runas
            if "install.ps1" in str(cmd):
                self.sig_output.emit("⚠ Se requieren permisos de Administrador — solicitando elevación...", "warn")
                try:
                    import ctypes
                    script = str(Path(cwd) / "install.ps1")
                    ctypes.windll.shell32.ShellExecuteW(
                        None, "runas", "powershell",
                        f'-ExecutionPolicy Bypass -File "{script}"',
                        str(cwd), 1)
                    self.sig_output.emit("✓ Script lanzado como Administrador — sigue las instrucciones en la ventana que abrió", "ok")
                    return 0
                except Exception as e:
                    self.sig_output.emit(f"✗ No se pudo elevar permisos: {e}", "err")
                    return -1
            raise
        except PermissionError as e:
            self.sig_output.emit(f"✗ Permiso denegado: {e}", "err")
            return -1
        except Exception as e:
            self.sig_output.emit(f"✗ Error inesperado: {e}", "err")
            return -1

    def run(self):
        self.sig_progress.emit(5)
        self._missing_tool_emitted = False

        # Validar internet
        if not check_internet():
            self.sig_output.emit("✗ Sin conexión a internet — verifica tu red", "err")
            self.sig_done.emit(False, ""); return

        url = resolve_url(self.url)

        # Validar que sea GitHub
        p = urlparse(url)
        if "github.com" not in p.netloc:
            self.sig_output.emit(f"⚠ URL no apunta a GitHub: {url}", "warn")
            self.sig_output.emit("ℹ Solo se soportan repos de github.com por ahora", "info")
            self.sig_done.emit(False, ""); return

        dest = Path(self.dest)

        # Validar carpeta destino con permisos de escritura
        if not dest.exists():
            self.sig_output.emit(f"✗ Carpeta destino no existe: {dest}", "err")
            self.sig_done.emit(False, ""); return
        if not os.access(dest, os.W_OK):
            self.sig_output.emit(f"✗ Sin permisos de escritura en: {dest}", "err")
            self.sig_done.emit(False, ""); return

        repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
        if not repo_name:
            self.sig_output.emit("✗ No se pudo extraer el nombre del repo de la URL", "err")
            self.sig_done.emit(False, ""); return

        clone_dest = dest / repo_name

        # Eliminar carpeta existente
        if clone_dest.exists():
            self.sig_output.emit(f"⚠ '{clone_dest.name}' ya existe — sobreescribiendo...", "warn")
            try:
                def _force_remove(func, path, _):
                    try:
                        os.chmod(path, 0o777)
                        func(path)
                    except Exception:
                        pass
                shutil.rmtree(clone_dest, onerror=_force_remove)
            except Exception as e:
                self.sig_output.emit(f"✗ No se pudo eliminar carpeta existente: {e}", "err")
                self.sig_done.emit(False, ""); return

        # Construir URL con token opcional
        clone_url = url
        if self.token:
            clone_url = f"{p.scheme}://{self.token}@{p.netloc}{p.path}"

        # Git clone
        self.sig_output.emit(f"→ git clone {url}", "info")
        rc = self.run_cmd(["git", "clone", "--recurse-submodules", clone_url, str(clone_dest)], dest)
        if rc != 0:
            if not self._missing_tool_emitted:
                if rc == 128:
                    self.sig_output.emit("✗ Repo no encontrado, privado o URL incorrecta", "err")
                    self.sig_output.emit("ℹ Si es privado, agrega tu token PAT", "info")
                else:
                    self.sig_output.emit("✗ git clone falló — revisa la URL o token PAT", "err")
            self.sig_done.emit(False, ""); return

        self.sig_progress.emit(40)
        self.sig_output.emit("✓ Clone completado", "ok")

        # .env.example → .env
        env_src = clone_dest / ".env.example"
        if env_src.exists() and not (clone_dest / ".env").exists():
            try:
                shutil.copy(env_src, clone_dest / ".env")
                self.sig_output.emit("⚠ .env.example copiado a .env — revisa variables", "warn")
            except Exception as e:
                self.sig_output.emit(f"⚠ No se pudo copiar .env.example: {e}", "warn")

        # Instalar dependencias
        installers = detect_installers(clone_dest)
        if not installers:
            self.sig_output.emit("ℹ Sin gestor de dependencias detectado — listo.", "info")
            self.sig_progress.emit(100)
            self.sig_done.emit(True, str(clone_dest)); return

        self.sig_progress.emit(50)
        all_ok = True
        for filename, cmd in installers:
            self.sig_output.emit(f"→ [{filename}] → {' '.join(cmd)}", "info")
            rc = self.run_cmd(cmd, clone_dest)
            if rc == 0:
                self.sig_output.emit("✓ Dependencias instaladas", "ok")
            elif self._missing_tool_emitted:
                all_ok = False
                break
            else:
                self.sig_output.emit(f"✗ Error instalando dependencias (código {rc})", "err")
                all_ok = False

        self.sig_progress.emit(100)
        # Si faltó herramienta: el repo SÍ fue clonado, informar ruta igual
        self.sig_done.emit(True, str(clone_dest))

# ── Worker instalación masiva ────────────────────────────────────────────────
class BulkInstallerWorker(QThread):
    sig_output   = pyqtSignal(str, str)
    sig_tool_done = pyqtSignal(str, bool)  # nombre, ok
    sig_done     = pyqtSignal()

    def __init__(self, tools: list):
        super().__init__()
        # tools: lista de (cmd, name, winget_id)
        self.tools = tools

    def run(self):
        for cmd, name, wid in self.tools:
            self.sig_output.emit(f"→ Instalando {name}...", "info")
            try:
                proc = subprocess.Popen(
                    ["winget", "install", "--id", wid, "-e",
                     "--accept-package-agreements", "--accept-source-agreements"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace")
                for line in proc.stdout:
                    l = line.rstrip()
                    if l: self.sig_output.emit(l, "info")
                proc.wait()
                ok = proc.returncode == 0
                self.sig_output.emit(
                    f"{'✓' if ok else '✗'} {name} {'instalado' if ok else 'falló'}", 
                    "ok" if ok else "err")
                self.sig_tool_done.emit(name, ok)
            except FileNotFoundError:
                self.sig_output.emit(f"✗ winget no disponible — instala manualmente", "err")
                self.sig_tool_done.emit(name, False)
                break
            except Exception as e:
                self.sig_output.emit(f"✗ Error: {e}", "err")
                self.sig_tool_done.emit(name, False)
        self.sig_done.emit()

# ── Worker winget ─────────────────────────────────────────────────────────────
class ToolInstallerWorker(QThread):
    sig_output = pyqtSignal(str, str)
    sig_done   = pyqtSignal(bool, str)

    def __init__(self, name, winget_id):
        super().__init__()
        self.name, self.winget_id = name, winget_id

    def run(self):
        self.sig_output.emit(f"→ Instalando {self.name} via winget...", "info")
        try:
            proc = subprocess.Popen(
                ["winget", "install", "--id", self.winget_id, "-e",
                 "--accept-package-agreements", "--accept-source-agreements"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace")
            for line in proc.stdout:
                l = line.rstrip()
                if l: self.sig_output.emit(l, "info")
            proc.wait()
            if proc.returncode == 0:
                self.sig_output.emit(f"✓ {self.name} instalado — reinicia GetGit y reintenta", "ok")
                self.sig_done.emit(True, self.name)
            else:
                self.sig_output.emit(f"✗ winget retornó código {proc.returncode}", "err")
                self.sig_done.emit(False, self.name)
        except FileNotFoundError:
            self.sig_output.emit("✗ winget no disponible en este sistema", "err")
            self.sig_output.emit("ℹ Instala manualmente desde: https://winget.run", "info")
            self.sig_done.emit(False, self.name)
        except Exception as e:
            self.sig_output.emit(f"✗ Error inesperado: {e}", "err")
            self.sig_done.emit(False, self.name)

# ── Worker preview GitHub API ─────────────────────────────────────────────────
class GithubPreviewWorker(QThread):
    sig_result = pyqtSignal(dict)
    sig_error  = pyqtSignal(str)

    def __init__(self, owner, repo):
        super().__init__()
        self.owner, self.repo = owner, repo
        self._cancelled = False

    def cancel(self): self._cancelled = True

    def _get(self, url):
        if self._cancelled: return None
        try:
            req = Request(url, headers={"User-Agent":"GetGit/1.0","Accept":"application/vnd.github+json"})
            with urlopen(req, timeout=8) as r:
                return json.loads(r.read().decode())
        except Exception:
            return None

    def run(self):
        base = f"https://api.github.com/repos/{self.owner}/{self.repo}"
        meta = self._get(base)
        if self._cancelled: return
        if not meta:
            self.sig_error.emit("Sin conexión o repo no encontrado"); return
        if "message" in meta:
            msg = meta["message"]
            if "rate limit" in msg.lower():
                self.sig_error.emit("Rate limit GitHub API — espera 1 min o agrega token PAT")
            else:
                self.sig_error.emit(msg[:60])
            return
        contents = self._get(f"{base}/contents") or []
        topics   = self._get(f"{base}/topics") or {}
        readme   = self._get(f"{base}/readme") or {}
        meta["_files"]   = [i["name"] for i in contents if isinstance(i, dict)]
        meta["_topics"]  = topics
        sections         = extract_readme_sections(readme.get("content", ""))
        meta["_usage"]   = sections["usage"]
        meta["_steps"]   = sections["steps"]
        if not self._cancelled:
            self.sig_result.emit(meta)

# ── Ventana principal ─────────────────────────────────────────────────────────
COLLAPSED_H = 46
EXPANDED_H  = 510
WIDTH       = 440

class GetGitWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.history       = load_history()
        self.config        = load_config()
        self.drag_pos      = QPoint()
        self.final_path    = ""
        self.expanded      = False
        self._api_worker   = None
        self._preview_timer = QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._fetch_repo_info)
        self._current_preview_url = ""
        self._build_ui()
        self._position_window()
        QApplication.instance().focusChanged.connect(self._on_focus_changed)
        # Timer que colapsa si la ventana pierde foco (fallback para Tool/StaysOnTop)
        self._focus_timer = QTimer()
        self._focus_timer.setInterval(300)
        self._focus_timer.timeout.connect(self._check_focus)
        self._focus_timer.start()

    def _position_window(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - WIDTH - 20, screen.top() + 20)

    def _build_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(WIDTH)
        self.setFixedHeight(COLLAPSED_H)

        self.container = QWidget(self)
        self.container.setGeometry(0, 0, WIDTH, COLLAPSED_H)
        self.container.setStyleSheet("""
            QWidget { background:rgba(13,17,23,215); border-radius:12px;
                      font-family:'Consolas','Courier New',monospace; font-size:11px; color:#e6edf3; }
        """)

        self.main_lay = QVBoxLayout(self.container)
        self.main_lay.setContentsMargins(10, 6, 10, 6)
        self.main_lay.setSpacing(6)

        # ── Fila pill siempre visible ─────────────────────────────────────────
        pill_row = QHBoxLayout()
        pill_row.setSpacing(6)
        lbl_icon = QLabel("⚡")
        lbl_icon.setStyleSheet("color:#58a6ff; font-size:14px; background:transparent;")
        lbl_icon.setFixedWidth(20)
        pill_row.addWidget(lbl_icon)

        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("Pega link de GitHub... (Ctrl+V)")
        self.input_url.setStyleSheet("""
            QLineEdit { background:rgba(1,4,9,180); border:1px solid #30363d;
                        border-radius:8px; padding:5px 10px; color:#58a6ff; font-size:11px; }
            QLineEdit:focus { border:1px solid #58a6ff; }
        """)
        self.input_url.textChanged.connect(self._on_url_changed)
        self.input_url.installEventFilter(self)
        pill_row.addWidget(self.input_url)

        btn_diag = QPushButton("🔍")
        btn_diag.setFixedSize(28, 28)
        btn_diag.setToolTip("Diagnóstico del sistema")
        btn_diag.setStyleSheet("""
            QPushButton{background:transparent;border:none;color:#484f58;font-size:13px;border-radius:14px;}
            QPushButton:hover{background:#21262d;color:#e3b341;}
        """)
        btn_diag.clicked.connect(self._toggle_diag)
        pill_row.addWidget(btn_diag)

        btn_close = QPushButton("×")
        btn_close.setFixedSize(24, 24)
        btn_close.setStyleSheet("""
            QPushButton { background:transparent; border:none; color:#484f58; font-size:16px; border-radius:12px; }
            QPushButton:hover { background:#f85149; color:#fff; }
        """)
        btn_close.clicked.connect(self.close)
        pill_row.addWidget(btn_close)
        self.main_lay.addLayout(pill_row)

        # ── Panel expandible ──────────────────────────────────────────────────
        self.panel = QWidget()
        self.panel.setVisible(False)
        panel_lay = QVBoxLayout(self.panel)
        panel_lay.setContentsMargins(0, 4, 0, 0)
        panel_lay.setSpacing(6)

        # ── Panel diagnóstico (oculto por default) ───────────────────────────
        self.frame_diag = QFrame()
        self.frame_diag.setVisible(False)
        self.frame_diag.setStyleSheet("""
            QFrame { background:rgba(13,17,10,200); border:1px solid #2d3f1f; border-radius:8px; }
        """)
        diag_lay = QVBoxLayout(self.frame_diag)
        diag_lay.setContentsMargins(10, 8, 10, 8)
        diag_lay.setSpacing(4)

        diag_header = QHBoxLayout()
        lbl_diag_title = QLabel("🔍 DIAGNÓSTICO DEL SISTEMA")
        lbl_diag_title.setStyleSheet("color:#8b949e; font-size:9px; letter-spacing:2px; background:transparent; border:none;")
        diag_header.addWidget(lbl_diag_title)
        diag_header.addStretch()
        self.btn_refresh_diag = QPushButton("↻")
        self.btn_refresh_diag.setFixedSize(22, 22)
        self.btn_refresh_diag.setStyleSheet("QPushButton{background:#21262d;border:1px solid #30363d;border-radius:4px;color:#8b949e;font-size:12px;}"
                                            "QPushButton:hover{background:#30363d;color:#e6edf3;}")
        self.btn_refresh_diag.clicked.connect(self._run_diag)
        diag_header.addWidget(self.btn_refresh_diag)
        diag_lay.addLayout(diag_header)

        self.diag_rows = QWidget()
        self.diag_rows.setStyleSheet("background:transparent;")
        self.diag_rows_lay = QVBoxLayout(self.diag_rows)
        self.diag_rows_lay.setContentsMargins(0, 4, 0, 0)
        self.diag_rows_lay.setSpacing(3)
        diag_lay.addWidget(self.diag_rows)

        self.btn_install_all = QPushButton("⚡ Instalar todo lo faltante")
        self.btn_install_all.setVisible(False)
        self.btn_install_all.setStyleSheet("""
            QPushButton{background:#6e40c9;border:1px solid #8957e5;border-radius:6px;
                        padding:6px 12px;color:#fff;font-size:10px;}
            QPushButton:hover{background:#8957e5;}
            QPushButton:disabled{background:#21262d;color:#484f58;border-color:#30363d;}
        """)
        self.btn_install_all.clicked.connect(self._install_all_missing)
        diag_lay.addWidget(self.btn_install_all)

        panel_lay.addWidget(self.frame_diag)

        # Preview
        self.frame_preview = QFrame()
        self.frame_preview.setStyleSheet("""
            QFrame { background:rgba(13,25,38,200); border:1px solid #1f3d5a; border-radius:8px; }
        """)
        prev_lay = QVBoxLayout(self.frame_preview)
        prev_lay.setContentsMargins(10, 8, 10, 8)
        prev_lay.setSpacing(3)

        row_name = QHBoxLayout()
        self.lbl_repo_name = QLabel("ℹ Esperando URL...")
        self.lbl_repo_name.setStyleSheet("color:#58a6ff; font-size:12px; font-weight:bold; background:transparent; border:none;")
        row_name.addWidget(self.lbl_repo_name)
        row_name.addStretch()
        self.lbl_stars = QLabel("")
        self.lbl_stars.setStyleSheet("color:#e3b341; font-size:10px; background:transparent; border:none;")
        row_name.addWidget(self.lbl_stars)
        prev_lay.addLayout(row_name)

        self.lbl_desc = QLabel("")
        self.lbl_desc.setStyleSheet("color:#8b949e; font-size:10px; background:transparent; border:none;")
        self.lbl_desc.setWordWrap(True)
        prev_lay.addWidget(self.lbl_desc)

        row_tags = QHBoxLayout()
        row_tags.setSpacing(4)
        def _tag(fg, bg):
            l = QLabel("")
            l.setStyleSheet(f"color:{fg}; background:{bg}; border-radius:3px; padding:1px 6px; font-size:10px; border:none;")
            return l
        self.lbl_lang      = _tag("#79c0ff","#1f3d5a")
        self.lbl_os        = _tag("#d2a8ff","#2d1f5a")
        self.lbl_installer = _tag("#56d364","#0f2d1a")
        self.lbl_license   = _tag("#8b949e","#21262d")
        for w in [self.lbl_lang, self.lbl_os, self.lbl_installer, self.lbl_license]:
            row_tags.addWidget(w)
        row_tags.addStretch()
        prev_lay.addLayout(row_tags)

        # Comandos de uso
        # Pasos de instalación
        self.lbl_steps_title = QLabel("PASOS DE INSTALACIÓN")
        self.lbl_steps_title.setStyleSheet("color:#484f58; font-size:9px; letter-spacing:2px; background:transparent; border:none; margin-top:4px;")
        self.lbl_steps_title.setVisible(False)
        prev_lay.addWidget(self.lbl_steps_title)

        self.steps_container = QWidget()
        self.steps_container.setStyleSheet("background:transparent;")
        self.steps_lay = QVBoxLayout(self.steps_container)
        self.steps_lay.setContentsMargins(0, 2, 0, 0)
        self.steps_lay.setSpacing(2)
        self.steps_container.setVisible(False)
        prev_lay.addWidget(self.steps_container)

        self.lbl_usage_title = QLabel("COMANDOS DE USO")
        self.lbl_usage_title.setStyleSheet("color:#484f58; font-size:9px; letter-spacing:2px; background:transparent; border:none; margin-top:4px;")
        self.lbl_usage_title.setVisible(False)
        prev_lay.addWidget(self.lbl_usage_title)

        self.usage_container = QWidget()
        self.usage_container.setStyleSheet("background:transparent;")
        self.usage_lay = QVBoxLayout(self.usage_container)
        self.usage_lay.setContentsMargins(0, 2, 0, 0)
        self.usage_lay.setSpacing(4)
        self.usage_container.setVisible(False)
        prev_lay.addWidget(self.usage_container)

        panel_lay.addWidget(self.frame_preview)

        # Destino
        row_dest = QHBoxLayout()
        self.txt_dest = QLineEdit(self.config.get("last_dest", DEFAULT_DEST))
        self.txt_dest.setStyleSheet("""
            QLineEdit { background:rgba(1,4,9,180); border:1px solid #30363d;
                        border-radius:6px; padding:5px 8px; color:#3fb950; font-size:11px; }
        """)
        btn_browse = QPushButton("📁")
        btn_browse.setFixedWidth(32)
        btn_browse.setStyleSheet("QPushButton{background:#21262d;border:1px solid #30363d;border-radius:6px;padding:4px;}"
                                 "QPushButton:hover{background:#30363d;}")
        btn_browse.clicked.connect(self._browse)
        row_dest.addWidget(self.txt_dest)
        row_dest.addWidget(btn_browse)
        panel_lay.addLayout(row_dest)

        # Token
        self.txt_token = QLineEdit()
        self.txt_token.setPlaceholderText("Token PAT (solo repos privados)")
        self.txt_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_token.setStyleSheet("""
            QLineEdit { background:rgba(1,4,9,180); border:1px solid #30363d;
                        border-radius:6px; padding:5px 8px; color:#8b949e; font-size:11px; }
        """)
        panel_lay.addWidget(self.txt_token)

        # Log
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(110)
        self.log.setStyleSheet("""
            QTextEdit { background:rgba(1,4,9,200); border:1px solid #21262d;
                        border-radius:6px; color:#8b949e; padding:4px; font-size:10px; }
        """)
        panel_lay.addWidget(self.log)

        # Progreso
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setStyleSheet("""
            QProgressBar { background:#21262d; border:none; border-radius:2px; max-height:3px; color:transparent; }
            QProgressBar::chunk { background:#58a6ff; border-radius:2px; }
        """)
        panel_lay.addWidget(self.progress)

        # Botones acción
        row_btns = QHBoxLayout()
        self.btn_log = QPushButton("💾 Log")
        self.btn_log.setStyleSheet("QPushButton{background:#21262d;border:1px solid #30363d;border-radius:6px;padding:6px 10px;color:#8b949e;}"
                                   "QPushButton:hover{background:#30363d;color:#e6edf3;}")
        self.btn_log.clicked.connect(self._save_log)

        self.btn_install = QPushButton("⚡ INSTALAR")
        self.btn_install.setStyleSheet("""
            QPushButton{background:#238636;border:1px solid #2ea043;border-radius:6px;
                        padding:7px 16px;color:#fff;font-weight:bold;letter-spacing:1px;}
            QPushButton:hover{background:#2ea043;}
            QPushButton:disabled{background:#21262d;color:#484f58;border-color:#30363d;}
        """)
        self.btn_install.clicked.connect(self._start_install)

        self.btn_copy = QPushButton("📎 Ruta")
        self.btn_copy.setEnabled(False)
        self.btn_copy.setStyleSheet("QPushButton{background:#21262d;border:1px solid #30363d;border-radius:6px;padding:6px 10px;color:#8b949e;}"
                                    "QPushButton:hover{background:#30363d;color:#e6edf3;}"
                                    "QPushButton:disabled{color:#484f58;}")
        self.btn_copy.clicked.connect(self._copy_path)

        row_btns.addWidget(self.btn_log)
        row_btns.addWidget(self.btn_install)
        row_btns.addWidget(self.btn_copy)
        panel_lay.addLayout(row_btns)

        # Botón instalador de herramienta (oculto por default)
        self.btn_tool = QPushButton("")
        self.btn_tool.setVisible(False)
        self.btn_tool.setStyleSheet("""
            QPushButton{background:#6e40c9;border:1px solid #8957e5;border-radius:6px;
                        padding:6px 12px;color:#fff;font-size:10px;}
            QPushButton:hover{background:#8957e5;}
            QPushButton:disabled{background:#21262d;color:#484f58;}
        """)
        panel_lay.addWidget(self.btn_tool)

        self.main_lay.addWidget(self.panel)

    # ── Expand / Collapse ─────────────────────────────────────────────────────
    def _expand(self):
        if self.expanded: return
        self.expanded = True
        self.panel.setVisible(True)
        self.setFixedHeight(EXPANDED_H)
        self.container.setGeometry(0, 0, WIDTH, EXPANDED_H)
        self.setWindowOpacity(0.97)

    def _collapse(self):
        if not self.expanded: return
        self.expanded = False
        self.panel.setVisible(False)
        self.setFixedHeight(COLLAPSED_H)
        self.container.setGeometry(0, 0, WIDTH, COLLAPSED_H)
        self.setWindowOpacity(0.82)

    def _on_focus_changed(self, old, now):
        """Foco entre widgets internos."""
        if now is None: return
        w = now
        while w:
            if w is self: self._expand(); return
            w = w.parent()
        # Foco fue a otro widget de otra ventana Qt
        self._collapse()

    def changeEvent(self, event):
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.WindowDeactivate:
            self._collapse()
        super().changeEvent(event)

    def _check_focus(self):
        """Polling: colapsa si ningún widget de esta ventana tiene foco."""
        if not self.expanded:
            return
        focused = QApplication.focusWidget()
        if focused is None:
            self._collapse()
            return
        w = focused
        while w:
            if w is self:
                return  # foco está adentro, no colapsar
            w = w.parent()
        self._collapse()

    def eventFilter(self, obj, event):
        if obj is self.input_url and event.type() == QEvent.Type.MouseButtonPress:
            self._expand()
        return super().eventFilter(obj, event)

    # ── Arrastrar ─────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton and not self.drag_pos.isNull():
            self.move(e.globalPosition().toPoint() - self.drag_pos)

    # ── Carpeta ───────────────────────────────────────────────────────────────
    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta destino", self.txt_dest.text())
        if folder:
            self.txt_dest.setText(folder)
            self.config["last_dest"] = folder
            save_config(self.config)

    # ── Diagnóstico ───────────────────────────────────────────────────────────
    def _toggle_diag(self):
        self._expand()
        visible = self.frame_diag.isVisible()
        self.frame_diag.setVisible(not visible)
        if not visible:
            self._run_diag()

    def _run_diag(self):
        # Limpiar filas anteriores
        while self.diag_rows_lay.count():
            item = self.diag_rows_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        results = scan_tools()
        missing = []
        for cmd, name, wid, desc, installed in results:
            row = QHBoxLayout()
            icon = QLabel("✓" if installed else "✗")
            icon.setFixedWidth(16)
            icon.setStyleSheet(f"color:{'#3fb950' if installed else '#f85149'}; background:transparent; border:none; font-size:12px;")
            lbl = QLabel(f"{name}")
            lbl.setFixedWidth(90)
            lbl.setStyleSheet(f"color:{'#e6edf3' if installed else '#f85149'}; background:transparent; border:none; font-size:10px;")
            lbl_desc = QLabel(desc)
            lbl_desc.setStyleSheet("color:#484f58; background:transparent; border:none; font-size:9px;")
            lbl_status = QLabel("instalado" if installed else "FALTANTE")
            lbl_status.setFixedWidth(60)
            lbl_status.setStyleSheet(f"color:{'#3fb950' if installed else '#e3b341'}; background:transparent; border:none; font-size:9px;")
            row.addWidget(icon)
            row.addWidget(lbl)
            row.addWidget(lbl_desc)
            row.addStretch()
            row.addWidget(lbl_status)
            self.diag_rows_lay.addLayout(row)
            if not installed:
                missing.append((cmd, name, wid))

        self.btn_install_all.setVisible(len(missing) > 0)
        self.btn_install_all.setEnabled(True)
        if missing:
            self.btn_install_all.setText(f"⚡ Instalar {len(missing)} herramienta{'s' if len(missing)>1 else ''} faltante{'s' if len(missing)>1 else ''}")
        self._missing_tools = missing

        # Ajustar altura expandida
        extra = len(results) * 22 + 60
        new_h = EXPANDED_H + extra
        self.setFixedHeight(new_h)
        self.container.setGeometry(0, 0, WIDTH, new_h)

    def _install_all_missing(self):
        if not hasattr(self, '_missing_tools') or not self._missing_tools:
            return
        self.btn_install_all.setEnabled(False)
        self.btn_install_all.setText("⏳ Instalando...")
        self.log.clear()
        self._expand()
        self._bulk_worker = BulkInstallerWorker(self._missing_tools)
        self._bulk_worker.sig_output.connect(self._log)
        self._bulk_worker.sig_tool_done.connect(lambda name, ok:
            self._log(f"{'✓' if ok else '✗'} {name}", "ok" if ok else "err"))
        self._bulk_worker.sig_done.connect(self._on_bulk_done)
        self._bulk_worker.start()

    def _on_bulk_done(self):
        self._log("✓ Listo — reinicia GetGit para que los cambios tomen efecto", "ok")
        self.btn_install_all.setText("↻ Re-escanear")
        self.btn_install_all.setEnabled(True)
        try: self.btn_install_all.clicked.disconnect()
        except: pass
        self.btn_install_all.clicked.connect(self._run_diag)

    # ── Preview GitHub API ────────────────────────────────────────────────────
    def _on_url_changed(self, url: str):
        self._current_preview_url = url.strip()
        # Cancelar worker previo si aún corre
        if self._api_worker and self._api_worker.isRunning():
            self._api_worker.cancel()
        self._preview_timer.stop()
        if not self._current_preview_url:
            self.lbl_repo_name.setText("ℹ Esperando URL...")
            return
        self._expand()
        self.lbl_repo_name.setText("⏳ Consultando...")
        for l in [self.lbl_stars, self.lbl_desc, self.lbl_lang, self.lbl_os, self.lbl_installer, self.lbl_license]:
            l.setText("")
        self.lbl_steps_title.setVisible(False)
        self.steps_container.setVisible(False)
        self._preview_timer.start(600)

    def _parse_owner_repo(self, url: str):
        resolved = resolve_url(url)
        p = urlparse(resolved)
        if "github.com" not in p.netloc: return None, None
        parts = [x for x in p.path.rstrip("/").replace(".git","").split("/") if x]
        if len(parts) >= 2: return parts[0], parts[1]
        return None, None

    def _fetch_repo_info(self):
        owner, repo = self._parse_owner_repo(self._current_preview_url)
        if not owner:
            self.lbl_repo_name.setText("⚠ URL no reconocida como GitHub")
            return
        self._api_worker = GithubPreviewWorker(owner, repo)
        self._api_worker.sig_result.connect(self._on_preview_result)
        self._api_worker.sig_error.connect(lambda e: self.lbl_repo_name.setText(f"⚠ {e}"))
        self._api_worker.start()

    def _on_preview_result(self, data: dict):
        name   = data.get("name","—")
        desc   = data.get("description") or "Sin descripción"
        stars  = data.get("stargazers_count", 0)
        lang   = data.get("language") or ""
        lic    = (data.get("license") or {}).get("spdx_id","")
        files  = data.get("_files",[])
        topics = (data.get("_topics") or {}).get("names",[])

        self.lbl_repo_name.setText(f"  {name}")
        self.lbl_desc.setText(desc[:100]+("…" if len(desc)>100 else ""))
        self.lbl_stars.setText(f"★ {stars:,}" if stars else "")
        self.lbl_lang.setText(f" {lang}" if lang else "")
        self.lbl_license.setText(f" {lic}" if lic else "")
        self.lbl_os.setText(f" {OS_BADGES[detect_os(files,topics)]}")
        inst = next((f for f,_ in DETECTORS if f in files), None)
        self.lbl_installer.setText(f" {inst}" if inst else "")

        # Limpiar pasos previos
        while self.steps_lay.count():
            item = self.steps_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        steps = data.get("_steps", [])
        if steps:
            self.lbl_steps_title.setVisible(True)
            self.steps_container.setVisible(True)
            for i, step in enumerate(steps, 1):
                lbl_step = QLabel(f"{i}. {step}")
                lbl_step.setWordWrap(True)
                lbl_step.setStyleSheet("""
                    color:#c9d1d9; background:transparent; border:none;
                    font-size:10px; padding:1px 0;
                """)
                self.steps_lay.addWidget(lbl_step)
        else:
            self.lbl_steps_title.setVisible(False)
            self.steps_container.setVisible(False)

        # Aviso install.ps1 requiere admin
        if "install.ps1" in files:
            lbl_ps = QLabel("⚠ install.ps1 detectado — se ejecutará como Administrador")
            lbl_ps.setStyleSheet("color:#e3b341; background:rgba(40,30,0,180); border:1px solid #5a4a00; border-radius:4px; padding:3px 8px; font-size:10px;")
            lbl_ps.setWordWrap(True)
            self.steps_lay.addWidget(lbl_ps)
            self.lbl_steps_title.setVisible(True)
            self.steps_container.setVisible(True)

        # Limpiar comandos previos
        while self.usage_lay.count():
            item = self.usage_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        usage = data.get("_usage", [])
        if usage:
            self.lbl_usage_title.setVisible(True)
            self.usage_container.setVisible(True)
            for block in usage:
                lines = block.strip().splitlines()
                for line in lines[:6]:  # max 6 líneas por bloque
                    line = line.strip()
                    if not line: continue
                    row = QHBoxLayout()
                    lbl_cmd = QLabel(line)
                    lbl_cmd.setStyleSheet("""
                        color:#e6edf3; background:rgba(1,4,9,200);
                        border:1px solid #30363d; border-radius:4px;
                        padding:3px 8px; font-size:10px; font-family:'Consolas','Courier New',monospace;
                    """)
                    lbl_cmd.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    lbl_cmd.setCursor(Qt.CursorShape.IBeamCursor)
                    btn_copy_cmd = QPushButton("⎘")
                    btn_copy_cmd.setFixedSize(22, 22)
                    btn_copy_cmd.setStyleSheet("""
                        QPushButton{background:#21262d;border:1px solid #30363d;border-radius:4px;color:#8b949e;font-size:11px;}
                        QPushButton:hover{background:#30363d;color:#e6edf3;}
                    """)
                    btn_copy_cmd.setToolTip("Copiar comando")
                    btn_copy_cmd.clicked.connect(lambda _, l=line: (
                        QApplication.clipboard().setText(l)
                    ))
                    row.addWidget(lbl_cmd)
                    row.addWidget(btn_copy_cmd)
                    self.usage_lay.addLayout(row)
        else:
            self.lbl_usage_title.setVisible(False)
            self.usage_container.setVisible(False)

    # ── Instalación ───────────────────────────────────────────────────────────
    def _start_install(self):
        url  = self.input_url.text().strip()
        dest = self.txt_dest.text().strip()
        if not url:
            self._log("✗ Ingresa una URL", "err"); return
        if not dest:
            self._log("✗ Selecciona una carpeta destino", "err"); return
        if not Path(dest).exists():
            self._log(f"✗ La carpeta no existe: {dest}", "err"); return

        self.log.clear()
        self.progress.setValue(0)
        self.btn_install.setEnabled(False)
        self.btn_copy.setEnabled(False)
        self.btn_tool.setVisible(False)
        self.final_path = ""
        self.history = save_history(url, self.history)

        self.worker = InstallerWorker(url, dest, self.txt_token.text())
        self.worker.sig_output.connect(self._log)
        self.worker.sig_progress.connect(self.progress.setValue)
        self.worker.sig_done.connect(self._on_done)
        self.worker.sig_missing_tool.connect(self._on_missing_tool)
        self.worker.start()

    def _on_done(self, ok: bool, path: str):
        self.btn_install.setEnabled(True)
        if ok and path:
            self.final_path = path
            self.btn_copy.setEnabled(True)
            self._log("─" * 38, "info")
            self._log(f"✓ Listo → {path}", "ok")
            self._log("⚡ Puedes instalar otro repo.", "info")
            self.lbl_repo_name.setText(f"✓ {Path(path).name} instalado")
        elif not ok:
            self._log("─" * 38, "info")
            self._log("✗ Instalación fallida — revisa el log", "err")

    def _on_missing_tool(self, cmd: str, name: str, winget_id: str):
        self.btn_tool.setText(f"⚡ Instalar {name} automáticamente")
        self.btn_tool.setVisible(True)
        # Desconectar señales previas
        try: self.btn_tool.clicked.disconnect()
        except Exception: pass
        self.btn_tool.clicked.connect(lambda: self._install_tool(name, winget_id))

    def _install_tool(self, name: str, winget_id: str):
        self.btn_tool.setEnabled(False)
        self.btn_tool.setText(f"⏳ Instalando {name}...")
        self._tool_worker = ToolInstallerWorker(name, winget_id)
        self._tool_worker.sig_output.connect(self._log)
        self._tool_worker.sig_done.connect(self._on_tool_installed)
        self._tool_worker.start()

    def _on_tool_installed(self, ok: bool, name: str):
        self.btn_tool.setVisible(False)
        if ok:
            self._log(f"✓ {name} instalado — cierra y vuelve a abrir GetGit, luego reintenta", "ok")
        else:
            self._log(f"✗ No se pudo instalar {name} — instálalo manualmente", "err")

    def _log(self, text: str, tipo: str = "info"):
        colors = {"ok":"#3fb950","warn":"#e3b341","err":"#f85149","info":"#8b949e"}
        self.log.append(f'<span style="color:{colors.get(tipo,"#8b949e")}">{text}</span>')

    def _copy_path(self):
        if self.final_path:
            QApplication.clipboard().setText(self.final_path)
            self.btn_copy.setText("✓")
            QTimer.singleShot(2000, lambda: self.btn_copy.setText("📎 Ruta"))

    def _save_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Guardar log",
            str(Path.home() / "getgit_log.txt"), "Text (*.txt)")
        if path:
            try:
                Path(path).write_text(self.log.toPlainText(), encoding="utf-8")
                self._log("✓ Log guardado", "ok")
            except Exception as e:
                self._log(f"✗ No se pudo guardar: {e}", "err")

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = GetGitWindow()
    win.show()
    win.setWindowOpacity(0.82)
    sys.exit(app.exec())
