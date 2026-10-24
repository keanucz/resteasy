# Frontend

Expo (SDK 58, to match Expo Go on iOS) + Expo Router + TypeScript.

## Goal: talk to the pillow

The app must **send signals to and receive signals from the pillow hardware**: show live sensor state
(head on pillow, motion, keys, light, temperature) and send commands (lights, vibration, breathing pulse,
presence glow) for setup, calibration and alerts.

The phone never talks to a board directly (boards are USB-bridged to a laptop, and the venue Wi-Fi
isolates devices). Everything goes through the backend, using the shapes in `coord/CONTRACT.md`:

```
phone app  <-- live state --  backend  <-- POST /api/pillows/{id}/state --  pillow
phone app  --  commands -->   backend  --> GET /api/pillows/{id}/commands --> pillow
```

## Run

```bash
cp .env.example .env   # set EXPO_PUBLIC_API_URL to the backend
npm install
npm start              # scan the QR code with Expo Go
```

`npm run typecheck`, `npm run lint`, `npm run doctor`.

Add packages with `npx expo install <pkg>`, not `npm install`, so versions match the SDK.

## Layout

```
src/
├── app/            routes only (Expo Router). Files here become screens; keep logic out.
│   ├── _layout.tsx root stack; signed-out users only see /login, signed-in users only see /
│   ├── login.tsx   "/login": email + password form
│   └── index.tsx   "/" — signed-in placeholder ("hi there!") confirming the login worked
├── hooks/          useSession — the live Supabase Auth session
├── components/     reusable UI (Screen container, AppText)
├── constants/      design tokens (colours, spacing, font sizes)
├── config/         env.ts — the only place that reads EXPO_PUBLIC_* vars
├── services/api/   client.ts — single fetch wrapper; add one file per backend resource
├── services/supabase/client.ts — the one Supabase client (publishable key, session in app storage)
└── services/auth.ts signIn / signOut; every failed login shows the same "Details incorrect"
```

Add `types/` under `src/` as you need it.

## Login

Supabase Auth with email + password; the form can also create an account. Any rejected login, whether the user is unknown or the
password is wrong, shows the same "Details incorrect", so the form never reveals which accounts exist.
Create logins from the backend: `cd backend; uv run python -m scripts.create_login <email> <contact_id>` (a plain name becomes
`<name>@pillow.test`, which is then what they type). Import with the `@/` alias (`@/components/Screen`).

## SDK 58 on a phone

The app is pinned to **Expo SDK 58** because that is what Expo Go on iOS runs. Expo Go only opens projects
built for its own SDK, so every phone needs the SDK 58 build of Expo Go.

- **iOS:** Expo Go from the App Store (SDK 58).
- **Android, physical phone:** Expo Go from the Play Store (58 is the latest SDK). If the store ever moves
  past 58, uninstall it, open https://expo.dev/go on the phone, pick SDK 58 + Android and install the APK.
- **Android emulator:** run `npm run android` (or press `a` in `npm start`). Expo installs the matching
  Expo Go on the emulator for you. Needs Android Studio with an emulator image.

## Cal Hacks Wi-Fi

The venue Wi-Fi blocks devices from talking to each other and hotspots are banned, so a phone cannot
reach this laptop by its `10.0.x.x` address. Run the backend, then the tunnel:

```powershell
cd backend; uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000   # terminal 1
cd frontend; npm run tunnel                                                      # terminal 2
```

`npm run tunnel` opens two Cloudflare quick tunnels (`https://<words>.trycloudflare.com`): one to Metro
so Expo Go can load the app, one to the backend on port 8000 so the app can call the API. It bakes the
backend tunnel into the app as `EXPO_PUBLIC_API_URL`, checks `GET /api/test` through it, and prints an
`exp://...trycloudflare.com:443` link plus the QR code. Ctrl+C or closing the terminal stops everything;
the links change every run.

- To use a backend that is already public instead (e.g. `https://pillow.keanuc.net` or the Pi), set
  `EXPO_PUBLIC_API_URL` to it in `.env`; then no backend tunnel is opened.
- Backend on another port: `$env:BACKEND_PORT = 8001; npm run tunnel`.
- Expo Go only opens a remote project when the Expo CLI and Expo Go are signed in to the same account
  (`npx expo login --no-browser`, or `$env:EXPO_TOKEN` from expo.dev access tokens).
- Needs `cloudflared` (`winget install --id Cloudflare.cloudflared`).
