#!/usr/bin/env python3
import logging
import os
import signal
import socket
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import serial

__version__ = "0.1.0"
DEFAULT_SERIAL_PORT = "/dev/ttyACM0"
DEFAULT_TCP_HOST = "0.0.0.0"
DEFAULT_TCP_PORT = 4403
DEFAULT_BAUD = 115200
DEFAULT_CLIENT_IDLE_TIMEOUT = 120
DEFAULT_LOG_LEVEL = "INFO"

READ_SIZE = 4096


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        logging.warning("Invalid integer for %s=%r, using %s", name, value, default)
        return default


@dataclass(frozen=True)
class Config:
    serial_port: str
    tcp_host: str
    tcp_port: int
    baud: int
    client_idle_timeout: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            serial_port=os.getenv("MESHTASTIC_SERIAL_PORT", DEFAULT_SERIAL_PORT),
            tcp_host=os.getenv("MESHTASTIC_TCP_HOST", DEFAULT_TCP_HOST),
            tcp_port=env_int("MESHTASTIC_TCP_PORT", DEFAULT_TCP_PORT),
            baud=env_int("MESHTASTIC_BAUD", DEFAULT_BAUD),
            client_idle_timeout=env_int(
                "MESHTASTIC_CLIENT_IDLE_TIMEOUT", DEFAULT_CLIENT_IDLE_TIMEOUT
            ),
            log_level=os.getenv("MESHTASTIC_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
        )


class CurrentClient:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sock: Optional[socket.socket] = None
        self._addr: Optional[Tuple[str, int]] = None
        self._last_seen = 0.0

    def set(self, sock: socket.socket, addr: Tuple[str, int]) -> None:
        with self._lock:
            old_sock = self._sock
            old_addr = self._addr
            self._sock = sock
            self._addr = addr
            self._last_seen = time.monotonic()

        if old_sock is not None:
            logging.info("Replacing stale TCP client %s with %s", format_addr(old_addr), format_addr(addr))
            close_socket(old_sock)
        logging.info("TCP client connected from %s", format_addr(addr))

    def clear(self, sock: socket.socket, reason: str) -> None:
        addr: Optional[Tuple[str, int]] = None
        cleared = False
        with self._lock:
            if self._sock is sock:
                addr = self._addr
                self._sock = None
                self._addr = None
                self._last_seen = 0.0
                cleared = True
        if cleared:
            logging.info("TCP client disconnected from %s: %s", format_addr(addr), reason)
        close_socket(sock)

    def touch(self, sock: socket.socket) -> None:
        with self._lock:
            if self._sock is sock:
                self._last_seen = time.monotonic()

    def get(self) -> Tuple[Optional[socket.socket], Optional[Tuple[str, int]], float]:
        with self._lock:
            return self._sock, self._addr, self._last_seen

    def close_if_idle(self, timeout: int) -> None:
        if timeout <= 0:
            return

        sock: Optional[socket.socket] = None
        addr: Optional[Tuple[str, int]] = None
        with self._lock:
            if self._sock is None:
                return
            idle_for = time.monotonic() - self._last_seen
            if idle_for < timeout:
                return
            sock = self._sock
            addr = self._addr
            self._sock = None
            self._addr = None
            self._last_seen = 0.0

        logging.info("Closing idle TCP client %s after %ss", format_addr(addr), timeout)
        close_socket(sock)


