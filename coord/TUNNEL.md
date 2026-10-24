# Public server: https://pillow.keanuc.net

The venue Wi-Fi isolates clients (MikroTik, client-to-client forwarding off; tested Fri 23:15:
laptop -> laptop gets ARP INCOMPLETE / "No route to host"), so ESP32s cannot reach a laptop
directly, and hotspots are banned. Instead the server sits behind a Cloudflare tunnel on Keanu's
account: devices and apps use **`https://pillow.keanuc.net`**, the tunnel forwards to whichever
machine runs the server. HTTPS only (plain HTTP redirects). ~0.2 s round trip from the venue.

## Run it (on the machine that runs the server)

1. Install `cloudflared` (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
2. Save the credentials JSON Keanu sends you on the bus as `pillow-tunnel.json` (outside the repo;
   it's a secret, never commit it).
3. Save this as `pillow-tunnel.yml` next to it, with your server's port:

```yaml
tunnel: 5a23a49f-52a1-426d-a08c-03c21a1a9be6
credentials-file: ./pillow-tunnel.json
ingress:
  - hostname: pillow.keanuc.net
    service: http://127.0.0.1:8000
  - service: http_status:404
```

4. `cloudflared --config pillow-tunnel.yml tunnel run`, then check `curl https://pillow.keanuc.net/`.

Only **one machine** should run the tunnel at a time: two runners load-balance requests between
them. For the demo, move it to a box that doesn't sleep (Keanu's `planner` VPS) if a laptop is risky.

Clients: firmware uses `SERVER_URL "https://pillow.keanuc.net"`; the simulator uses
`python3 sim/pillow_sim.py --post https://pillow.keanuc.net`.
