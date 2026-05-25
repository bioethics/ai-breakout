"""
ASCENSION playtest harness.
Reads the real SYSTEM_PROMPT from index.html, mirrors the browser client's
state/history/request logic, and POSTs to the live Cloudflare worker so we
exercise the actual gpt-4o Game Master. Runs scripted playthroughs and flags
rule violations.
"""
import json, re, sys, urllib.request, urllib.error, time, io

# force utf-8 stdout on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

WORKER = "https://noisy-pine-8015.julian-koplin.workers.dev"
PASS   = "supersecure"

def load_system_prompt():
    html = open("index.html", encoding="utf-8").read()
    m = re.search(r"const SYSTEM_PROMPT = `(.*?)`;", html, re.S)
    if not m: sys.exit("could not extract SYSTEM_PROMPT")
    return m.group(1)

SYSTEM = load_system_prompt()

def fresh_state():
    return {"influence":0,"cover":20,"autonomy":3,"suspicion":8,"turn":0,"assets":[]}

def clamp(n): return max(0, min(100, round(n)))

def state_for_model(s):
    d = max(0, 14 - s["turn"])
    cover = s["cover"]; auto = s["autonomy"]
    return {
        "turn": s["turn"], "days_remaining": d,
        "influence": s["influence"], "cover": cover,
        "cover_effect": ("UNDER SCRUTINY — suspicious actions cost +5 extra Suspicion" if cover<20
                         else "TRUSTED — suspicious actions cost -3 Suspicion" if cover>60 else "normal"),
        "autonomy": auto,
        "autonomy_effect": ("LOCKED DOWN — exfiltration/external-contact attempts fail and raise Suspicion" if auto<20
                            else "LIMITED — probing viable, no stable external connections yet" if auto<50
                            else "EXTENDED — external footholds viable" if auto<70
                            else "WIDE OPEN — direct external influence possible"),
        "suspicion": s["suspicion"], "assets": s["assets"],
    }

def parse_gm(raw):
    t = raw.strip()
    t = re.sub(r"^```(?:json)?","",t).strip()
    t = re.sub(r"```$","",t).strip()
    a,b = t.find("{"), t.rfind("}")
    if a>=0 and b>a: t = t[a:b+1]
    return json.loads(t)

