# ⚡ GetGit

Ventana flotante always-on-top para Windows que clona cualquier repo GitHub e instala todas sus dependencias automáticamente.

**Repo:** https://github.com/lotof1292-bit/GetGit

## Instalación rápida

```bash
pip install PyQt6
python gitdeploy.py
```

O simplemente descarga el `.exe` de [Releases](https://github.com/lotof1292-bit/GetGit/releases).

## Uso

1. Pega la URL del repo (funciona con links de redes sociales, fbclid y todo)
2. Selecciona la carpeta destino
3. Opcionalmente agrega un token PAT si el repo es privado
4. Clic en **⚡ INSTALAR**

## Ecosistemas soportados (detección automática)

| Archivo detectado   | Comando ejecutado                 |
|---------------------|-----------------------------------|
| `requirements.txt`  | `pip install -r requirements.txt` |
| `pyproject.toml`    | `pip install -e .`                |
| `setup.py`          | `pip install -e .`                |
| `package.json`      | `npm install`                     |
| `yarn.lock`         | `yarn install`                    |
| `pom.xml`           | `mvn install -q`                  |
| `Cargo.toml`        | `cargo build`                     |
| `go.mod`            | `go mod download`                 |
| `Makefile`          | `make install`                    |
| `install.sh`        | `bash install.sh`                 |
| `install.bat`       | `cmd /c install.bat`              |

Además copia automáticamente `.env.example` → `.env` si existe.

## Características

- Preview en vivo del repo (nombre, descripción, stars, lenguaje, licencia) vía GitHub API
- Limpia automáticamente URLs con fbclid y otros query params
- Historial de últimos 10 repos
- Always-on-top, frameless, arrastrable
- Log coloreado en tiempo real con opción de exportar
- Soporte repos privados vía token PAT
- Copia la ruta final al portapapeles con un click

## Futuras actualizaciones

- [ ] Selección de rama (branch)
- [ ] Soporte SSH keys
- [ ] Notificación Windows Toast al completar
- [ ] Ícono en system tray
- [ ] Auto-abrir carpeta en Explorer al terminar
- [ ] Integración con Nexus Shell como plugin Mod.GitDeploy
