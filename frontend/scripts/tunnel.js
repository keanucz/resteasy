/**
 * Serve the app to Expo Go from anywhere. Opens two Cloudflare quick tunnels:
 *   - Metro, so Expo Go can load the app (EXPO_PACKAGER_PROXY_URL points the QR code and exp:// link at it)
 *   - the local backend, so the app on the phone can call the API (EXPO_PUBLIC_API_URL points at it)
 * If EXPO_PUBLIC_API_URL (shell or .env) is already a public URL, that backend is used and no
 * backend tunnel is opened.
 *
 * Run with `npm run tunnel` while the backend runs on BACKEND_PORT (default 8000).
 * Ctrl+C or closing the terminal stops Metro and both tunnels.
 * Needs `cloudflared` on PATH (winget install --id Cloudflare.cloudflared).
 */

const { spawn, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');

// Metro's default port; the next free one is used if it is taken (e.g. by a plain `npm start`).
const FIRST_METRO_PORT = 8081;
const PORT_SEARCH_LIMIT = 20;
const BACKEND_PORT = Number(process.env.BACKEND_PORT ?? 8000);
const ENV_FILE = path.join(__dirname, '..', '.env');
const API_URL_VAR = 'EXPO_PUBLIC_API_URL';
// Hosts only reachable from this computer (or its emulator), never from a phone.
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '0.0.0.0', '10.0.2.2']);
const TUNNEL_URL_PATTERN = /https:\/\/[a-z0-9-]+\.trycloudflare\.com/;
const TUNNEL_URL_TIMEOUT_MS = 60_000;
// New trycloudflare hostnames take a few seconds to reach DNS, so readiness is polled.
const READY_POLL_INTERVAL_MS = 2_000;
const READY_TIMEOUT_MS = 120_000;
const METRO_READY_BODY = 'packager-status:running';
const BACKEND_TEST_PATH = '/api/test';
const IS_WINDOWS = process.platform === 'win32';

const children = [];

/** Kill a child and everything it spawned (npx on Windows runs Metro in a grandchild). */
function killTree(child) {
  if (child.exitCode !== null || child.pid === undefined) return;
  if (IS_WINDOWS) {
    spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
  } else {
    child.kill('SIGTERM');
  }
}

/** Stop every child process and exit with `code`. */
function shutdown(code) {
  children.forEach(killTree);
  process.exit(code);
}

/** Resolve whether nothing is listening on `port`. */
function isPortFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => server.close(() => resolve(true)));
    server.listen(port);
  });
}

