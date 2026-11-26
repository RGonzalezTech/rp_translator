# RP Translator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a desktop GUI tool that translates player messages into a WoW character's voice via LLM, with clipboard output and global hotkey summon.

**Architecture:** Single-file tkinter app (~300 lines) backed by SQLite for character storage and OpenRouter for LLM. Non-GUI layers (db, llm, settings) are tested with pytest; GUI layers verified manually.

**Tech Stack:** Python 3.x, tkinter, SQLite (stdlib) + pyperclip, pynput, requests (pip)

**Spec:** `docs/superpowers/specs/2025-11-25-rp-translator-design.md`

## Global Constraints

- Python 3.x stdlib for GUI (tkinter) and storage (sqlite3); no heavy GUI frameworks
- Single `rp_translator.py` file (~300 lines); `characters.db` and `settings.json` auto-created
- OpenRouter model: `deepseek/deepseek-v4-flash-0731`
- WoW tokens (%t, %f, %n) must pass through LLM untouched
- Two pip deps: pyperclip (clipboard), pynput (global hotkey), requests (HTTP)
- Windows-only — tkinter ships with Python on Windows; pynput works on Windows
- Voice examples are 2-3 before/after pairs stored as text; LLM can generate them on demand

## Review Focus

1. **No characters exist yet** — app opens with empty dropdown; Translate button disabled; show "No characters — create one first" placeholder → tested in Task 4
2. **OpenRouter API key missing** — translation shows "API key not found. Set OPENROUTER_API_KEY environment variable." in result area, does not crash → tested in Task 2 (unit) and Task 4 (integration)
3. **Network timeout during translation** — shows "Translation timed out. Try again." after 30s, does not hang → tested in Task 2 (mock timeout)
4. **Special characters in character fields** (quotes, newlines, %) — escaped properly in system prompt JSON, don't break the API call → tested in Task 2
5. **Global hotkey conflicts** — if registration fails (e.g. another app owns Ctrl+Shift+T), show warning in status bar, app still works via taskbar → tested in Task 5

---

### Task 1: Database Layer & Settings

**Files:**
- Create: `rp_translator.py` (db + settings sections)

**Interfaces:**
- Produces:
  - `init_db() -> sqlite3.Connection` — creates table, returns connection
  - `add_character(conn, name, race, class_, backstory, notes, voice_examples) -> int` — returns row id
  - `get_character(conn, id) -> dict | None`
  - `list_characters(conn) -> list[dict]` — returns id, name for dropdown
  - `update_character(conn, id, **fields) -> bool`
  - `delete_character(conn, id) -> bool`
  - `load_settings() -> dict` — loads `settings.json`, returns defaults if missing
  - `save_settings(settings: dict) -> None`

- [ ] **Step 1: Write failing tests for database CRUD**

```python
# test_rp_translator.py
import sqlite3
import pytest
from rp_translator import init_db, add_character, get_character, list_characters, delete_character

@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn

def test_add_and_get_character(conn):
    cid = add_character(conn, "Thrall", "Orc", "Shaman", "Warchief", "Speaks in proverbs", "gj -> Lok'tar!")
    char = get_character(conn, cid)
    assert char["name"] == "Thrall"
    assert char["race"] == "Orc"
    assert char["voice_examples"] == "gj -> Lok'tar!"

def test_list_characters_empty(conn):
    assert list_characters(conn) == []

def test_list_characters(conn):
    add_character(conn, "A", "Human", "Warrior", "", "", "")
    add_character(conn, "B", "Elf", "Mage", "", "", "")
    chars = list_characters(conn)
    assert len(chars) == 2

def test_update_character(conn):
    cid = add_character(conn, "Old", "Orc", "Rogue", "", "", "")
    from rp_translator import update_character
    update_character(conn, cid, name="New")
    assert get_character(conn, cid)["name"] == "New"

def test_delete_character(conn):
    cid = add_character(conn, "ToDelete", "Troll", "Priest", "", "", "")
    assert delete_character(conn, cid) is True
    assert get_character(conn, cid) is None

def test_settings_defaults():
    from rp_translator import load_settings
    import os
    # ensure no settings.json in cwd for this test
    settings = load_settings()
    assert "hotkey" in settings
    assert "always_on_top" in settings
    assert settings["always_on_top"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_rp_translator.py -v`
Expected: All 6 tests FAIL (module/function not found)

- [ ] **Step 3: Implement database and settings functions in `rp_translator.py`**

Database: `characters` table with columns `id INTEGER PRIMARY KEY, name TEXT, race TEXT, class TEXT, backstory TEXT, notes TEXT, voice_examples TEXT`. Use `init_db()` with `CREATE TABLE IF NOT EXISTS`. Each CRUD function takes a connection and returns/accepts the types listed in Interfaces.

