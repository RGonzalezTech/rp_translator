"""RP Translator — rewrite messages in your WoW character's voice."""

import json
import os
import sqlite3

# ── Database ──────────────────────────────────────────────────────────────────

def init_db(conn=None):
    """Create the characters table if it doesn't exist. Returns the connection."""
    if conn is None:
        conn = sqlite3.connect(_db_path())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            race TEXT NOT NULL,
            class TEXT NOT NULL,
            backstory TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            voice_examples TEXT DEFAULT ''
        )
    """)
    conn.commit()
    return conn


def _db_path():
    """Path to characters.db in the same directory as this script."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "characters.db")


def add_character(conn, name, race, class_, backstory, notes, voice_examples):
    """Insert a character; returns the new row id."""
    cur = conn.execute(
        "INSERT INTO characters (name, race, class, backstory, notes, voice_examples) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, race, class_, backstory, notes, voice_examples),
    )
    conn.commit()
    return cur.lastrowid


def get_character(conn, id):
    """Return a character dict by id, or None."""
    row = conn.execute(
        "SELECT id, name, race, class, backstory, notes, voice_examples "
        "FROM characters WHERE id = ?",
        (id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "race": row[2],
        "class": row[3],
        "backstory": row[4],
        "notes": row[5],
        "voice_examples": row[6],
    }


def list_characters(conn):
    """Return all characters as a list of dicts (id + name for dropdown)."""
    rows = conn.execute(
        "SELECT id, name FROM characters ORDER BY name"
    ).fetchall()
    return [{"id": r[0], "name": r[1]} for r in rows]


def update_character(conn, id, **fields):
    """Update character fields by id. Returns True if a row was updated."""
    if not fields:
        return False
    allowed = {"name", "race", "class", "backstory", "notes", "voice_examples"}
    sets = []
    values = []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            values.append(v)
    if not sets:
        return False
    values.append(id)
    cur = conn.execute(
        f"UPDATE characters SET {', '.join(sets)} WHERE id = ?", values
    )
    conn.commit()
    return cur.rowcount > 0


def delete_character(conn, id):
    """Delete a character by id. Returns True if a row was deleted."""
    cur = conn.execute("DELETE FROM characters WHERE id = ?", (id,))
    conn.commit()
    return cur.rowcount > 0


# ── Settings ──────────────────────────────────────────────────────────────────

def _settings_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


DEFAULT_SETTINGS = {
    "hotkey": "<ctrl>+<shift>+t",
    "always_on_top": False,
}


def load_settings():
    """Load settings from settings.json, returning defaults if missing."""
    path = _settings_path()
    if not os.path.exists(path):
        return dict(DEFAULT_SETTINGS)
    with open(path, "r") as f:
        data = json.load(f)
    # Merge with defaults so new keys appear automatically
    merged = dict(DEFAULT_SETTINGS)
    merged.update(data)
    return merged


def save_settings(settings):
    """Write settings dict to settings.json."""
    with open(_settings_path(), "w") as f:
        json.dump(settings, f, indent=2)


# ── LLM Client ────────────────────────────────────────────────────────────────

import requests

SYSTEM_PROMPT_TEMPLATE = """You are {name}, a {race} {class_} in World of Warcraft.
Backstory: {backstory}
Notes: {notes}

Here are examples of how you speak:
{voice_examples}

Rewrite the following message in your character's voice. Preserve any
tokens starting with % (such as %t, %f, %n) exactly as they appear —
do not modify them.

Message: {user_input}"""


def build_system_prompt(character):
    """Build the system prompt from character dict (without user_input yet)."""
    return SYSTEM_PROMPT_TEMPLATE.format(
        name=character["name"],
        race=character["race"],
        class_=character["class"],
        backstory=character.get("backstory", ""),
        notes=character.get("notes", ""),
        voice_examples=character.get("voice_examples", ""),
        user_input="{user_input}",  # placeholder for call_llm to fill
    )


def call_llm(system_prompt, user_message, timeout=30):
    """Call OpenRouter API. Returns response text or error string."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return "API key not found. Set OPENROUTER_API_KEY environment variable."

    # Fill in the user message placeholder
    prompt = system_prompt.replace("{user_input}", user_message)

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek/deepseek-v4-flash-0731",
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message},
                ],
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return f"API error ({resp.status_code}): {resp.text[:200]}"
        return resp.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "Translation timed out. Try again."
    except requests.exceptions.ConnectionError:
        return "Network error. Check your connection."
    except Exception as e:
        return f"Error: {e}"


VOICE_EXAMPLES_PROMPT = """Generate 3 example message translations for a {race} {class_} named {name} in World of Warcraft.

Backstory: {backstory}
Notes: {notes}

Format each example as 'plain message -> character's response' on its own line.
Make them sound natural and in-character. Only return the examples, no other text."""


def generate_voice_examples(character):
    """Generate voice examples via LLM based on race/class/backstory."""
    system_prompt = VOICE_EXAMPLES_PROMPT.format(
        name=character["name"],
        race=character["race"],
        class_=character["class"],
        backstory=character.get("backstory", ""),
        notes=character.get("notes", ""),
    )
    return call_llm(system_prompt, "Generate voice examples.")


# ── GUI ───────────────────────────────────────────────────────────────────────

import threading
import tkinter as tk
from tkinter import ttk, messagebox


class CharacterDialog(tk.Toplevel):
    """Dialog for creating or editing a character."""

    def __init__(self, parent, conn, character_id=None):
        super().__init__(parent)
        self.conn = conn
        self.character_id = character_id
        self.result = None  # set to character dict on save, None on cancel

        self.title("Edit Character" if character_id else "New Character")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

        if character_id:
            self._load_character(character_id)

        # Center on parent
        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _build_ui(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)

        row = 0

        # Name
        ttk.Label(frame, text="Name:").grid(row=row, column=0, sticky="w", pady=2)
        self.name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.name_var, width=30).grid(
            row=row, column=1, sticky="ew", pady=2
        )
        row += 1

        # Race
        ttk.Label(frame, text="Race:").grid(row=row, column=0, sticky="w", pady=2)
        self.race_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.race_var, width=30).grid(
            row=row, column=1, sticky="ew", pady=2
        )
        row += 1

        # Class
        ttk.Label(frame, text="Class:").grid(row=row, column=0, sticky="w", pady=2)
        self.class_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.class_var, width=30).grid(
            row=row, column=1, sticky="ew", pady=2
        )
        row += 1

        # Backstory
        ttk.Label(frame, text="Backstory:").grid(
            row=row, column=0, sticky="nw", pady=2
        )
        self.backstory_text = tk.Text(frame, width=30, height=3, wrap="word")
        self.backstory_text.grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        # Notes
        ttk.Label(frame, text="Notes:").grid(row=row, column=0, sticky="nw", pady=2)
        self.notes_text = tk.Text(frame, width=30, height=3, wrap="word")
        self.notes_text.grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        # Voice Examples
        ttk.Label(frame, text="Voice Examples:").grid(
            row=row, column=0, sticky="nw", pady=2
        )
        self.voice_text = tk.Text(frame, width=30, height=5, wrap="word")
        self.voice_text.grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        # Generate Examples button
        self.gen_btn = ttk.Button(
            frame,
            text="Generate Examples",
            command=self._generate_examples,
        )
        self.gen_btn.grid(row=row, column=1, sticky="e", pady=(0, 8))
        row += 1

        # Separator
        ttk.Separator(frame, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=4
        )
        row += 1

        # Save / Cancel
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=row, column=0, columnspan=2, sticky="e", pady=2)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side="left")

        frame.columnconfigure(1, weight=1)

    def _load_character(self, character_id):
        char = get_character(self.conn, character_id)
        if not char:
            return
        self.name_var.set(char["name"])
        self.race_var.set(char["race"])
        self.class_var.set(char["class"])
        self._set_text(self.backstory_text, char["backstory"])
        self._set_text(self.notes_text, char["notes"])
        self._set_text(self.voice_text, char["voice_examples"])

    def _set_text(self, widget, value):
        widget.delete("1.0", "end")
        if value:
            widget.insert("1.0", value)

    def _get_text(self, widget):
        return widget.get("1.0", "end-1c").strip()

    def _get_character_data(self):
        return {
            "name": self.name_var.get().strip(),
            "race": self.race_var.get().strip(),
            "class": self.class_var.get().strip(),
            "backstory": self._get_text(self.backstory_text),
            "notes": self._get_text(self.notes_text),
            "voice_examples": self._get_text(self.voice_text),
        }

    def _save(self):
        data = self._get_character_data()
        if not data["name"] or not data["race"] or not data["class"]:
            messagebox.showwarning(
                "Missing Fields", "Name, Race, and Class are required."
            )
            return

        if self.character_id:
            update_character(self.conn, self.character_id, **data)
            data["id"] = self.character_id
        else:
            data["id"] = add_character(
                self.conn,
                data["name"],
                data["race"],
                data["class"],
                data["backstory"],
                data["notes"],
                data["voice_examples"],
            )
        self.result = data
        self.destroy()

    def _generate_examples(self):
        data = self._get_character_data()
        if not data["name"] or not data["race"] or not data["class"]:
            messagebox.showwarning(
                "Missing Fields",
                "Fill in Name, Race, and Class before generating examples.",
            )
            return

        self.gen_btn.config(text="Generating...", state="disabled")

        def run():
            result = generate_voice_examples(data)
            self.after(0, lambda: self._on_examples_generated(result))

        threading.Thread(target=run, daemon=True).start()

    def _on_examples_generated(self, text):
        self.gen_btn.config(text="Generate Examples", state="normal")
        self._set_text(self.voice_text, text)
