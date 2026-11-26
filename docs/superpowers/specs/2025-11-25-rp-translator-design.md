# RP Translator — Design Doc

## Intent

An internal desktop tool that rewrites a player's messages into the voice of their
WoW: Forever roleplaying character. Player types "gj team", picks their paladin,
and gets "The Light protects us!" on their clipboard — ready to paste in-game.

## Goals

- CRUD for WoW characters: name, race, class, backstory, notes, voice examples
- Translate any short message through the selected character's voice via LLM
- Write the translated result directly to the system clipboard
- Pass WoW tokens (%t, %f, etc.) through untouched so the game expands them
- Global hotkey (configurable, default Ctrl+Shift+T) to summon the window from anywhere
- Always-on-top toggle (off by default) so it can float over the game when desired
- Loading indicator during translation (the LLM call is async, not instant)

## Non-goals

- In-game addon integration (this is a standalone desktop tool)
- Multi-player / shared character databases
- Message history or logging (v2)
- Token substitution (the tool never expands %t — WoW does that)

## Anti-goals

- Anything that injects into the WoW client process (ToS violation)
- A web service or server (local-only, single-user)

## Constraints

- Python 3.x + tkinter (ships with Python, zero extra GUI deps)
- SQLite for character storage (ships with Python)
- OpenRouter API + deepseek/deepseek-v4-flash-0731 for LLM
- `pyperclip` for clipboard (the one external dependency)
- `pynput` or `keyboard` for global hotkey (the second external dependency)
- Windows-only (WoW runs on Windows; cross-platform is not a goal)

## Approaches Considered

1. **tkinter desktop app** (chosen) — zero GUI deps, simple, fast to build
2. **PyQt/PySide** — slicker but 50MB+ dep for two text boxes, not worth it
3. **Web UI (Flask + browser)** — always-on-top and global hotkey are harder

## Design

Single-window tkinter app, ~300 lines. Two logical panels:

**Top: Character selector + management**
- Dropdown listing saved characters
- "New / Edit / Delete" buttons open a small dialog (name, race, class, backstory,
  notes, voice examples)
- All character fields feed into the LLM system prompt as character context
- Voice examples: 2-3 before/after pairs that show the LLM exactly how this
  character speaks (e.g. "gj team" → "The Light protects us!")
- "Generate Examples" button in the character dialog: calls the LLM once
  with race/class/backstory to auto-fill voice examples; user can edit before saving

**Bottom: Translation**
- Multi-line text input (2-3 lines tall)
- "Translate" button (also bound to Enter)
- Loading spinner or progress bar shown during API call
- Result displayed in a read-only text area
- "Copy" button (also auto-copies on successful translation)

**Behavior:**
- Global hotkey (configurable, default Ctrl+Shift+T) brings window to front (or creates it on first press)
- Always-on-top is a toggleable setting (menu or checkbox), off by default
- On translate: build system prompt from character fields, call OpenRouter,
  show spinner, display result, copy to clipboard
- WoW tokens (%t, %f, %n, etc.) are described in the system prompt as placeholders
  to preserve verbatim

**System prompt template (per translation):**
```
You are {name}, a {race} {class} in World of Warcraft.
Backstory: {backstory}
Notes: {notes}

Here are examples of how you speak:
{voice_examples}

Rewrite the following message in your character's voice. Preserve any
tokens starting with % (such as %t, %f, %n) exactly as they appear —
do not modify them.

Message: {user_input}
```

## Files

```
rp_translator/
  rp_translator.py    — main app (~300 lines)
  characters.db       — SQLite database (auto-created)
  requirements.txt    — pyperclip, pynput (or keyboard)
```

## What's Left to the Builder

- Exact tkinter widget layout and styling
- Global hotkey library choice (pynput vs keyboard — both work, pynput is more
  actively maintained)
- SQLite schema (one `characters` table, straightforward)
- Error handling for API failures (show error in the result area, don't crash)
- Loading indicator implementation (ttk.Progressbar indeterminate mode, or a
  simple "Translating..." label that toggles)
- Settings persistence (hotkey binding, always-on-top pref) — a simple JSON
  file in the app directory is sufficient
