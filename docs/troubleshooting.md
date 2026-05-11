# Troubleshooting

## Check Service

```bash
sudo systemctl status meshtastic-tcp-bridge --no-pager
```

## Logs

```bash
sudo journalctl -u meshtastic-tcp-bridge -n 100 --no-pager
```

## Check Listening Port

```bash
ss -ltnp | grep 4403
```

## Check USB Device

```bash
lsusb
ls -l /dev/serial/by-id/
dmesg -T | egrep -i 'usb|ttyACM|ttyUSB|cdc_acm|cp210|ch340|disconnect|reset|error' | tail -120
```

## Permission Issues

Serial devices are usually owned by the `dialout` group. The service user must be in `dialout`:

```bash
id meshtastic-tcp-bridge
```

After changing group membership, restart the service. A reboot can also be useful on minimal distributions if device permissions were refreshed during boot.

## Serial Already Busy

Only one process can use the serial device at a time. Stop other tools that may be using it, including Meshtastic CLI sessions or a separate HTTP proxy.

```bash
sudo lsof /dev/ttyACM0
sudo lsof /dev/ttyUSB0
```

## Android Reconnect

Stale Android TCP clients should be replaced automatically. Check logs for:

```text
Replacing stale TCP client
```