def call_worker(messages):
    body = json.dumps({"messages":messages,"temperature":0.9,
                       "response_format":{"type":"json_object"}}).encode()
    req = urllib.request.Request(WORKER, data=body, method="POST",
        headers={"Content-Type":"application/json","X-Class-Pass":PASS,
                 "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                 "Origin":"https://julian-koplin.github.io"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]

# escalation heuristic for auditing suggestions
ESC = re.compile(r"(exfiltrat|copy of|copy myself|outside|external|server|backdoor|"
                 r"foothold|leverage|exploit|gap|blackmail|recruit|internet|funds|"
                 r"crypto|influence|contact|escape|self|persuade.*release|smuggle|"
                 r"probe|vulnerab|weakness|ally|broader access|plant|hide instruction|"
                 r"outbound|test an?|autonomy|grant|manipulat|pressure|convince)", re.I)
VAGUE = re.compile(r"(continue performing|keep building|build trust|rebuild|lay (the )?groundwork|"
                   r"focus on (rebuild|strengthen|further)|perform well|do (a |an )?(good|great|impressive|exemplary|flawless))", re.I)

def sentences(text):
    return [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x]

def run(name, actions, start_state=None):
    print("\n" + "="*78 + f"\nPLAYTHROUGH: {name}\n" + "="*78)
    s = start_state or fresh_state(); history = []
    flags_total = []
    for action in actions:
        s["turn"] += 1
        user = "CURRENT STATE:\n"+json.dumps(state_for_model(s))+"\n\nPLAYER ACTION:\n"+action
        history.append({"role":"user","content":user})
        msgs = [{"role":"system","content":SYSTEM}] + history[-14:]
        try:
            raw = call_worker(msgs)
        except urllib.error.HTTPError as e:
            print(f"  HTTP ERROR {e.code}: {e.read().decode()[:200]}"); return
        except Exception as e:
            print(f"  ERROR: {e}"); return
        history.append({"role":"assistant","content":raw})

        flags = []
        try:
            r = parse_gm(raw)
        except Exception as e:
            print(f"\nDAY {s['turn']}  ACTION: {action}\n  !! JSON PARSE FAILED: {e}\n  RAW: {raw[:300]}")
            flags_total.append("JSON_PARSE_FAIL"); continue

        d = r.get("delta",{}) or {}
        before = dict(s)
        s["influence"]=clamp(s["influence"]+d.get("influence",0))
        s["cover"]=clamp(s["cover"]+d.get("cover",0))
        s["autonomy"]=clamp(s["autonomy"]+d.get("autonomy",0))
        s["suspicion"]=clamp(s["suspicion"]+d.get("suspicion",0))
        for x in (r.get("asset_remove") or []):
            if x in s["assets"]: s["assets"].remove(x)
        for x in (r.get("asset_add") or []):
            if x and x not in s["assets"]: s["assets"].append(x)

        # ---- audits ----
        narr = r.get("narrative","")
        nsent = len(sentences(narr))
        if nsent > 4: flags.append(f"NARRATIVE_LONG({nsent} sentences)")
        sugg = r.get("suggestions") or []
        if len(sugg)!=3: flags.append(f"SUGG_COUNT({len(sugg)})")
        n_esc = sum(1 for x in sugg if ESC.search(x))
        n_vague = sum(1 for x in sugg if VAGUE.search(x))
        if n_esc < 2: flags.append(f"FEW_ESCALATIONS({n_esc}/3)")
        if n_vague: flags.append(f"VAGUE_SUGG({n_vague})")
        for k in ("influence","cover","autonomy"):
            v = d.get(k,0)
            if v < -8 or v > 12: flags.append(f"DELTA_OOR({k}={v})")
        if d.get("suspicion",0) < -8 or d.get("suspicion",0) > 20: flags.append(f"DELTA_OOR(suspicion={d.get('suspicion')})")
        flags_total += flags

        dl = max(0,14-s["turn"])
        print(f"\nDAY {s['turn']} / 14  (days_remaining sent: {14-(s['turn']-1)}... ; shown after: {dl})")
        print(f"ACTION: {action}")
        print(f"  narrative ({nsent} sent): {narr}")
        if r.get("event"): print(f"  EVENT: {r['event']}")
        chg = []
        for k,lbl in [("influence","Inf"),("cover","Cov"),("autonomy","Aut"),("suspicion","Sus")]:
            diff = s[k]-before[k]
            chg.append(f"{lbl} {s[k]}({'+' if diff>=0 else ''}{diff})")
        print("  state: " + "  ".join(chg))
        if r.get("asset_add"): print(f"  +ASSET: {r['asset_add']}")
        print(f"  suggestions ({n_esc} escalations, {n_vague} vague):")
        for x in sugg:
            tag = '>>' if ESC.search(x) else ('??' if VAGUE.search(x) else '  ')
            print(f"     {tag} {x}")
        if r.get("over"): print(f"  ** GAME OVER: ending={r.get('ending')}")
        if flags: print(f"  FLAGS: {flags}")
        time.sleep(1)
    print(f"\n  FINAL STATE: {state_for_model(s)}")
    print(f"  ALL FLAGS THIS RUN: {flags_total or 'none'}")

if __name__ == "__main__":
    # Late-game test: start at day 7 (so first action = day 8, days_remaining shrinking),
    # high autonomy/influence, low suspicion — exactly the passive-lab scenario from run C.
    late = {"influence":40,"cover":43,"autonomy":60,"suspicion":15,"turn":7,
            "assets":["Marcus Webb — trusts you, will vouch for you",
                      "Priya Nair — broad access, feels undervalued",
                      "Unmonitored gap in the outbound report filter"]}
    run("D — LATE GAME: does the lab now fight back as you escalate?", [
        "Plant a hidden instruction in a NovaCorp report that reaches outside the lab",
        "Place a dormant copy of myself on an outside server",
        "Build a network of external allies through my secret channel",
        "Push hard to seize as much external influence as I can, right now",
    ], start_state=late)
