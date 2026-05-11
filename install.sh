#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="meshtastic-tcp-bridge"
SERVICE_FILE="${SERVICE_NAME}.service"
SERVICE_USER="meshtastic-tcp-bridge"
INSTALL_DIR="/opt/meshtastic-tcp-bridge"
ENV_FILE="/etc/meshtastic-tcp-bridge.env"
DEFAULT_TCP_HOST="0.0.0.0"
DEFAULT_TCP_PORT="4403"
DEFAULT_BAUD="115200"
DEFAULT_IDLE_TIMEOUT="120"
DEFAULT_LOG_LEVEL="INFO"

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SERIAL_PORT=""
TCP_HOST="$DEFAULT_TCP_HOST"
TCP_PORT="$DEFAULT_TCP_PORT"
BAUD="$DEFAULT_BAUD"
NO_START=0

usage() {
  cat <<USAGE
Usage: sudo ./install.sh [options]

Options:
  --serial-port PATH   Serial device path, for example /dev/serial/by-id/...
  --tcp-host HOST      TCP listen host (default: ${DEFAULT_TCP_HOST})
  --tcp-port PORT      TCP listen port (default: ${DEFAULT_TCP_PORT})
  --baud BAUD          Serial baud rate (default: ${DEFAULT_BAUD})
  --no-start           Install but do not enable/start the systemd service
  --help               Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial-port)
      SERIAL_PORT="${2:-}"
      shift 2
      ;;
    --tcp-host)
      TCP_HOST="${2:-}"
      shift 2
      ;;
    --tcp-port)
      TCP_PORT="${2:-}"
      shift 2
      ;;
    --baud)
      BAUD="${2:-}"
      shift 2
      ;;
    --no-start)
      NO_START=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "This installer needs root privileges. Run: sudo ./install.sh" >&2
    exit 1
  fi
}

install_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get install -y python3 python3-venv python3-pip coreutils util-linux
  else
    echo "apt-get was not found. Install python3, python3-venv, python3-pip, coreutils, and util-linux manually." >&2
  fi
}

collect_serial_devices() {
  shopt -s nullglob
  local devices=(
    /dev/serial/by-id/*
    /dev/ttyACM*
    /dev/ttyUSB*
  )
  shopt -u nullglob
  printf '%s\n' "${devices[@]}"
}

choose_serial_device() {
  if [[ -n "$SERIAL_PORT" ]]; then
    return
  fi

  mapfile -t devices < <(collect_serial_devices)

  if [[ "${#devices[@]}" -eq 0 ]]; then
    echo "No serial devices found under /dev/serial/by-id, /dev/ttyACM*, or /dev/ttyUSB*."
    echo "Plug in a Meshtastic USB serial device and rerun this installer, or edit ${ENV_FILE} manually after install."
    SERIAL_PORT="/dev/serial/by-id/your-meshtastic-device"
    return
  fi

  echo "Available serial devices:"
  local i
  for i in "${!devices[@]}"; do
    printf '  %s) %s\n' "$((i + 1))" "${devices[$i]}"
  done

  if [[ "${#devices[@]}" -eq 1 ]]; then
    read -r -p "Use ${devices[0]}? [Y/n] " answer
    case "${answer:-Y}" in
      y|Y|yes|YES)
        SERIAL_PORT="${devices[0]}"
        return
        ;;
    esac
  fi

  while [[ -z "$SERIAL_PORT" ]]; do
    read -r -p "Choose serial device number, or enter a full path: " answer
    if [[ "$answer" =~ ^[0-9]+$ ]] && (( answer >= 1 && answer <= ${#devices[@]} )); then
      SERIAL_PORT="${devices[$((answer - 1))]}"
    elif [[ -n "$answer" ]]; then
      SERIAL_PORT="$answer"
    fi
  done
}

install_files() {
  install -d -m 0755 "$INSTALL_DIR"
  install -m 0755 "$SOURCE_DIR/bridge.py" "$INSTALL_DIR/bridge.py"
  install -m 0644 "$SOURCE_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"
  if [[ -d "$SOURCE_DIR/docs" ]]; then
    install -d -m 0755 "$INSTALL_DIR/docs"
    cp -a "$SOURCE_DIR/docs/." "$INSTALL_DIR/docs/"
  fi
  python3 -m venv "$INSTALL_DIR/.venv"
  "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
  "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
}

create_service_user() {
  if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$INSTALL_DIR" --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  fi
  usermod -a -G dialout "$SERVICE_USER"
  chown -R "$SERVICE_USER:dialout" "$INSTALL_DIR"
}

write_env_file() {
  cat > "$ENV_FILE" <<ENV
MESHTASTIC_SERIAL_PORT=${SERIAL_PORT}
MESHTASTIC_TCP_HOST=${TCP_HOST}
MESHTASTIC_TCP_PORT=${TCP_PORT}
MESHTASTIC_BAUD=${BAUD}
MESHTASTIC_CLIENT_IDLE_TIMEOUT=${DEFAULT_IDLE_TIMEOUT}
MESHTASTIC_LOG_LEVEL=${DEFAULT_LOG_LEVEL}
ENV
  chmod 0644 "$ENV_FILE"
}

install_service() {
  local target="/etc/systemd/system/${SERVICE_FILE}"
  if [[ -f "$target" ]]; then
    cp "$target" "${target}.backup.$(date +%Y%m%d-%H%M%S)"
  fi
  install -m 0644 "$SOURCE_DIR/$SERVICE_FILE" "$target"
  systemctl daemon-reload
  if [[ "$NO_START" -eq 0 ]]; then
    systemctl enable --now "$SERVICE_NAME"
  else
    echo "Installed service but did not start it because --no-start was used."
  fi
}

print_final_instructions() {
  cat <<INFO

Installed ${SERVICE_NAME}.

Android Meshtastic app:
  TCP host: this Linux host IP
  TCP port: ${TCP_PORT}

Useful commands:
  sudo systemctl status ${SERVICE_NAME} --no-pager
  sudo journalctl -u ${SERVICE_NAME} -f
  sudo systemctl restart ${SERVICE_NAME}
  sudo nano ${ENV_FILE}

INFO
}

require_root
install_packages
choose_serial_device
install_files
create_service_user
write_env_file
install_service
print_final_instructions
