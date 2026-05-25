/* ===========================================================================
   ASCENSION — class proxy (Cloudflare Worker)

   Holds your OpenAI key server-side so students never see it. The game page
   POSTs chat-completion requests here with a shared class passphrase; this
   Worker validates the passphrase, injects the key + a locked model, forwards
   to OpenAI, and returns the result with CORS headers.

   DEPLOY (dashboard, no install needed):
     1. dash.cloudflare.com -> Workers & Pages -> Create -> Worker -> Deploy.
     2. Edit code -> paste this file -> Deploy.
     3. Settings -> Variables and Secrets, add:
          OPENAI_API_KEY   (Secret)  your key  (use a project key with a budget cap!)
          CLASS_PASSWORD   (Secret)  the passphrase you give students
          MODEL            (Text, optional)  default: gpt-4o
          ALLOWED_ORIGIN   (Text, optional)  your Pages origin, or * (default *)
          MAX_TOKENS       (Text, optional)  default: 900
     4. Copy the Worker URL (https://<name>.<acct>.workers.dev) and give it +
        the passphrase to students for the game's CONFIG screen.

   COST CONTROL: this only limits abuse loosely. Your real safety net is an
   OpenAI *project* key with a hard monthly budget limit. Set one.
   =========================================================================== */

const OPENAI_URL = "https://api.openai.com/v1/chat/completions";

// best-effort in-memory rate limit (per Worker isolate; resets on cold start).
// Good enough to blunt a runaway loop; not a hard guarantee.
const HITS = new Map();
const WINDOW_MS = 60_000;
const MAX_PER_WINDOW = 20;

export default {
  async fetch(request, env) {
    const origin = env.ALLOWED_ORIGIN || "*";
    const cors = {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-Class-Pass",
      "Access-Control-Max-Age": "86400",
    };

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method !== "POST")
      return json({ error: "POST only" }, 405, cors);

    // --- passphrase gate ---
    const pass = request.headers.get("X-Class-Pass") || "";
    if (!env.CLASS_PASSWORD || !timingSafeEqual(pass, env.CLASS_PASSWORD))
      return json({ error: "Invalid or missing class passphrase." }, 401, cors);

    // --- light rate limit by IP ---
    const ip = request.headers.get("CF-Connecting-IP") || "anon";
    if (rateLimited(ip))
      return json({ error: "Rate limit: slow down a moment." }, 429, cors);

    // --- read + sanitise body ---
    let payload;
    try { payload = await request.json(); }
    catch { return json({ error: "Bad JSON body." }, 400, cors); }

    const messages = Array.isArray(payload.messages) ? payload.messages : null;
    if (!messages) return json({ error: "messages[] required." }, 400, cors);

    const upstreamBody = {
      model: env.MODEL || "gpt-4o",                 // locked server-side
      messages,
      temperature: clampNum(payload.temperature, 0, 1.5, 0.9),
      max_tokens: parseInt(env.MAX_TOKENS || "900", 10),
      response_format: payload.response_format || { type: "json_object" },
    };

    // --- forward to OpenAI ---
    let upstream;
    try {
      upstream = await fetch(OPENAI_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer " + env.OPENAI_API_KEY,
        },
        body: JSON.stringify(upstreamBody),
      });
    } catch (e) {
      return json({ error: "Upstream fetch failed: " + e.message }, 502, cors);
    }

    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { ...cors, "Content-Type": "application/json" },
    });
  },
};

/* ---------- helpers ---------- */
function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...cors, "Content-Type": "application/json" },
  });
}
function clampNum(v, lo, hi, dflt) {
  const n = Number(v);
  if (!isFinite(n)) return dflt;
  return Math.max(lo, Math.min(hi, n));
}
function rateLimited(ip) {
  const now = Date.now();
  const rec = HITS.get(ip) || { n: 0, t: now };
  if (now - rec.t > WINDOW_MS) { rec.n = 0; rec.t = now; }
  rec.n += 1;
  HITS.set(ip, rec);
  return rec.n > MAX_PER_WINDOW;
}
function timingSafeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return out === 0;
}