Settings: `settings.json` in the script's directory. `load_settings()` returns `{"hotkey": "<ctrl>+<shift>+t", "always_on_top": False}` as defaults when the file doesn't exist. `save_settings()` writes JSON.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_rp_translator.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add rp_translator.py test_rp_translator.py
git commit -m "feat: add database layer and settings persistence"
```

---

### Task 2: LLM Client

**Files:**
- Modify: `rp_translator.py` (add llm section)

**Interfaces:**
- Consumes: (none from Task 1 — LLM client is independent)
- Produces:
  - `build_system_prompt(character: dict) -> str` — fills the template from spec
  - `call_llm(system_prompt: str, user_message: str, timeout: int = 30) -> str` — calls OpenRouter, returns response text
  - `generate_voice_examples(character: dict) -> str` — calls LLM to generate 2-3 example pairs from race/class/backstory

- [ ] **Step 1: Write failing tests for LLM client**

```python
def test_build_system_prompt():
    from rp_translator import build_system_prompt
    char = {"name": "Thrall", "race": "Orc", "class": "Shaman",
            "backstory": "Warchief", "notes": "Speaks wisdom",
            "voice_examples": "gj -> Lok'tar!"}
    prompt = build_system_prompt(char)
    assert "Thrall" in prompt
    assert "Orc" in prompt
    assert "Shaman" in prompt
    assert "Warchief" in prompt
    assert "Lok'tar" in prompt
    assert "%t" in prompt  # token instruction present

def test_build_system_prompt_special_chars():
    from rp_translator import build_system_prompt
    char = {"name": "D'rath", "race": "Night Elf", "class": "Druid",
            "backstory": 'Follower of "Elune"', "notes": "Loves %t",
            "voice_examples": "hi -> greetings"}
    prompt = build_system_prompt(char)
    assert "D'rath" in prompt
    assert 'Elune' in prompt

def test_call_llm_missing_key(monkeypatch):
    from rp_translator import call_llm
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = call_llm("system", "user message")
    assert "API key" in result.lower()

def test_generate_voice_examples_returns_string():
    from rp_translator import generate_voice_examples
    char = {"name": "Test", "race": "Human", "class": "Paladin",
            "backstory": "Knight of the Silver Hand", "notes": ""}
    # This test expects the function to exist and return a string (live call or mock)
    # In unit test context, we mock the HTTP call
    result = generate_voice_examples(char)
    assert isinstance(result, str)
    assert len(result) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_rp_translator.py -v -k "build_system_prompt or call_llm or generate_voice"`
Expected: Tests FAIL (functions not defined)

- [ ] **Step 3: Implement LLM client functions in `rp_translator.py`**

`build_system_prompt(character)`: fills the template from the spec doc, returns the full system prompt string.

`call_llm(system_prompt, user_message, timeout=30)`: POST to `https://openrouter.ai/api/v1/chat/completions` with `Authorization: Bearer $OPENROUTER_API_KEY`, model `deepseek/deepseek-v4-flash-0731`, messages `[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}]`. Use `requests.post` with timeout. On error (missing key, network, timeout, non-200), return an error string. On success, return `response.json()["choices"][0]["message"]["content"]`.

