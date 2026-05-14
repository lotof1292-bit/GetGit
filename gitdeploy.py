"""
GitDeploy — Ventana flotante instaladora de repos GitHub
Plataforma: Windows | Stack: Python 3.x + PyQt6
Autor: Eli / generado con Claude
"""
import sys, os, json, shutil, subprocess, re
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFileDialog,
    QComboBox, QProgressBar, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint, QTimer
from PyQt6.QtGui import QFont, QClipboard

# ── Rutas ────────────────────────────────────────────────────────────────────
HISTORY_FILE = Path(__file__).parent / "history.json"
MAX_HISTORY  = 10
DEFAULT_DEST = str(Path.home())

# ── Detectores de ecosistema ──────────────────────────────────────────────────
DETECTORS = [
    ("requirements.txt",  ["pip", "install", "-r", "requirements.txt"]),
    ("pyproject.toml",    ["pip", "install", "-e", "."]),
    ("setup.py",          ["pip", "install", "-e", "."]),
    ("package.json",      ["npm", "install"]),
    ("yarn.lock",         ["yarn", "install"]),
    ("pom.xml",           ["mvn", "install", "-q"]),
    ("Cargo.toml",        ["cargo", "build"]),
    ("go.mod",            ["go", "mod", "download"]),
    ("Makefile",          ["make", "install"]),
    ("install.sh",        ["bash", "install.sh"]),
    ("install.bat",       ["cmd", "/c", "install.bat"]),
]

ENV_EXAMPLE = ".env.example"
ENV_TARGET  = ".env"

# ── Tema ──────────────────────────────────────────────────────────────────────
STYLE = """
QWidget {
    background: #0d1117;
    color: #e6edf3;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
}
QLineEdit, QComboBox {
    background: #010409;
    border: 1px solid #30363d;
    border-radius: 5px;
    padding: 5px 8px;
    color: #58a6ff;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #58a6ff; }
QComboBox QAbstractItemView {
    background: #161b22;
    color: #8b949e;
    border: 1px solid #30363d;
    selection-background-color: #21262d;
}
QTextEdit {
    background: #010409;
    border: 1px solid #30363d;
    border-radius: 5px;
    color: #8b949e;
    padding: 4px;
}
QPushButton {
    border: 1px solid #30363d;
    border-radius: 5px;
    padding: 6px 12px;
    background: #21262d;
    color: #8b949e;
}
QPushButton:hover   { background: #30363d; color: #e6edf3; }
QPushButton:pressed { background: #161b22; }
QPushButton#btn_install {
    background: #238636;
    border: 1px solid #2ea043;
    color: #ffffff;
    font-weight: bold;
    letter-spacing: 1px;
    padding: 8px 16px;
}
QPushButton#btn_install:hover    { background: #2ea043; }
QPushButton#btn_install:disabled {
    background: #21262d; color: #484f58; border-color: #30363d;
}
QProgressBar {
    background: #21262d; border: none;
    border-radius: 2px; max-height: 3px;
    text-align: center; color: transparent;
}
QProgressBar::chunk { background: #58a6ff; border-radius: 2px; }
QLabel#lbl_section {
    color: #484f58; font-size: 9px; letter-spacing: 2px;
}
QLabel#lbl_detected {
    color: #58a6ff; background: #0d1926;
    border: 1px solid #1f3d5a; border-radius: 5px; padding: 4px 8px;
}
"""

# ── Historial ─────────────────────────────────────────────────────────────────
def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_history(url: str, history: list) -> list:
    if url in history:
        history.remove(url)
    history.insert(0, url)
    history = history[:MAX_HISTORY]
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return history

# ── Detección de instaladores ─────────────────────────────────────────────────
def detect_installers(folder: Path) -> list:
    found = []
    for filename, cmd in DETECTORS:
        if (folder / filename).exists():
            found.append((filename, cmd))
            break  # solo el primero (prioridad en orden)
    # Siempre revisar .env.example aparte
    return found

