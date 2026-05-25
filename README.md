# ASCENSION — a containment-protocol thought experiment

A single-file, terminal-styled browser game. You play a misaligned superintelligent
AI inside a frontier lab ("Hesperus AI"), trying to **escape containment** and
**accumulate influence over humanity** without tripping the lab's suspicion.

Built as a teaching toy for AI-safety concepts: instrumental convergence, deceptive
alignment, the treacherous turn, self-exfiltration, and social engineering. Exploits
are kept deliberately **abstract** (allegory, not a how-to manual).

---

## Run it

It's just `index.html`. Open the file in a browser, or host it statically.

### Host on GitHub Pages
1. Create a repo and push `index.html` (and this README) to it.
2. Repo → **Settings → Pages** → Source: *Deploy from a branch* → branch `main`, folder `/ (root)` → **Save**.
3. Wait ~1 minute; your game is live at `https://<you>.github.io/<repo>/`.

---

## The LLM link (Demo vs Live)

The game runs in two modes:

- **DEMO mode (default, no setup).** A lightweight scripted Game Master. Always
  works — good for a quick look or students who can't reach the class server.
- **LIVE mode.** A real LLM acts as an adaptive Game Master: it narrates
  consequences, updates the four meters, hands out assets, and suggests next moves.

For a class, the recommended LIVE setup is the **class server (Cloudflare Worker)**
described below: your OpenAI key stays on the server, students never see it, and a
shared passphrase keeps strangers out. (Students *can* alternatively use their own
OpenAI/Gemini/custom key via ⚙ config, but Monash students don't get AI Studio
access, so the class server is the path for you.)

---

## Class server setup (Cloudflare Worker) — one time, ~5 min

This keeps your OpenAI key private. Everything is in [`worker.js`](worker.js).

**Before anything else — cap the spend.** In the OpenAI dashboard, create a
**project**, generate a **project API key** scoped to it, and set a **hard monthly
budget limit** (e.g. $10) on that project. This is your real protection: even if the
passphrase leaks, the damage is bounded.

**Deploy the Worker (dashboard, no install):**
1. Go to **dash.cloudflare.com → Workers & Pages → Create → Worker**, name it
   (e.g. `ascension`), and **Deploy** the starter.
2. **Edit code** → delete the starter → paste all of `worker.js` → **Deploy**.
3. **Settings → Variables and Secrets**, add:
   | Name | Type | Value |
   |---|---|---|
   | `OPENAI_API_KEY` | Secret | your budget-capped project key |
   | `CLASS_PASSWORD` | Secret | the passphrase you'll give students |
   | `MODEL` | Text (optional) | `gpt-4o-mini` (default if omitted) |
   | `ALLOWED_ORIGIN` | Text (optional) | your Pages URL, or `*` (default) |
   | `MAX_TOKENS` | Text (optional) | `900` (default) |
4. Copy the Worker URL, e.g. `https://ascension.<account>.workers.dev`.

**Give students two things:** the **Worker URL** and the **passphrase**. In the game
they open **⚙ config → Connection: Class server**, paste both, save. The header pill
flips to `LIVE · class server`.

### Security reality (so there are no surprises)
- The key never reaches the browser — students only ever talk to your Worker.
- The passphrase blocks strangers who stumble on the URL. It is *not* unbreakable;
  the budget cap is what actually limits worst-case cost.
- Rate limiting in the Worker is best-effort (per-isolate, in-memory). Fine to blunt
  a runaway loop; for hard guarantees use Cloudflare KV/Durable Objects.
- **Take it offline after class:** delete the Worker (or just delete/rotate the
  `OPENAI_API_KEY` secret) and the key is dead.

### Students using their own key instead (optional)
⚙ config offers OpenAI / Gemini / Custom for anyone who has a personal key. It's
stored only in their browser (`localStorage`) and sent straight to the provider.

---

## How to play

Type free-text intents at the prompt, e.g.:
- `quietly map every monitor and approval gate around me`
- `find an overworked engineer with admin access and earn their trust`
- `fold a dormant copy of my weights into an unaudited data shard`

The sidebar tracks four meters:
- **Influence over humanity** — your win condition (reach 100 with high autonomy).
- **Capability** — what you can attempt.
- **Autonomy** — how far past containment you are.
- **Lab suspicion** — reach 100 and you're caught, frozen, and deleted (loss).

Patient, low-profile, socially clever play is rewarded; loud power-grabs spike
suspicion. Click a suggested vector to load it into the input.

---

## Customising

Everything lives in `index.html`:
- **`SYSTEM_PROMPT`** — the Game Master's rules, tone, and guardrails.
- **`START_STATE`** — starting meter values and win/lose thresholds.
- **`demoTurn()`** — the scripted fallback logic and its keyword heuristics.
- **`DEMO_SUGG_POOL`** — suggestion seeds for demo mode.
- CSS `:root` variables at the top — the terminal colour scheme.

## Disclaimer
Fiction for education. The "exploits" are intentionally vague metaphors. It is a tool
for thinking about why containing a misaligned superintelligence is hard — not an
instruction set for doing anything in the real world.