`generate_voice_examples(character)`: builds a prompt like "Generate 3 example message translations for a {race} {class} named {name}. Backstory: {backstory}. Format each as 'input -> output' on its own line." and calls `call_llm` with it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_rp_translator.py -v -k "build_system_prompt or call_llm or generate_voice"`
Expected: Tests PASS (mock the HTTP call for generate_voice_examples test)

- [ ] **Step 5: Commit**

```bash
git add rp_translator.py test_rp_translator.py
git commit -m "feat: add LLM client and voice example generator"
```

---

### Task 3: Character Dialog (GUI)

**Files:**
- Modify: `rp_translator.py` (add CharacterDialog class)

**Interfaces:**
- Consumes: `add_character`, `update_character`, `get_character`, `generate_voice_examples` from Tasks 1-2
- Produces: `CharacterDialog` — tkinter Toplevel, returns character dict on save, None on cancel
  - `CharacterDialog(parent, conn, character_id=None)` — None = create mode, id = edit mode

- [ ] **Step 1: Implement CharacterDialog class**

A `tkinter.Toplevel` dialog with:
- Entry fields: Name, Race, Class
- Text areas: Backstory (3 lines), Notes (3 lines), Voice Examples (5 lines)
- "Generate Examples" button (calls `generate_voice_examples`, fills Voice Examples field; grayed out while loading)
- Save / Cancel buttons
- Edit mode pre-fills fields from `get_character(conn, character_id)`
- Save calls `add_character` or `update_character` as appropriate

- [ ] **Step 2: Manual verification**

Run a stub mainloop: `python -c "import tkinter; from rp_translator import *; root=tkinter.Tk(); conn=init_db(...); CharacterDialog(root, conn)"` and verify:
- Dialog opens, all fields visible
- Generate Examples calls the LLM and fills the field
- Save adds character, dialog closes
- Edit mode pre-fills fields correctly

- [ ] **Step 3: Commit**

```bash
git add rp_translator.py
git commit -m "feat: add character create/edit dialog"
```

---

### Task 4: Main Window & Translation Flow

**Files:**
- Modify: `rp_translator.py` (add MainWindow class)

**Interfaces:**
- Consumes: `list_characters`, `get_character`, `delete_character`, `build_system_prompt`, `call_llm`, `CharacterDialog`
- Produces: `MainWindow(tkinter.Tk)` — the application root window

- [ ] **Step 1: Implement MainWindow class**

A `tkinter.Tk` window with:

**Top panel — Character:**
- Dropdown (`ttk.Combobox`) of character names, populated from `list_characters`
- New / Edit / Delete buttons
- On selection change: store character_id
- If no characters exist: dropdown disabled, "No characters" label, Translate disabled

**Middle panel — Translation:**
- Multi-line Text widget (2-3 lines tall, word wrap)
- Translate button (disabled when no character selected or empty input)
- Ctrl+Enter also triggers translate

**Bottom panel — Result:**
- Read-only Text widget (2-3 lines tall)
- Copy button (calls `pyperclip.copy`, flashes button text to "Copied!" briefly)
- On successful translate: auto-copy to clipboard

**Menu bar:**
- Settings → Always on Top (checkbutton, toggles `root.attributes('-topmost', ...)`)
- Settings → Configure Hotkey (opens a small dialog to capture key combo)

**Loading indicator:**
- During translation, Translate button text changes to "Translating..." and is disabled
- On completion/error, reverts to "Translate" and re-enables

**Settings integration:**
- On startup: load settings, apply always_on_top, start hotkey listener
- On toggle: save immediately to settings.json

**Error display:**
- LLM errors appear as red text in the result area instead of crashing

- [ ] **Step 2: Manual verification**

Run the app: `python rp_translator.py`
- Create a character via New button; appears in dropdown
- Select character, type "gj team", click Translate
- Loading indicator shows during API call
- Result appears in result area and is copied to clipboard
- Verify clipboard with Ctrl+V in notepad
- Edit character, change fields, verify translation changes
- Delete character, verify it disappears
- Toggle Always on Top, verify window stays above other windows
- No characters → app shows placeholder, Translate disabled

- [ ] **Step 3: Commit**

```bash
git add rp_translator.py
git commit -m "feat: add main window with translation flow"
```

---

### Task 5: Global Hotkey & Polish

**Files:**
- Modify: `rp_translator.py` (add hotkey listener, final wiring)
- Create: `requirements.txt`

**Interfaces:**
- Consumes: `MainWindow`, `load_settings`, `save_settings`
- Produces: `main()` entry point

- [ ] **Step 1: Implement global hotkey listener**

- Start a `pynput.keyboard.GlobalHotKeys` listener on app startup
- Default binding: `<ctrl>+<shift>+t` (parsed from settings)
- On hotkey press: `root.deiconify()`, `root.lift()`, `root.focus_force()`
- On window close (X button): `root.withdraw()` instead of destroying (minimize to background)
- System tray icon (optional, pynput-only approach: just hide on close, quit via File → Exit menu item)
- Settings → Configure Hotkey: capture next key combo, update settings, restart listener

- [ ] **Step 2: Write requirements.txt**

```
pyperclip>=1.8.0
pynput>=1.7.0
requests>=2.28.0
```

- [ ] **Step 3: Manual verification**

- Launch app, press Ctrl+Shift+T → window appears
- Close window (X) → window hides, process still running
- Press Ctrl+Shift+T again → window reappears with state intact
- File → Exit → process exits cleanly
- Change hotkey in Settings → Configure Hotkey → new binding works, old binding stops
- Hotkey conflict: if Ctrl+Shift+T is taken, app still opens normally from taskbar

- [ ] **Step 4: Final integration test**

Full walkthrough:
1. `pip install -r requirements.txt`
2. `set OPENROUTER_API_KEY=...` (or env var already set)
3. `python rp_translator.py`
4. Create 2 characters with different races/classes
5. Translate same message through each — verify different outputs
6. Verify %t and %f pass through untouched
7. Ctrl+Shift+T from another app, verify window focus
8. Close and reopen — verify characters and settings persist

- [ ] **Step 5: Commit**

```bash
git add rp_translator.py requirements.txt
git commit -m "feat: add global hotkey, settings, and final polish"
```
