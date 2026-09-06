# Time Bank

**Give hours, not money.** A community time bank where people donate
skill-hours instead of cash: charity for those who can't give money.

Built for the [DEV Weekend Challenge: Generosity Edition](https://dev.to/challenges/weekend-2026-09-03).

- **Live demo:** https://timebank.jamilxt.com
- **Matching:** Google AI (Gemini) reads every open request, in any language, and returns reasoned cross-language matches
- **Voice:** ElevenLabs multilingual playback of all open requests, for low-vision and low-literacy members
- **UI:** English, Español, Français, বাংলা — one tap switches everything, including the voice-over script

## Quick start

```bash
# 1. get the code
git clone https://github.com/jamilxt/time-bank && cd time-bank

# 2. (optional) add keys for AI matching + voice; demo mode works without them
cp .env.example keys.env   # then edit keys.env

# 3. run — no dependencies, stdlib only
python3 server.py
# -> http://127.0.0.1:8791
```

No pip install. No build step. One Python file, one HTML file.

## How it works

1. Post what you need, in any language ("Help my daughter with math, 2h")
2. Offer what you can do in plain text; Gemini matches you to open needs with a reason
3. Pledge → fulfil; every exchange moves through a public hour ledger
4. "Listen to all requests" reads the board aloud in your language

Without API keys the app runs in demo mode: keyword-overlap matching and
browser speech synthesis, clearly labeled as such in the UI.

## Deploy (VPS + nginx)

```bash
sudo cp timebank.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now timebank
# nginx: proxy your server_name to 127.0.0.1:8791 (see README section below)
```

nginx server block:

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    location / {
        proxy_pass http://127.0.0.1:8791;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## API

| Method | Path | Body |
|---|---|---|
| GET | `/api/state` | — |
| POST | `/api/needs` | `{name, city, need, hours}` |
| POST | `/api/pledge` | `{member, need_id, hours}` |
| POST | `/api/fulfil` | `{pledge_id}` |
| POST | `/api/match` | `{offer}` |
| POST | `/api/speak` | `{text}` |

## License

MIT
