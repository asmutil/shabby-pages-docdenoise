#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# Instalador do Editor de Imagens Offline para Ubuntu/Linux
#
# O que este script faz:
#   1. Verifica o Python 3 (>= 3.8)
#   2. Instala as dependencias que faltarem:
#        - Pillow        (via pip --user)
#        - python3-tk    (via apt, se houver sudo)
#   3. Instala o icone no tema hicolor do usuario
#   4. Cria o lancador em ~/.local/bin
#   5. Cria o atalho no menu de aplicativos ("Editor de Imagens (Offline)")
#
# Uso:  bash ubuntu/install.sh
# ----------------------------------------------------------------------------
set -euo pipefail

APP_ID="editor-de-imagens-offline"
APP_NAME="Editor de Imagens (Offline)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_FILE="${APP_DIR}/image_editor.py"

BIN_DIR="${HOME}/.local/bin"
LAUNCHER="${BIN_DIR}/editor-de-imagens"
ICON_SRC="${SCRIPT_DIR}/icon.png"
ICON_DIR="${HOME}/.local/share/icons/hicolor/256x256/apps"
ICON_DST="${ICON_DIR}/${APP_ID}.png"
DESKTOP_DIR="${HOME}/.local/share/applications"
DESKTOP_FILE="${DESKTOP_DIR}/${APP_ID}.desktop"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m OK \033[0m %s\n' "$*"; }
fail()  { printf '\033[1;31mERRO\033[0m %s\n' "$*" >&2; exit 1; }

info "Diretorio do aplicativo: ${APP_DIR}"

[ -f "${APP_FILE}" ] || fail "image_editor.py nao encontrado em ${APP_DIR}"

# ---------------------------------------------------------------- 1. Python 3
command -v python3 >/dev/null 2>&1 \
  || fail "Python 3 nao encontrado. Instale com: sudo apt install python3"

PYVER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
ok "Python ${PYVER} encontrado"

# ------------------------------------------------------- 2. Dependencias
# 2a. Pillow (pip --user; com fallback para PEP 668 do Ubuntu 23.04+)
if python3 -c 'import PIL' >/dev/null 2>&1; then
  ok "Pillow ja instalado ($(python3 -c 'import PIL; print(PIL.__version__)'))"
else
  info "Instalando Pillow (pip --user)..."
  python3 -m pip install --user pillow >/dev/null 2>&1 \
    || python3 -m pip install --user --break-system-packages pillow \
    || fail "Nao foi possivel instalar o Pillow automaticamente.
       Tente manualmente:  python3 -m pip install --user pillow"
  ok "Pillow instalado"
fi

# 2b. Tkinter (python3-tk via apt)
if python3 -c 'import tkinter' >/dev/null 2>&1; then
  ok "Tkinter ja instalado"
else
  info "Tkinter ausente - tentando instalar python3-tk via apt..."
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get update -qq || true
    sudo apt-get install -y python3-tk \
      || fail "Instale o Tkinter manualmente:  sudo apt install python3-tk"
    ok "python3-tk instalado"
  else
    fail "Sem sudo disponivel. Instale o Tkinter manualmente:
       sudo apt install python3-tk"
  fi
fi

# ------------------------------------------------------------- 3. Icone
[ -f "${ICON_SRC}" ] || python3 "${SCRIPT_DIR}/make_icon.py" \
  || fail "Nao foi possivel gerar o icone"
mkdir -p "${ICON_DIR}"
install -m 644 "${ICON_SRC}" "${ICON_DST}"
ok "Icone instalado em ${ICON_DST}"

# ---------------------------------------------------------- 4. Lancador
mkdir -p "${BIN_DIR}"
cat > "${LAUNCHER}" <<EOF
#!/usr/bin/env bash
# Gerado por ubuntu/install.sh - Editor de Imagens Offline
exec python3 "${APP_FILE}" "\$@"
EOF
chmod +x "${LAUNCHER}"
ok "Lancador criado em ${LAUNCHER}"

case ":${PATH}:" in
  *":${BIN_DIR}:"*) ;;
  *) info "AVISO: ${BIN_DIR} nao esta no seu PATH (o atalho do menu funciona mesmo assim)." ;;
esac

# --------------------------------------------------- 5. Atalho do menu
mkdir -p "${DESKTOP_DIR}"
cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=${APP_NAME}
GenericName=Editor de Imagens
Comment=Edite imagens localmente e offline (6000 px / 600 DPI)
Exec=${LAUNCHER}
Icon=${APP_ID}
Terminal=false
Categories=Graphics;RasterGraphics;2DGraphics;
Keywords=imagem;foto;editor;brilho;contraste;binarizar;dpi;offline;
StartupNotify=true
EOF
ok "Atalho criado em ${DESKTOP_FILE}"

# Atualiza caches (se os utilitarios existirem; nao sao obrigatorios)
command -v update-desktop-database >/dev/null 2>&1 \
  && update-desktop-database "${DESKTOP_DIR}" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 \
  && gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true

if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "${DESKTOP_FILE}" \
    && ok "Atalho validado (desktop-file-validate)" \
    || info "AVISO: o atalho foi criado, mas com advertencias de validacao."
fi

echo
ok "Instalacao concluida!"
echo "   - Abra pelo menu de aplicativos: ${APP_NAME}"
echo "   - Ou pelo terminal:              editor-de-imagens"
echo "   - Para remover:                  bash ${SCRIPT_DIR}/uninstall.sh"
