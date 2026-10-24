# Public server: https://pillow.keanuc.net

The venue Wi-Fi isolates clients (MikroTik, client-to-client forwarding off; tested Fri 23:15:
laptop -> laptop gets ARP INCOMPLETE / "No route to host"), so ESP32s cannot reach a laptop
directly, and hotspots are banned. Instead the server sits behind a Cloudflare tunnel on Keanu's
account: devices and apps use **`https://pillow.keanuc.net`**, the tunnel forwards to the server on Keanu's VPS.
HTTPS only (plain HTTP redirects). 0.3-0.9 s round trip from the venue (the VPS is in Germany).

## Where it runs

The tunnel and the backend run on Keanu's VPS, in Docker, deployed from master by GitHub Actions:
see `deploy/README.md`. Changes reach the server only by PR -> master.

**Never run `cloudflared` for `calhacks-pillow` on a laptop.** Two runners split requests between
them, so half go to a stale or dead backend (Sat 24 Oct: 502s for half an hour). Develop against
your own `uvicorn` on localhost instead.

Check the tunnel has exactly one connector (the VPS, `linux_amd64`), from Keanu's laptop:
`cloudflared tunnel info calhacks-pillow`. A stray one: `cloudflared tunnel cleanup --connector-id <id>
calhacks-pillow` drops it, but it reconnects until its process is killed.

End-to-end check with a board on USB (stop the bridge first; posts as `test-pillow`):
`python3 sim/link_test.py --port /dev/ttyACM0`. It prints PASS/FAIL per hop (server, up, down)
and says which one broke. `--no-board` checks only the server hops.

Clients: firmware uses `SERVER_URL "https://pillow.keanuc.net"`; the simulator uses
`python3 sim/pillow_sim.py --post https://pillow.keanuc.net`.