class SerialBridge:
    def __init__(self, config: Config, current_client: CurrentClient, stop_event: threading.Event) -> None:
        self.config = config
        self.current_client = current_client
        self.stop_event = stop_event
        self.serial: Optional[serial.Serial] = None

    def run(self) -> None:
        backoff = 1.0
        while not self.stop_event.is_set():
            try:
                self._open()
                backoff = 1.0
                self._read_loop()
            except Exception:
                logging.exception("Serial bridge error")
            finally:
                self._close()

            if self.stop_event.is_set():
                break

            logging.info("Reopening serial in %.1fs", backoff)
            self.stop_event.wait(backoff)
            backoff = min(backoff * 2, 30.0)

    def write(self, data: bytes) -> bool:
        ser = self.serial
        if ser is None or not ser.is_open:
            logging.warning("Dropping %s bytes from TCP because serial is not open", len(data))
            return False

        try:
            ser.write(data)
            return True
        except Exception:
            logging.exception("Serial write error")
            self._close()
            return False

    def _open(self) -> None:
        logging.info("Opening serial %s at %s baud", self.config.serial_port, self.config.baud)
        self.serial = serial.Serial(
            port=self.config.serial_port,
            baudrate=self.config.baud,
            timeout=1,
            write_timeout=1,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        logging.info("Serial opened: %s", self.config.serial_port)

    def _close(self) -> None:
        ser = self.serial
        self.serial = None
        if ser is None:
            return
        try:
            if ser.is_open:
                logging.info("Closing serial %s", self.config.serial_port)
                ser.close()
        except Exception:
            logging.exception("Serial close error")

    def _read_loop(self) -> None:
        assert self.serial is not None
        while not self.stop_event.is_set():
            data = self.serial.read(READ_SIZE)
            if not data:
                continue

            client, addr, _last_seen = self.current_client.get()
            if client is None:
                continue

            try:
                client.sendall(data)
            except Exception:
                logging.exception("TCP write error to %s", format_addr(addr))
                self.current_client.clear(client, "write error")


def format_addr(addr: Optional[Tuple[str, int]]) -> str:
    if addr is None:
        return "<unknown>"
    return f"{addr[0]}:{addr[1]}"


def close_socket(sock: Optional[socket.socket]) -> None:
    if sock is None:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def configure_keepalive(sock: socket.socket) -> None:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    for option_name, value in (
        ("TCP_KEEPIDLE", 15),
        ("TCP_KEEPINTVL", 5),
        ("TCP_KEEPCNT", 3),
    ):
        option = getattr(socket, option_name, None)
        if option is None:
            continue
        try:
            sock.setsockopt(socket.IPPROTO_TCP, option, value)
        except OSError:
            logging.debug("Unable to set %s=%s", option_name, value, exc_info=True)


def handle_client(
    sock: socket.socket,
    addr: Tuple[str, int],
    bridge: SerialBridge,
    current_client: CurrentClient,
    stop_event: threading.Event,
) -> None:
    configure_keepalive(sock)
    sock.settimeout(1.0)
    current_client.set(sock, addr)

    while not stop_event.is_set():
        active_sock, _active_addr, _last_seen = current_client.get()
        if active_sock is not sock:
            close_socket(sock)
            return

        try:
            data = sock.recv(READ_SIZE)
        except socket.timeout:
            continue
        except OSError:
            logging.warning("TCP read error from %s", format_addr(addr), exc_info=True)
            current_client.clear(sock, "read error")
            return

        if not data:
            current_client.clear(sock, "remote closed")
            return

        current_client.touch(sock)
        bridge.write(data)


def idle_monitor(current_client: CurrentClient, config: Config, stop_event: threading.Event) -> None:
    while not stop_event.wait(5):
        current_client.close_if_idle(config.client_idle_timeout)


def serve(config: Config, bridge: SerialBridge, current_client: CurrentClient, stop_event: threading.Event) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        configure_keepalive(server)
        server.bind((config.tcp_host, config.tcp_port))
        server.listen(16)
        server.settimeout(1.0)

        logging.info(
            "Meshtastic TCP bridge listening on %s:%s -> %s @ %s baud",
            config.tcp_host,
            config.tcp_port,
            config.serial_port,
            config.baud,
        )

        while not stop_event.is_set():
            try:
                client_sock, addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                if stop_event.is_set():
                    break
                raise

            thread = threading.Thread(
                target=handle_client,
                args=(client_sock, addr, bridge, current_client, stop_event),
                daemon=True,
            )
            thread.start()


def main() -> int:
    config = Config.from_env()
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.info(
        "Starting Meshtastic TCP bridge: serial_port=%s tcp_host=%s tcp_port=%s baud=%s idle_timeout=%s log_level=%s",
        config.serial_port,
        config.tcp_host,
        config.tcp_port,
        config.baud,
        config.client_idle_timeout,
        config.log_level,
    )
    stop_event = threading.Event()
    current_client = CurrentClient()
    bridge = SerialBridge(config, current_client, stop_event)

    def stop(_signum: int, _frame: object) -> None:
        logging.info("Stopping Meshtastic TCP bridge")
        stop_event.set()
        sock, _addr, _last_seen = current_client.get()
        close_socket(sock)
        bridge._close()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    serial_thread = threading.Thread(target=bridge.run, daemon=True)
    serial_thread.start()

    monitor_thread = threading.Thread(
        target=idle_monitor, args=(current_client, config, stop_event), daemon=True
    )
    monitor_thread.start()

    try:
        serve(config, bridge, current_client, stop_event)
    except Exception:
        logging.exception("Server error")
        return 1
    finally:
        stop_event.set()
        sock, _addr, _last_seen = current_client.get()
        close_socket(sock)
        bridge._close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
