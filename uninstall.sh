#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="meshtastic-tcp-bridge"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
INSTALL_DIR="/opt/meshtastic-tcp-bridge"
ENV_FILE="/etc/meshtastic-tcp-bridge.env"

if [[ "${EUID}" -ne 0 ]]; then
  echo "This uninstaller needs root privileges. Run: sudo ./uninstall.sh" >&2
  exit 1
fi

removed=()

if systemctl list-unit-files "${SERVICE_NAME}.service" >/dev/null 2>&1; then
  systemctl disable --now "$SERVICE_NAME" || true
  removed+=("stopped and disabled ${SERVICE_NAME}.service")
fi

if [[ -f "$SERVICE_FILE" ]]; then
  rm -f "$SERVICE_FILE"
  removed+=("removed ${SERVICE_FILE}")
  systemctl daemon-reload
fi

if [[ -d "$INSTALL_DIR" ]]; then
  read -r -p "Remove ${INSTALL_DIR}? [y/N] " answer
  case "${answer:-N}" in
    y|Y|yes|YES)
      rm -rf "$INSTALL_DIR"
      removed+=("removed ${INSTALL_DIR}")
      ;;
    *)
      removed+=("kept ${INSTALL_DIR}")
      ;;
  esac
fi

if [[ -f "$ENV_FILE" ]]; then
  read -r -p "Remove ${ENV_FILE}? [y/N] " answer
  case "${answer:-N}" in
    y|Y|yes|YES)
      rm -f "$ENV_FILE"
      removed+=("removed ${ENV_FILE}")
      ;;
    *)
      removed+=("kept ${ENV_FILE}")
      ;;
  esac
fi

echo "Uninstall summary:"
if [[ "${#removed[@]}" -eq 0 ]]; then
  echo "  Nothing was removed."
else
  printf '  %s\n' "${removed[@]}"
fi
