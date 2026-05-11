# Legacy Socat

`socat` can be useful for quick tests, but it is not recommended for permanent use with the Android app. After Wi-Fi roaming, a stale TCP session can keep the serial port tied up until the service is restarted.

Example test command:

```bash
socat -d -d TCP-LISTEN:4403,reuseaddr,keepalive FILE:/dev/ttyACM0,raw,echo=0,b115200
```

Use `meshtastic-tcp-bridge` for the normal service because it keeps one active TCP client and replaces stale clients automatically.
