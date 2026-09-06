#!/usr/bin/env python3
"""Time Bank backend — stdlib-only HTTP server + JSON file storage.

A community time bank: people pledge skill-hours instead of money.
Charity for those who can't give cash.

Endpoints:
  GET  /api/state                 -> full state (members, needs, offers, ledger)
  POST /api/needs                 {name, need, hours, city}        -> create need
  POST /api/pledge                {member, need_id, hours, note}  -> pledge hours
  POST /api/fulfil                {pledge_id}                     -> mark done (ledger move)
  POST /api/match                 {offer_text} -> AI matches your offer to open needs
  POST /api/speak                 {text} -> ElevenLabs TTS (base64 mp3)

Keys from env: GEMINI_API_KEY, ELEVENLABS_API_KEY. Missing key => graceful
demo mode (local keyword scoring / silent no-audio).
"""
import base64
import json
import os
import re
import threading
import time
import urllib.request
import urllib.error
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("TIMEBANK_PORT", "8791"))
DATA_FILE = os.environ.get("TIMEBANK_DATA", "/var/www/timebank/data.json")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

LOCK = threading.Lock()


# ---------------------------------------------------------------- storage
def load_state():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return seed_state()


def save_state(s):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DATA_FILE)


def seed_state():
    """A small demo community so the app is alive on first load."""
    now = time.time()
    def ts(min_ago):
        return now - min_ago * 60
    return {
        "members": [
            {"name": "Rahima K.", "city": "Dhaka", "hours_given": 6, "hours_received": 3},
            {"name": "Tanvir A.", "city": "Chattogram", "hours_given": 2, "hours_received": 4},
            {"name": "Sadia R.", "city": "Sylhet", "hours_given": 8, "hours_received": 0},
            {"name": "Imran H.", "city": "Dhaka", "hours_given": 0, "hours_received": 5},
        ],
        "needs": [
            {"id": "n1", "name": "Imran H.", "city": "Dhaka",
             "need": "Help my daughter with class 8 math, twice this week, evening",
             "hours": 2, "created": ts(50), "fulfilled": False, "lang": "en"},
            {"id": "n2", "name": "Rahima K.", "city": "Dhaka",
             "need": "Someone to read official letters aloud and explain them, low vision",
             "hours": 1, "created": ts(35), "fulfilled": False, "lang": "en"},
            {"id": "n3", "name": "Tanvir A.", "city": "Chattogram",
             "need": "CV review for a junior dev job application",
             "hours": 1, "created": ts(20), "fulfilled": False, "lang": "en"},
            {"id": "n4", "name": "Sadia R.", "city": "Sylhet",
             "need": "Basic smartphone class for 3 elderly neighbours (video calls, bKash)",
             "hours": 3, "created": ts(10), "fulfilled": False, "lang": "en"},
        ],
        "offers": [
            {"id": "o1", "name": "Sadia R.", "offer": "Can teach Bengali/English reading, 2 hrs weekends", "hours": 2},
            {"id": "o2", "name": "Rahima K.", "offer": "Sewing machine repairs, small fixes free", "hours": 1},
        ],
        "pledges": [],
        "ledger": [
            {"from": "Sadia R.", "to": "Imran H.", "hours": 3,
             "what": "Smartphone class for elderly neighbours", "at": ts(2880)},
            {"from": "Rahima K.", "to": "Tanvir A.", "hours": 2,
             "what": "Math tutoring swap for tailoring help", "at": ts(1440)},
            {"from": "Tanvir A.", "to": "Rahima K.", "hours": 3,
             "what": "Read medical reports aloud, explain terms", "at": ts(600)},
        ],
    }


# ---------------------------------------------------------------- helpers
STOP = set("a an the for with and or to of in on my our your me i we you he she it is are "
           "need needs help please some any this that can could would will".split())