/** Resolve whether a server accepts connections on localhost:`port` (IPv4 or IPv6). */
function isListening(port) {
  return new Promise((resolve) => {
    const socket = net.connect({ port, host: 'localhost', autoSelectFamily: true });
    socket.once('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.once('error', () => resolve(false));
  });
}

/** Return the first free port from FIRST_METRO_PORT upwards. */
async function findMetroPort() {
  for (let port = FIRST_METRO_PORT; port < FIRST_METRO_PORT + PORT_SEARCH_LIMIT; port++) {
    if (await isPortFree(port)) return port;
  }
  throw new Error(`no free port between ${FIRST_METRO_PORT} and ${FIRST_METRO_PORT + PORT_SEARCH_LIMIT - 1}`);
}

/** Return EXPO_PUBLIC_API_URL from the shell, else from .env, else undefined. */
function configuredApiUrl() {
  if (process.env[API_URL_VAR]) return process.env[API_URL_VAR];
  if (!fs.existsSync(ENV_FILE)) return undefined;
  const line = fs
    .readFileSync(ENV_FILE, 'utf8')
    .split(/\r?\n/)
    .find((entry) => entry.trim().startsWith(`${API_URL_VAR}=`));
  return line?.split('=').slice(1).join('=').trim().replace(/^["']|["']$/g, '') || undefined;
}

/** Whether a phone on another network can reach `url`. */
function isPublicUrl(url) {
  try {
    return !LOCAL_HOSTS.has(new URL(url).hostname);
  } catch {
    return false;
  }
}

/** Start a cloudflared quick tunnel to `port` and resolve with the public https URL it prints. */
function startTunnel(port, label) {
  return new Promise((resolve, reject) => {
    const tunnel = spawn('cloudflared', ['tunnel', '--no-autoupdate', '--url', `http://localhost:${port}`], {
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    children.push(tunnel);

    const timer = setTimeout(() => reject(new Error(`cloudflared gave no ${label} URL within 60 s`)), TUNNEL_URL_TIMEOUT_MS);
    const onOutput = (chunk) => {
      const match = chunk.toString().match(TUNNEL_URL_PATTERN);
      if (match) {
        clearTimeout(timer);
        resolve(match[0]);
      }
    };
    tunnel.stdout.on('data', onOutput);
    tunnel.stderr.on('data', onOutput);
    tunnel.on('error', (error) => {
      clearTimeout(timer);
      reject(new Error(`could not run cloudflared (${error.message}). Install it: winget install --id Cloudflare.cloudflared`));
    });
    tunnel.on('exit', (code) => {
      console.error(`\ncloudflared (${label}) exited (code ${code}); the links no longer work.`);
      shutdown(1);
    });
  });
}

/** Use the configured public backend, or tunnel the local one; resolve with the API base URL. */
async function resolveApiUrl() {
  const configured = configuredApiUrl();
  if (configured && isPublicUrl(configured)) {
    console.log(`Backend: ${configured} (from ${API_URL_VAR})`);
    return configured;
  }
  // uvicorn binds IPv4 only, so a bind test on the IPv6 wildcard would miss it; connect instead.
  if (!(await isListening(BACKEND_PORT))) {
    console.warn(
      `Warning: nothing is listening on localhost:${BACKEND_PORT}. Start the backend:\n` +
        `  cd backend; uv run uvicorn app.main:app --reload --host 0.0.0.0 --port ${BACKEND_PORT}`,
    );
  }
  const backendUrl = await startTunnel(BACKEND_PORT, 'backend');
  console.log(`Backend tunnel: ${backendUrl} -> localhost:${BACKEND_PORT}`);
  return backendUrl;
}

/** Start Metro on `port` in this terminal, with its URLs and the API URL pointed at the tunnels. */
function startExpo(port, metroUrl, apiUrl) {
  // One command string: Windows needs a shell to run npx, and Node warns about args plus shell.
  const command = ['npx', 'expo', 'start', '--port', String(port), ...process.argv.slice(2)].join(' ');
  const expo = spawn(command, {
    stdio: 'inherit',
    shell: true,
    env: { ...process.env, EXPO_PACKAGER_PROXY_URL: metroUrl, [API_URL_VAR]: apiUrl },
  });
  children.push(expo);
  expo.on('exit', (code) => shutdown(code ?? 0));
}

/** Poll `url` until its body contains `expected` (or any 2xx when `expected` is omitted). */
async function waitFor(url, expected) {
  const deadline = Date.now() + READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      const body = await response.text();
      if (expected ? body.includes(expected) : response.ok) return body;
    } catch {
      // DNS for the new hostname is not live yet, or the server is still starting; keep polling.
    }
    await new Promise((resolve) => setTimeout(resolve, READY_POLL_INTERVAL_MS));
  }
  return undefined;
}

/** Print the Expo Go link once Metro answers, and whether the backend answers through its URL. */
async function announceWhenReady(metroUrl, apiUrl) {
  const expoGoUrl = `exp://${new URL(metroUrl).hostname}:443`;
  const [metroBody, backendBody] = await Promise.all([
    waitFor(`${metroUrl}/status`, METRO_READY_BODY),
    waitFor(`${apiUrl}${BACKEND_TEST_PATH}`),
  ]);
  console.log('');
  console.log(
    backendBody
      ? `  Backend OK: ${apiUrl}${BACKEND_TEST_PATH}`
      : `  Backend NOT reachable at ${apiUrl}${BACKEND_TEST_PATH}. Is uvicorn running on port ${BACKEND_PORT}?`,
  );
  if (!metroBody) console.error(`  Metro never answered at ${metroUrl}/status; try the link anyway.`);
  console.log(`  Expo Go link (any network): ${expoGoUrl}`);
  console.log('  Scan the QR code above with your camera (iOS) or Expo Go (Android), or paste the link into Expo Go.\n');
}

/** Open the tunnels, start Metro behind them, and announce the link. */
async function main() {
  process.on('SIGINT', () => shutdown(0));
  process.on('SIGTERM', () => shutdown(0));
  process.on('SIGHUP', () => shutdown(0));

  const port = await findMetroPort();
  console.log('Opening Cloudflare tunnels...');
  const [metroUrl, apiUrl] = await Promise.all([startTunnel(port, 'Metro'), resolveApiUrl()]);
  console.log(`Metro tunnel: ${metroUrl} -> localhost:${port}\n`);
  startExpo(port, metroUrl, apiUrl);
  announceWhenReady(metroUrl, apiUrl);
}

main().catch((error) => {
  console.error(error.message);
  shutdown(1);
});
