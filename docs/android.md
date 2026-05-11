# Android Setup

1. Open the Meshtastic Android app.
2. Add or connect a network device.
3. Set the host to the IP address of the Linux box running this bridge.
4. Set the port to `4403`, unless you changed `MESHTASTIC_TCP_PORT`.
5. Connect.

If the app hangs after Wi-Fi roaming, reconnecting should open a new TCP connection. The bridge will replace the previous stale client automatically.

Check logs with:

```bash
sudo journalctl -u meshtastic-tcp-bridge -f
```

Look for log lines similar to:

```text
Replacing stale TCP client old-address with new-address
```
