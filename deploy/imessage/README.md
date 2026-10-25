# iMessage sidecar

Photon's iMessage SDK (`spectrum-ts`) is TypeScript only, so the backend's notifications sender
(`backend/app/notify/`) calls this small Node service on the compose network instead:

    POST /send {"to": "+15551234567", "text": "..."}  ->  200 {"id": "<message id>"}
                                                          502 {"error": "..."}  (backend falls back to SMS)
                                                          503 {"error": "..."}  (not configured)
    GET /health                                       ->  200 once connected to Spectrum Cloud

Settings, from `/opt/pillow/backend.env`: `SPECTRUM_PROJECT_ID`, `SPECTRUM_PROJECT_SECRET`. On the
free tier every recipient must be added as a User in the Photon dashboard first.

Locally: `npm ci && SPECTRUM_PROJECT_ID=... SPECTRUM_PROJECT_SECRET=... node index.mjs`, then set
`IMESSAGE_URL=http://127.0.0.1:8787` for the backend. Inbound replies are only logged for now.