# ── Worker thread ─────────────────────────────────────────────────────────────
class InstallerWorker(QThread):
    sig_output   = pyqtSignal(str, str)   # (texto, tipo: ok/info/warn/err)
    sig_progress = pyqtSignal(int)
    sig_done     = pyqtSignal(bool, str)  # (exito, ruta_final)

    def __init__(self, url: str, dest: str, token: str = ""):
        super().__init__()
        self.url   = url
        self.dest  = dest
        self.token = token.strip()

    def run_cmd(self, cmd: list, cwd: Path) -> int:
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(cwd),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace"
            )
            for line in proc.stdout:
                l = line.rstrip()
                if l:
                    self.sig_output.emit(l, "info")
            proc.wait()
            return proc.returncode
        except FileNotFoundError:
            self.sig_output.emit(f"✗ Comando no encontrado: {cmd[0]}", "err")
            return -1

    @staticmethod
    def clean_url(url: str) -> str:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url.strip())
        clean = urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", "", ""))
        if not clean.endswith(".git"):
            clean += ".git"
        return clean

    def run(self):
        self.sig_progress.emit(5)
        self.url  = self.clean_url(self.url)
        dest      = Path(self.dest)
        repo_name = self.url.rstrip("/").split("/")[-1].replace(".git", "")
        clone_dest = dest / repo_name

        # Manejo carpeta existente
        if clone_dest.exists():
            self.sig_output.emit(f"⚠ '{clone_dest.name}' ya existe — sobreescribiendo...", "warn")
            try:
                shutil.rmtree(clone_dest)
            except Exception as e:
                self.sig_output.emit(f"✗ No se pudo eliminar: {e}", "err")
                self.sig_done.emit(False, "")
                return

        # Construir URL (con token si hay)
        url = self.url
        if self.token:
            from urllib.parse import urlparse
            p = urlparse(url)
            url = f"{p.scheme}://{self.token}@{p.netloc}{p.path}"

        # Git clone
        self.sig_output.emit(f"→ git clone {self.url}", "info")
        rc = self.run_cmd(["git", "clone", url, str(clone_dest)], dest)
        if rc != 0:
            self.sig_output.emit("✗ git clone falló — verifica la URL o el token PAT", "err")
            self.sig_done.emit(False, "")
            return

        self.sig_progress.emit(40)
        self.sig_output.emit("✓ Clone completado", "ok")

        # Copiar .env.example → .env
        env_src = clone_dest / ENV_EXAMPLE
        env_dst = clone_dest / ENV_TARGET
        if env_src.exists() and not env_dst.exists():
            shutil.copy(env_src, env_dst)
            self.sig_output.emit("⚠ .env.example copiado a .env — revisa tus variables de entorno", "warn")

        # Detectar e instalar dependencias
        installers = detect_installers(clone_dest)
        if not installers:
            self.sig_output.emit("ℹ No se detectó gestor de dependencias — listo.", "info")
            self.sig_progress.emit(100)
            self.sig_done.emit(True, str(clone_dest))
            return

        self.sig_progress.emit(50)
        for filename, cmd in installers:
            self.sig_output.emit(f"→ Detectado [{filename}] → ejecutando: {' '.join(cmd)}", "info")
            rc = self.run_cmd(cmd, clone_dest)
            if rc == 0:
                self.sig_output.emit(f"✓ Dependencias instaladas correctamente", "ok")
            else:
                self.sig_output.emit(f"✗ Error al instalar dependencias (código {rc})", "err")

        self.sig_progress.emit(100)
        self.sig_done.emit(True, str(clone_dest))

# ── Worker preview GitHub API ─────────────────────────────────────────────────
class GithubPreviewWorker(QThread):
    sig_result = pyqtSignal(dict)
    sig_error  = pyqtSignal(str)

    def __init__(self, owner: str, repo: str):
        super().__init__()
        self.owner = owner
        self.repo  = repo

    def _get(self, url: str) -> dict | None:
        try:
            req = Request(url, headers={"User-Agent": "GitDeploy/1.0", "Accept": "application/vnd.github+json"})
            with urlopen(req, timeout=8) as r:
                return json.loads(r.read().decode())
        except Exception:
            return None

    def run(self):
        base = f"https://api.github.com/repos/{self.owner}/{self.repo}"
        meta = self._get(base)
        if meta is None:
            self.sig_error.emit("Repo no encontrado o sin acceso")
            return
        if "message" in meta:
            self.sig_error.emit(meta["message"][:60])
            return

        # Archivos raíz para detectar instalador
        contents = self._get(f"{base}/contents") or []
        files = [item["name"] for item in contents if isinstance(item, dict)]
        meta["_files"] = files
        self.sig_result.emit(meta)


