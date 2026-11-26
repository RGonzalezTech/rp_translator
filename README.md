# RP Translator

Desktop tool that rewrites your messages into your WoW character's voice. Pick your paladin, type "gj team," get "The Light protects us!" on your clipboard.

## Quick Start

```
pip install -r requirements.txt
set OPENROUTER_API_KEY=sk-or-...
python rp_translator.py
```

Press Ctrl+Shift+T from anywhere (even in-game), type, hit Translate, paste.

## Features

- **Character CRUD** — name, race, class, backstory, notes, voice examples
- **LLM translation** — OpenRouter + deepseek-v4-flash, dirt cheap (~37K translations per dollar)
- **Auto-generate voice examples** — one click fills example lines from race/class/backstory
- **Clipboard output** — result auto-copies, ready to paste in chat
- **WoW token passthrough** — `%t`, `%f`, `%n` ride through untouched
- **Global hotkey** — configurable (default Ctrl+Shift+T), summons from anywhere
- **Always-on-top toggle** — float over the game in windowed mode

## Voice Examples

The single biggest lever for getting good output. Fill in 2-3 before/after pairs:

```
gj team → The Light smiles upon us!
incoming → Steel yourselves, they come!
help %t → Elune guide you, %t.
```

The LLM matches that style. Hit "Generate Examples" to get a starter set.

## Files

```
rp_translator.py    — the whole app (single file)
characters.db       — SQLite, auto-created
settings.json       — hotkey + always-on-top prefs
```
