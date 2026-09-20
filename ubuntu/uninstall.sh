#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# Desinstalador do Editor de Imagens Offline (Ubuntu/Linux)
# Remove o lancador, o atalho do menu e o icone instalados por install.sh.
#
# Uso:  bash ubuntu/uninstall.sh
# ----------------------------------------------------------------------------
set -euo pipefail

APP_ID="editor-de-imagens-offline"

LAUNCHER="${HOME}/.local/bin/editor-de-imagens"
ICON_DST="${HOME}/.local/share/icons/hicolor/256x256/apps/${APP_ID}.png"
DESKTOP_FILE="${HOME}/.local/share/applications/${APP_ID}.desktop"

removed=0
for f in "${LAUNCHER}" "${DESKTOP_FILE}" "${ICON_DST}"; do
  if [ -f "${f}" ]; then
    rm -f "${f}"
    printf '\033[1;32m OK \033[0m removido: %s\n' "${f}"
    removed=$((removed + 1))
  fi
done

command -v update-desktop-database >/dev/null 2>&1 \
  && update-desktop-database "${HOME}/.local/share/applications" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 \
  && gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true

if [ "${removed}" -eq 0 ]; then
  echo "Nada para remover (o aplicativo nao estava instalado)."
else
  echo
  echo "Desinstalacao concluida."
fi
