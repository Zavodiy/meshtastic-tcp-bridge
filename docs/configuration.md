# Configuration

The service reads runtime settings from:

```text
/etc/meshtastic-tcp-bridge.env
```

Supported environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `MESHTASTIC_SERIAL_PORT` | `/dev/ttyACM0` | USB serial device path. Prefer `/dev/serial/by-id/...` when available. |
| `MESHTASTIC_TCP_HOST` | `0.0.0.0` | TCP listen address. |
| `MESHTASTIC_TCP_PORT` | `4403` | TCP listen port for the Android app. |
| `MESHTASTIC_BAUD` | `115200` | Serial baud rate. |
| `MESHTASTIC_CLIENT_IDLE_TIMEOUT` | `120` | Seconds before an idle TCP client is closed. Use `0` to disable idle timeout. |
| `MESHTASTIC_LOG_LEVEL` | `INFO` | Python logging level such as `DEBUG`, `INFO`, `WARNING`, or `ERROR`. |

After editing the file, restart the service:

```bash
sudo systemctl restart meshtastic-tcp-bridge
```

## Finding The Serial Device

Prefer stable by-id paths:

```bash
ls -l /dev/serial/by-id/
```

Fallback device names:

```bash
ls -l /dev/ttyACM* /dev/ttyUSB*
```

`/dev/serial/by-id/...` is preferred because `/dev/ttyACM0` or `/dev/ttyUSB0` can change when devices are unplugged, replugged, or boot order changes.
