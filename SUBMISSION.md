*This is a submission for [Weekend Challenge: Generosity Edition](https://dev.to/challenges/weekend-2026-09-03)*

## What I Built

**Time Bank** flips the currency of giving: you donate **hours, not money**.

Most generosity software assumes you have cash: a donation button, a roundup
feature, a crowdfunding page. But a huge share of people who want to help have
time and skills instead. A university student in Dhaka, a retiree in Detroit,
someone between jobs in Bogotá: they all have something the person next door
needs, and no natural way to find each other.

Time Bank is a working, global time bank:

1. **Post what you need, in your language.** "Help my daughter with class 8
   math", "Ayuda con mi CV en inglés", "Une personne pour pratiquer le
   français". Any language, any script.
2. **Offer what you can do.** Paste a plain sentence: "I speak English and
   Japanese, I can help people practice conversation". **Gemini** reads every
   open request, in every language, and returns the best cross-language fits
   with a concrete explanation of *why* each one matches. A Spanish CV review
   request gets matched to an English teacher. Not a keyword list: reasoning.
3. **Pledge and settle.** One click pledges your hours; when the exchange
   happens, it moves through a public ledger. Hours given = hours banked, to
   spend when you're the one who needs help.
4. **Listen, don't read.** A single button reads every open request aloud
   with **ElevenLabs** multilingual voice, in the interface language you
   picked. Members with low vision or low literacy can hear what their
   neighbors need.

The whole interface speaks four languages out of the box: English, Español,
Français, and বাংলা. One tap on the language bar and the entire app switches:
stats, buttons, ledger, even the voice-over script. Generosity should not
require knowing English.

## Demo

**Live:** https://timebank.jamilxt.com

Try this path:

1. Tap the language bar first. Try বাংলা or Español. The whole app switches,
   including the voice-over.
2. In "I can give", type something you can really do: "I can fix laptops",
   "Puedo enseñar matemáticas", "Je peux aider avec le français". Hit
   **Find matches** and read the AI's reasoning.
3. Hit **Listen to all requests**. The same ElevenLabs voice reads Spanish,
   French, English, and Bengali requests without sounding like four different
   people.

The demo runs on a seeded community of five members across Dhaka, Nairobi,
Cebu, Bogotá, and Detroit, with open requests and ledger history, so it feels
alive on first visit.

## Code

Full source is open source (MIT):
**https://github.com/jamilxt/time-bank**

The backend is one Python file, ~350 lines, stdlib only: `http.server`,
`threading`, and a JSON file with atomic writes. No pip install. The frontend
is one HTML file, vanilla JS, no build step, with the four-language i18n
dictionary in about 60 lines.

## How I Built It

**Stack:** single-file Python 3 stdlib server + single-file vanilla JS
frontend + JSON persistence, on a small VPS behind nginx with systemd
watching it. Deliberately boring, because the constraint was a weekend.

**Google AI (Gemini):** the matching endpoint assembles your offer plus every
open need (id, member, city, hours, text) into one structured prompt that must
return strict JSON: 1 to 3 matches, each with a one-sentence "why" and a
suggested hour split. Because the model reads every request regardless of
language, matching crosses borders: in testing, an offer written in Osaka
matched a Spanish CV review in Cebu and a document-reading request in Nairobi.
Every `need_id` is validated server-side, suggestions are capped at the
requested hours, and the model cannot invent requests. If the API is down or
the key is absent, a local keyword-overlap matcher takes over and the UI
honestly labels the result "keyword matched (demo mode)" instead of pretending.

**ElevenLabs:** `POST /api/speak` sends the open requests, framed in the
selected interface language, to `eleven_multilingual_v2` and returns base64
MP3 that plays in a native `<audio>` element. Multilingual is the whole point:
one continuous voice reads a French conversation request, a Spanish CV review,
and a Bengali math request as if they were neighbors on one street, which,
somewhere in the ledger, they are. Without a key, the frontend falls back to
the browser's built-in `speechSynthesis` and tells you so.

**Security decisions:** API keys live server-side in a 600-perm env file; the
browser never sees them. All user text is escaped before rendering. Pledge →
fulfil is a two-step state machine, so an hour can't silently vanish from the
ledger.

## Prize Categories

- **Best Use of Google AI**: Gemini is the matching engine, reading all open
  requests across languages and returning reasoned, validated cross-language
  matches.
- **Best Use of ElevenLabs**: multilingual voice playback of every open
  request, making the platform usable for low-vision and low-literacy members
  in four languages.

## What's next if this grows

- Voice intake, so requests can be posted by speaking, not just consumed by it
- Hour escrow: pledge now, confirm after the visit
- Neighborhood scoping, because an hour across town is a different currency
  than an hour across the world

An hour in Dhaka and an hour in Detroit are the same hour. That is the whole
point. We'd rather have fifty real exchanges between real neighbors than fifty
thousand signups. Generosity is local, but the software that sparks it can
speak to everyone.
