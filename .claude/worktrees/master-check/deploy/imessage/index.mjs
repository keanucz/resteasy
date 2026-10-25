// iMessage sidecar: the backend's notification sender POSTs {to, text} here and this sends it as an
// iMessage through Photon's Spectrum Cloud (photon.codes). Only reachable on the compose network.
// Needs SPECTRUM_PROJECT_ID and SPECTRUM_PROJECT_SECRET; without them it answers 503, so the
// backend falls back to Twilio SMS. Recipients must be registered as Users in the Photon dashboard.
import http from "node:http";
import { Spectrum } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";

const PORT = Number(process.env.PORT ?? 8787);
const E164 = /^\+[1-9][0-9]{6,14}$/;
const MAX_BODY = 8 * 1024;

const configured = Boolean(process.env.SPECTRUM_PROJECT_ID && process.env.SPECTRUM_PROJECT_SECRET);
let app = null;
let startError = configured ? null : "SPECTRUM_PROJECT_ID / SPECTRUM_PROJECT_SECRET not set";

async function start() {
  if (!configured) return;
  try {
    app = await Spectrum({ providers: [imessage.config()] });
    console.log("imessage: connected to Spectrum Cloud");
    // Drain the inbound stream; replies are only logged for now (no content, no numbers)
    for await (const [, message] of app.messages) {
      console.log(`imessage: inbound ${message.content?.type ?? "message"} on ${message.platform}`);
    }
  } catch (err) {
    startError = `Spectrum start failed: ${err?.message ?? err}`;
    console.error(`imessage: ${startError}`);
    app = null;
  }
}

async function send(to, text) {
  const im = imessage(app);
  const user = await im.user(to);
  const space = await im.space.create(user);
  const sent = await space.send(text);
  return sent?.id ?? "sent";
}

function reply(res, code, body) {
  res.writeHead(code, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
      if (raw.length > MAX_BODY) reject(new Error("body too large"));
    });
    req.on("end", () => {
      try {
        resolve(JSON.parse(raw || "{}"));
      } catch {
        reject(new Error("body is not JSON"));
      }
    });
    req.on("error", reject);
  });
}

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    return reply(res, app ? 200 : 503, { ready: Boolean(app), error: startError });
  }
  if (req.method !== "POST" || req.url !== "/send") return reply(res, 404, { error: "not found" });
  if (!app) return reply(res, 503, { error: startError ?? "still connecting" });
  let body;
  try {
    body = await readJson(req);
  } catch (err) {
    return reply(res, 400, { error: err.message });
  }
  const { to, text } = body;
  if (typeof to !== "string" || !E164.test(to)) return reply(res, 400, { error: "to must be E.164" });
  if (typeof text !== "string" || !text.trim()) return reply(res, 400, { error: "text is empty" });
  try {
    return reply(res, 200, { id: await send(to, text) });
  } catch (err) {
    // e.g. "Target not allowed for this project": the number isn't a User in the Photon dashboard
    console.error(`imessage: send failed: ${err?.message ?? err}`);
    return reply(res, 502, { error: String(err?.message ?? err) });
  }
});

server.listen(PORT, () => console.log(`imessage: listening on :${PORT}`));
start();
process.on("SIGTERM", async () => {
  server.close();
  await app?.stop?.();
  process.exit(0);
});