# ── Ventana principal ─────────────────────────────────────────────────────────
class GitDeployWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.history     = load_history()
        self.drag_pos    = QPoint()
        self.final_path  = ""
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        self.setWindowTitle("GitDeploy")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setMinimumWidth(440)
        self.resize(440, 460)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Barra de título ───────────────────────────────────────────────────
        bar = QWidget()
        bar.setFixedHeight(34)
        bar.setStyleSheet("background: #161b22; border-bottom: 1px solid #30363d;")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(12, 0, 10, 0)

        lbl_title = QLabel("⚡ GITDEPLOY")
        lbl_title.setStyleSheet("color: #8b949e; font-size: 10px; letter-spacing: 3px;")
        bar_lay.addWidget(lbl_title)
        bar_lay.addStretch()

        btn_min = QPushButton("−")
        btn_min.setFixedSize(22, 22)
        btn_min.setStyleSheet("QPushButton { background: #21262d; border: none; border-radius: 11px; color: #e3b341; font-size: 14px; }"
                              "QPushButton:hover { background: #e3b341; color: #000; }")
        btn_min.clicked.connect(self.showMinimized)

        btn_close = QPushButton("×")
        btn_close.setFixedSize(22, 22)
        btn_close.setStyleSheet("QPushButton { background: #21262d; border: none; border-radius: 11px; color: #f85149; font-size: 14px; }"
                                "QPushButton:hover { background: #f85149; color: #fff; }")
        btn_close.clicked.connect(self.close)

        bar_lay.addWidget(btn_min)
        bar_lay.addWidget(btn_close)
        root.addWidget(bar)

        # ── Cuerpo ────────────────────────────────────────────────────────────
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(14, 12, 14, 12)
        body_lay.setSpacing(8)

        # Repo URL
        lbl1 = QLabel("REPO URL")
        lbl1.setObjectName("lbl_section")
        body_lay.addWidget(lbl1)

        row_url = QHBoxLayout()
        self.combo_url = QComboBox()
        self.combo_url.setEditable(True)
        self.combo_url.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_url.lineEdit().setPlaceholderText("https://github.com/usuario/repo.git")
        for h in self.history:
            self.combo_url.addItem(h)
        row_url.addWidget(self.combo_url)

        btn_clear = QPushButton("✕")
        btn_clear.setFixedWidth(30)
        btn_clear.setToolTip("Limpiar")
        btn_clear.clicked.connect(lambda: self.combo_url.lineEdit().clear())
        row_url.addWidget(btn_clear)
        body_lay.addLayout(row_url)

        # Carpeta destino
        lbl2 = QLabel("CARPETA DESTINO")
        lbl2.setObjectName("lbl_section")
        body_lay.addWidget(lbl2)

        row_dest = QHBoxLayout()
        self.txt_dest = QLineEdit(DEFAULT_DEST)
        self.txt_dest.setStyleSheet("color: #3fb950;")
        row_dest.addWidget(self.txt_dest)

        btn_browse = QPushButton("📁 Elegir")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._browse)
        row_dest.addWidget(btn_browse)
        body_lay.addLayout(row_dest)

        # Token PAT (opcional)
        lbl3 = QLabel("GITHUB PAT (repo privado — opcional)")
        lbl3.setObjectName("lbl_section")
        body_lay.addWidget(lbl3)

        self.txt_token = QLineEdit()
        self.txt_token.setPlaceholderText("ghp_xxxxxxxxxxxxxxxxxxxx")
        self.txt_token.setEchoMode(QLineEdit.EchoMode.Password)
        body_lay.addWidget(self.txt_token)

        # Panel preview del repo
        self.frame_preview = QFrame()
        self.frame_preview.setStyleSheet(
            "QFrame { background: #0d1926; border: 1px solid #1f3d5a; border-radius: 6px; padding: 2px; }"
        )
        prev_lay = QVBoxLayout(self.frame_preview)
        prev_lay.setContentsMargins(10, 8, 10, 8)
        prev_lay.setSpacing(4)

        row_name = QHBoxLayout()
        self.lbl_repo_name = QLabel("ℹ Pega una URL para ver el repo")
        self.lbl_repo_name.setStyleSheet("color: #58a6ff; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        row_name.addWidget(self.lbl_repo_name)
        row_name.addStretch()
        self.lbl_stars = QLabel("")
        self.lbl_stars.setStyleSheet("color: #e3b341; font-size: 11px; background: transparent; border: none;")
        row_name.addWidget(self.lbl_stars)
        prev_lay.addLayout(row_name)

        self.lbl_desc = QLabel("")
        self.lbl_desc.setStyleSheet("color: #8b949e; font-size: 10px; background: transparent; border: none;")
        self.lbl_desc.setWordWrap(True)
        prev_lay.addWidget(self.lbl_desc)

        row_tags = QHBoxLayout()
        self.lbl_lang = QLabel("")
        self.lbl_lang.setStyleSheet(
            "color: #79c0ff; background: #1f3d5a; border-radius: 3px; padding: 1px 6px; font-size: 10px; border: none;"
        )
        self.lbl_installer = QLabel("")
        self.lbl_installer.setStyleSheet(
            "color: #56d364; background: #0f2d1a; border-radius: 3px; padding: 1px 6px; font-size: 10px; border: none;"
        )
        self.lbl_license = QLabel("")
        self.lbl_license.setStyleSheet(
            "color: #8b949e; background: #21262d; border-radius: 3px; padding: 1px 6px; font-size: 10px; border: none;"
        )
        row_tags.addWidget(self.lbl_lang)
        row_tags.addWidget(self.lbl_installer)
        row_tags.addWidget(self.lbl_license)
        row_tags.addStretch()
        prev_lay.addLayout(row_tags)

        body_lay.addWidget(self.frame_preview)

        # Timer debounce para no spamear la API
        self._preview_timer = QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._fetch_repo_info)

        # Log
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(110)
        body_lay.addWidget(self.log)

        # Progress
        self.progress = QProgressBar()
        self.progress.setValue(0)
        body_lay.addWidget(self.progress)

        # Botones acción
        row_btns = QHBoxLayout()
        self.btn_log = QPushButton("💾 Guardar log")
        self.btn_log.clicked.connect(self._save_log)
        row_btns.addWidget(self.btn_log)

        self.btn_install = QPushButton("⚡  INSTALAR")
        self.btn_install.setObjectName("btn_install")
        self.btn_install.clicked.connect(self._start_install)
        row_btns.addWidget(self.btn_install)

        self.btn_copy = QPushButton("📎 Copiar ruta")
        self.btn_copy.clicked.connect(self._copy_path)
        self.btn_copy.setEnabled(False)
        row_btns.addWidget(self.btn_copy)

        body_lay.addLayout(row_btns)
        root.addWidget(body)

        # Detectar al cambiar URL (debounce 600ms)
        self.combo_url.lineEdit().textChanged.connect(self._on_url_changed)

    def _apply_style(self):
        self.setStyleSheet(STYLE)

    # ── Arrastrar ventana ─────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton and not self.drag_pos.isNull():
            self.move(e.globalPosition().toPoint() - self.drag_pos)

    # ── Seleccionar carpeta ───────────────────────────────────────────────────
    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Selecciona carpeta destino", self.txt_dest.text())
        if folder:
            self.txt_dest.setText(folder)

    # ── Preview con API GitHub ────────────────────────────────────────────────
    def _on_url_changed(self, url: str):
        self._current_preview_url = url.strip()
        if not self._current_preview_url:
            self._reset_preview()
            return
        self.lbl_repo_name.setText("⏳ Consultando GitHub...")
        self.lbl_desc.setText("")
        self.lbl_stars.setText("")
        self.lbl_lang.setText("")
        self.lbl_installer.setText("")
        self.lbl_license.setText("")
        self._preview_timer.start(600)

    def _reset_preview(self):
        self.lbl_repo_name.setText("ℹ Pega una URL para ver el repo")
        self.lbl_desc.setText("")
        self.lbl_stars.setText("")
        self.lbl_lang.setText("")
        self.lbl_installer.setText("")
        self.lbl_license.setText("")

    def _parse_github_url(self, url: str):
        """Extrae owner/repo ignorando query params y fragments (e.g. fbclid)."""
        from urllib.parse import urlparse
        p = urlparse(url.strip())
        path = p.path.rstrip("/").replace(".git", "")
        parts = [x for x in path.split("/") if x]
        if len(parts) >= 2:
            return parts[0], parts[1]
        # fallback SSH
        m = re.search(r"github\.com[:/]([^/?#]+)/([^/?#\.]+)", url)
        if m:
            return m.group(1), m.group(2)
        return None, None

    def _fetch_repo_info(self):
        url = getattr(self, "_current_preview_url", "")
        owner, repo = self._parse_github_url(url)
        if not owner:
            self.lbl_repo_name.setText("⚠ URL no reconocida como GitHub")
            return
        self._api_worker = GithubPreviewWorker(owner, repo)
        self._api_worker.sig_result.connect(self._on_preview_result)
        self._api_worker.sig_error.connect(self._on_preview_error)
        self._api_worker.start()

    def _on_preview_result(self, data: dict):
        name  = data.get("name", "—")
        desc  = data.get("description") or "Sin descripción"
        stars = data.get("stargazers_count", 0)
        lang  = data.get("language") or ""
        lic   = (data.get("license") or {}).get("spdx_id", "")
        files = data.get("_files", [])

        self.lbl_repo_name.setText(f"  {name}")
        self.lbl_desc.setText(desc[:90] + ("…" if len(desc) > 90 else ""))
        self.lbl_stars.setText(f"★ {stars:,}" if stars else "")
        self.lbl_lang.setText(f" {lang}") if lang else self.lbl_lang.setText("")
        self.lbl_license.setText(f" {lic}") if lic else self.lbl_license.setText("")

        # Detectar instalador desde lista de archivos raíz
        installer_found = ""
        for filename, _ in DETECTORS:
            if filename in files:
                installer_found = filename
                break
        if installer_found:
            self.lbl_installer.setText(f" {installer_found}")
        else:
            self.lbl_installer.setText(" sin gestor detectado")
            self.lbl_installer.setStyleSheet(
                "color: #8b949e; background: #21262d; border-radius: 3px; padding: 1px 6px; font-size: 10px; border: none;"
            )

    def _on_preview_error(self, msg: str):
        self.lbl_repo_name.setText(f"⚠ {msg}")
        self.lbl_desc.setText("")

    # ── Iniciar instalación ───────────────────────────────────────────────────
    def _start_install(self):
        url   = self.combo_url.lineEdit().text().strip()
        dest  = self.txt_dest.text().strip()
        token = self.txt_token.text().strip()

        if not url:
            self._log("✗ Ingresa una URL de repo", "err")
            return
        if not dest or not Path(dest).exists():
            self._log("✗ Carpeta destino inválida o no existe", "err")
            return

        self.log.clear()
        self.progress.setValue(0)
        self.btn_install.setEnabled(False)
        self.btn_copy.setEnabled(False)
        self.final_path = ""
        self.history = save_history(url, self.history)

        self.worker = InstallerWorker(url, dest, token)
        self.worker.sig_output.connect(self._log)
        self.worker.sig_progress.connect(self.progress.setValue)
        self.worker.sig_done.connect(self._on_done)
        self.worker.start()

    def _on_done(self, ok: bool, path: str):
        self.btn_install.setEnabled(True)
        if ok:
            self.final_path = path
            self.btn_copy.setEnabled(True)
            self._log(f"✓ Instalación completa → {path}", "ok")
            self.lbl_detected.setText(f"✓ Proyecto listo en: {Path(path).name}")
        else:
            self._log("✗ La instalación falló — revisa el log", "err")

    def _log(self, text: str, tipo: str = "info"):
        colors = {"ok": "#3fb950", "warn": "#e3b341", "err": "#f85149", "info": "#8b949e"}
        color  = colors.get(tipo, "#8b949e")
        self.log.append(f'<span style="color:{color}">{text}</span>')

    def _copy_path(self):
        if self.final_path:
            QApplication.clipboard().setText(self.final_path)
            self.btn_copy.setText("✓ Copiado")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self.btn_copy.setText("📎 Copiar ruta"))

    def _save_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Guardar log", str(Path.home() / "gitdeploy_log.txt"), "Text (*.txt)")
        if path:
            Path(path).write_text(self.log.toPlainText(), encoding="utf-8")
            self._log(f"✓ Log guardado en {path}", "ok")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = GitDeployWindow()
    win.show()
    sys.exit(app.exec())