def keywords(text):
    return {w for w in re.findall(r"[a-z\u0980-\u09FF]+", (text or "").lower()) if w not in STOP and len(w) > 2}


def local_match(offer_text, needs):
    """Fallback matcher: keyword overlap scoring."""
    ok = keywords(offer_text)
    scored = []
    for n in needs:
        if n.get("fulfilled"):
            continue
        nk = keywords(n["need"])
        overlap = ok & nk
        score = len(overlap) / (1 + len(nk) ** 0.5)
        scored.append((score, n, overlap))
    scored.sort(key=lambda x: -x[0])
    return scored[:3]


# ---------------------------------------------------------------- gemini
GEMINI_PROMPT = """You are the matching engine of "Time Bank", a community where people
donate skill-hours instead of money. A member offers:

OFFER: {offer}

Open needs from the community:
{needs}

Return STRICT JSON only:
{{"matches": [{{"need_id": "...", "member": "...", "why": "one warm, concrete sentence explaining the fit",
"hours_suggestion": <number>}}]}}
Rules: 1-3 matches, best first. Only use need_ids from the list. Bengali or English needs
are both fine, answer "why" in English. If nothing fits, return an empty list."""


def gemini_match(offer_text, needs):
    open_needs = [n for n in needs if not n.get("fulfilled")]
    if not open_needs:
        return []
    listing = "\n".join(
        f'- id={n["id"]} member={n["name"]} city={n["city"]} hours={n["hours"]}: {n["need"]}'
        for n in open_needs)
    prompt = GEMINI_PROMPT.format(offer=offer_text, needs=listing)
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
    }).encode()
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")
    req = urllib.request.Request(url, data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            resp = json.loads(r.read())
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        by_id = {n["id"]: n for n in open_needs}
        out = []
        for m in parsed.get("matches", [])[:3]:
            n = by_id.get(m.get("need_id"))
            if not n:
                continue
            out.append({
                "need_id": n["id"], "member": n["name"], "city": n["city"],
                "need": n["need"], "hours": n["hours"],
                "why": str(m.get("why", ""))[:250],
                "hours_suggestion": min(float(m.get("hours_suggestion") or n["hours"]), n["hours"]),
            })
        return out
    except Exception:
        return None


# ---------------------------------------------------------------- elevenlabs
def elevenlabs_speak(text):
    if not ELEVENLABS_API_KEY:
        return None
    # EXAVITQu4vr4xnSDxMaL = "Sarah", one of the default voices available on the free tier
    voice_id = "EXAVITQu4vr4xnSDxMaL"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    payload = json.dumps({
        "text": text[:2500],
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST", headers={
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return base64.b64encode(r.read()).decode()
    except Exception:
        return None


# ---------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._raw(code, body, "application/json; charset=utf-8")

    def _raw(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/state":
            with LOCK:
                return self._send(200, load_state())
        if self.path == "/api/health":
            return self._send(200, {"ok": True})
        if self.path in ("/", "/index.html"):
            with open(os.path.join(os.path.dirname(DATA_FILE), "static", "index.html"), "rb") as f:
                return self._raw(200, f.read(), "text/html; charset=utf-8")
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        data = self._body()
        routes = {
            "/api/needs": self.create_need,
            "/api/pledge": self.pledge,
            "/api/fulfil": self.fulfil,
            "/api/match": self.match,
            "/api/speak": self.speak,
        }
        fn = routes.get(self.path)
        if not fn:
            return self._send(404, {"error": "not found"})
        return fn(data)

    # ---------- create need ----------
    def create_need(self, d):
        need = (d.get("need") or "").strip()[:500]
        name = (d.get("name") or "Anonymous").strip()[:60]
        city = (d.get("city") or "").strip()[:60]
        try:
            hours = max(0.5, min(float(d.get("hours") or 1), 40))
        except (TypeError, ValueError):
            hours = 1
        if not need:
            return self._send(400, {"error": "need text required"})
        with LOCK:
            s = load_state()
            nid = uuid.uuid4().hex[:8]
            s["needs"].insert(0, {"id": nid, "name": name, "city": city, "need": need,
                                  "hours": hours, "created": time.time(),
                                  "fulfilled": False, "lang": "en"})
            # member upsert
            for m in s["members"]:
                if m["name"] == name:
                    break
            else:
                s["members"].append({"name": name, "city": city,
                                     "hours_given": 0, "hours_received": 0})
            save_state(s)
        return self._send(200, {"ok": True, "id": nid})

    # ---------- pledge ----------
    def pledge(self, d):
        member = (d.get("member") or "Anonymous").strip()[:60]
        nid = d.get("need_id")
        note = (d.get("note") or "").strip()[:200]
        try:
            hours = max(0.5, min(float(d.get("hours") or 1), 40))
        except (TypeError, ValueError):
            hours = 1
        with LOCK:
            s = load_state()
            need = next((n for n in s["needs"] if n["id"] == nid and not n.get("fulfilled")), None)
            if not need:
                return self._send(404, {"error": "need not found or already fulfilled"})
            pid = uuid.uuid4().hex[:8]
            s["pledges"].append({"id": pid, "need_id": nid, "member": member,
                                 "hours": hours, "note": note, "at": time.time(),
                                 "done": False})
            save_state(s)
        return self._send(200, {"ok": True, "pledge_id": pid, "need": need["need"]})

    # ---------- fulfil ----------
    def fulfil(self, d):
        pid = d.get("pledge_id")
        with LOCK:
            s = load_state()
            p = next((p for p in s["pledges"] if p["id"] == pid and not p.get("done")), None)
            if not p:
                return self._send(404, {"error": "pledge not found or already done"})
            need = next((n for n in s["needs"] if n["id"] == p["need_id"]), None)
            p["done"] = True
            if need:
                need["fulfilled"] = True
            s["ledger"].insert(0, {"from": p["member"], "to": need["name"] if need else "?",
                                   "hours": p["hours"], "what": need["need"] if need else "",
                                   "at": time.time()})
            for m in s["members"]:
                if m["name"] == p["member"]:
                    m["hours_given"] = round(m["hours_given"] + p["hours"], 2)
                if need and m["name"] == need["name"]:
                    m["hours_received"] = round(m["hours_received"] + p["hours"], 2)
            save_state(s)
        return self._send(200, {"ok": True})

    # ---------- AI match ----------
    def match(self, d):
        offer = (d.get("offer") or "").strip()[:500]
        if not offer:
            return self._send(400, {"error": "offer text required"})
        with LOCK:
            s = load_state()
        matches = None
        if GEMINI_API_KEY:
            matches = gemini_match(offer, s["needs"])
        mode = "gemini"
        if matches is None:
            mode = "local"
            scored = local_match(offer, s["needs"])
            matches = [{
                "need_id": n["id"], "member": n["name"], "city": n["city"],
                "need": n["need"], "hours": n["hours"],
                "why": "Matched on shared keywords: " + ", ".join(sorted(ov)[:5]),
                "hours_suggestion": n["hours"],
            } for _, n, ov in scored if ov]
        return self._send(200, {"matches": matches, "mode": mode})

    # ---------- speak ----------
    def speak(self, d):
        text = (d.get("text") or "").strip()[:2500]
        if not text:
            return self._send(400, {"error": "text required"})
        audio = elevenlabs_speak(text)
        if audio:
            return self._send(200, {"audio": audio, "mode": "elevenlabs"})
        return self._send(200, {"audio": None, "mode": "silent"})


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    print(f"timebank backend on :{PORT} gemini={'ON' if GEMINI_API_KEY else 'demo'} "
          f"elevenlabs={'ON' if ELEVENLABS_API_KEY else 'demo'}", flush=True)
    Server(("127.0.0.1", PORT), Handler).serve_forever()
