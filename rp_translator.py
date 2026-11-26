"""RP Translator — rewrite messages in your WoW character's voice."""

import json
import os
import sqlite3

# ── Database ──────────────────────────────────────────────────────────────────

def init_db(conn=None):
    """Create tables if they don't exist. Migrates old voice_examples column. Returns the connection."""
    if conn is None:
        conn = sqlite3.connect(_db_path())
    conn.execute("PRAGMA foreign_keys = ON")
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS voice_examples (
            id INTEGER PRIMARY KEY,
            character_id INTEGER NOT NULL,
            before_text TEXT NOT NULL,
            after_text TEXT NOT NULL,
            FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    _migrate_voice_examples(conn)
    return conn


def _migrate_voice_examples(conn):
    """Migrate old voice_examples TEXT column to the new voice_examples table."""
    # Check if migration already ran (any rows in voice_examples table)
    already = conn.execute(
        "SELECT COUNT(*) FROM voice_examples"
    ).fetchone()[0]
    if already > 0:
        return

    # Also skip if old column doesn't exist
    cols = [r[1] for r in conn.execute("PRAGMA table_info(characters)").fetchall()]
    if "voice_examples" not in cols:
        return

    rows = conn.execute(
        "SELECT id, voice_examples FROM characters WHERE voice_examples != ''"
    ).fetchall()
    if not rows:
        return

    for char_id, text in rows:
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Split on first " -> "
            if " -> " in line:
                before, after = line.split(" -> ", 1)
                conn.execute(
                    "INSERT INTO voice_examples (character_id, before_text, after_text) VALUES (?, ?, ?)",
                    (char_id, before.strip(), after.strip()),
                )
    conn.commit()


def _db_path():
    """Path to characters.db in the same directory as this script."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "characters.db")


def add_character(conn, name, race, class_, backstory, notes):
    """Insert a character; returns the new row id."""
    cur = conn.execute(
        "INSERT INTO characters (name, race, class, backstory, notes) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, race, class_, backstory, notes),
    )
    conn.commit()
    return cur.lastrowid


def get_character(conn, id):
    """Return a character dict by id, or None."""
    row = conn.execute(
        "SELECT id, name, race, class, backstory, notes "
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
    allowed = {"name", "race", "class", "backstory", "notes"}
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


# ── Voice Examples CRUD ───────────────────────────────────────────────────────

def get_voice_examples(conn, character_id):
    """Return all voice examples for a character as a list of {id, before, after} dicts."""
    rows = conn.execute(
        "SELECT id, before_text, after_text FROM voice_examples "
        "WHERE character_id = ? ORDER BY id",
        (character_id,),
    ).fetchall()
    return [{"id": r[0], "before": r[1], "after": r[2]} for r in rows]


def add_voice_example(conn, character_id, before, after):
    """Add a voice example row. Returns the new row id."""
    cur = conn.execute(
        "INSERT INTO voice_examples (character_id, before_text, after_text) "
        "VALUES (?, ?, ?)",
        (character_id, before.strip(), after.strip()),
    )
    conn.commit()
    return cur.lastrowid


def update_voice_example(conn, example_id, before, after):
    """Update a voice example by id. Returns True if updated."""
    cur = conn.execute(
        "UPDATE voice_examples SET before_text = ?, after_text = ? WHERE id = ?",
        (before.strip(), after.strip(), example_id),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_voice_example(conn, example_id):
    """Delete a single voice example by id. Returns True if deleted."""
    cur = conn.execute("DELETE FROM voice_examples WHERE id = ?", (example_id,))
    conn.commit()
    return cur.rowcount > 0


def clear_voice_examples(conn, character_id):
    """Delete all voice examples for a character. Returns count deleted."""
    cur = conn.execute(
        "DELETE FROM voice_examples WHERE character_id = ?", (character_id,)
    )
    conn.commit()
    return cur.rowcount


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

SYSTEM_PROMPT_TEMPLATE = """{name}, a {race} {class_}.
Backstory: {backstory}
Notes: {notes}

You talk like this:
{voice_examples}

Say the next message your way. Do not change the facts -- who, what,
where, all of it. Just change how it is said. Keep it short,
like real WoW chat. Game codes (%t, %f, %n) pass through unchanged."""


def build_system_prompt(character, voice_examples=None):
    """Build the system prompt from character dict and optional voice examples list."""
    if voice_examples is None:
        voice_examples = []
    lines = []
    for ex in voice_examples:
        lines.append(f"{ex['before']} -> {ex['after']}")
    examples_text = "\n".join(lines) if lines else ""
    return SYSTEM_PROMPT_TEMPLATE.format(
        name=character["name"],
        race=character["race"],
        class_=character["class"],
        backstory=character.get("backstory", ""),
        notes=character.get("notes", ""),
        voice_examples=examples_text,
    )


def call_llm(system_prompt, user_message, timeout=30):
    """Call OpenRouter API. Returns response text or error string."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return "API key not found. Set OPENROUTER_API_KEY environment variable."

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek/deepseek-v3.2",
                "messages": [
                    {"role": "system", "content": system_prompt},
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


VOICE_EXAMPLES_PROMPT = """{name} is a {race} {class_} in WoW.
Backstory: {backstory}
Notes: {notes}

Write 3 short chat messages and how {name} would say them instead.
Reply with just a JSON array of "before" and "after" pairs. Example:
[
  {{"before": "gj team", "after": "The Light protects us!"}},
  {{"before": "incoming", "after": "They approach from the east!"}},
  {{"before": "thanks", "after": "My gratitude, friend."}}
]"""


def generate_voice_examples(character):
    """Generate voice examples via LLM. Returns a list of {{before, after}} dicts."""
    system_prompt = VOICE_EXAMPLES_PROMPT.format(
        name=character["name"],
        race=character["race"],
        class_=character["class"],
        backstory=character.get("backstory", ""),
        notes=character.get("notes", ""),
    )
    result = call_llm(system_prompt, "Generate voice examples.")
    try:
        # Try to extract JSON from the response (may be wrapped in markdown fences)
        text = result.strip()
        if text.startswith("```"):
            # Strip markdown code fences
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        examples = json.loads(text)
        if isinstance(examples, list):
            return examples
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: parse as text lines
    examples = []
    for line in result.strip().split("\n"):
        line = line.strip()
        if " -> " in line:
            before, after = line.split(" -> ", 1)
            examples.append({"before": before.strip(), "after": after.strip()})
    return examples


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

        # Voice Examples — table header
        ttk.Label(frame, text="Voice Examples:").grid(
            row=row, column=0, sticky="nw", pady=2
        )
        # Container for the example rows
        examples_container = ttk.Frame(frame)
        examples_container.grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        # Header row: "Before" / "After"
        header_frame = ttk.Frame(examples_container)
        header_frame.pack(fill="x")
        ttk.Label(header_frame, text="Before", width=14, anchor="center").pack(
            side="left", padx=(0, 2)
        )
        ttk.Label(header_frame, text="After", width=14, anchor="center").pack(
            side="left", padx=(2, 0)
        )

        # Scrollable frame for example rows
        self._example_rows = []
        self._examples_frame = ttk.Frame(examples_container)
        self._examples_frame.pack(fill="x", pady=(2, 0))

        # Buttons row
        btn_row_frame = ttk.Frame(frame)
        btn_row_frame.grid(row=row, column=1, sticky="e", pady=(0, 8))
        row += 1

        ttk.Button(
            btn_row_frame, text="+", width=3, command=self._add_example_row
        ).pack(side="left", padx=2)

        self.gen_btn = ttk.Button(
            btn_row_frame,
            text="Generate Examples",
            command=self._generate_examples,
        )
        self.gen_btn.pack(side="left", padx=2)

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

    def _add_example_row(self, before="", after=""):
        """Add one before/after row to the examples table."""
        row_frame = ttk.Frame(self._examples_frame)
        row_frame.pack(fill="x", pady=1)

        before_var = tk.StringVar(value=before)
        after_var = tk.StringVar(value=after)

        before_entry = ttk.Entry(row_frame, textvariable=before_var, width=15)
        before_entry.pack(side="left", padx=(0, 2))

        ttk.Label(row_frame, text="→").pack(side="left", padx=2)

        after_entry = ttk.Entry(row_frame, textvariable=after_var, width=15)
        after_entry.pack(side="left", padx=(2, 2))

        del_btn = ttk.Button(
            row_frame, text="×", width=2,
            command=lambda: self._remove_example_row(row_frame),
        )
        del_btn.pack(side="left", padx=2)

        self._example_rows.append({
            "frame": row_frame,
            "before": before_var,
            "after": after_var,
        })

    def _remove_example_row(self, row_frame):
        """Remove a row from the examples table."""
        self._example_rows = [
            r for r in self._example_rows if r["frame"] is not row_frame
        ]
        row_frame.destroy()

    def _load_character(self, character_id):
        char = get_character(self.conn, character_id)
        if not char:
            return
        self.name_var.set(char["name"])
        self.race_var.set(char["race"])
        self.class_var.set(char["class"])
        self._set_text(self.backstory_text, char["backstory"])
        self._set_text(self.notes_text, char["notes"])
        # Load voice examples from the new table
        examples = get_voice_examples(self.conn, character_id)
        for ex in examples:
            self._add_example_row(ex["before"], ex["after"])

    def _set_text(self, widget, value):
        widget.delete("1.0", "end")
        if value:
            widget.insert("1.0", value)

    def _get_text(self, widget):
        return widget.get("1.0", "end-1c").strip()

    def _get_voice_examples_from_ui(self):
        """Collect voice examples from the UI rows."""
        return [
            {"before": r["before"].get().strip(), "after": r["after"].get().strip()}
            for r in self._example_rows
            if r["before"].get().strip() or r["after"].get().strip()
        ]

    def _save(self):
        # Collect character fields
        name = self.name_var.get().strip()
        race = self.race_var.get().strip()
        class_ = self.class_var.get().strip()
        backstory = self._get_text(self.backstory_text)
        notes = self._get_text(self.notes_text)

        if not name or not race or not class_:
            messagebox.showwarning(
                "Missing Fields", "Name, Race, and Class are required."
            )
            return

        if self.character_id:
            update_character(self.conn, self.character_id,
                             name=name, race=race, class_=class_,
                             backstory=backstory, notes=notes)
            char_id = self.character_id
        else:
            char_id = add_character(self.conn, name, race, class_,
                                    backstory, notes)

        # Save voice examples
        clear_voice_examples(self.conn, char_id)
        for ex in self._get_voice_examples_from_ui():
            add_voice_example(self.conn, char_id, ex["before"], ex["after"])

        self.result = {"id": char_id, "name": name}
        self.destroy()

    def _generate_examples(self):
        name = self.name_var.get().strip()
        race = self.race_var.get().strip()
        class_ = self.class_var.get().strip()
        if not name or not race or not class_:
            messagebox.showwarning(
                "Missing Fields",
                "Fill in Name, Race, and Class before generating examples.",
            )
            return

        data = {
            "name": name,
            "race": race,
            "class": class_,
            "backstory": self._get_text(self.backstory_text),
            "notes": self._get_text(self.notes_text),
        }

        self.gen_btn.config(text="Generating...", state="disabled")

        def run():
            result = generate_voice_examples(data)
            self.after(0, lambda: self._on_examples_generated(result))

        threading.Thread(target=run, daemon=True).start()

    def _on_examples_generated(self, examples):
        self.gen_btn.config(text="Generate Examples", state="normal")
        # Clear existing rows, fill with generated examples
        for r in list(self._example_rows):
            self._remove_example_row(r["frame"])
        for ex in examples:
            before = ex.get("before", "")
            after = ex.get("after", "")
            self._add_example_row(before, after)


class MainWindow(tk.Tk):
    """Main application window."""

    def __init__(self, conn):
        super().__init__()
        self.conn = conn
        self.selected_character_id = None
        self.settings = load_settings()

        self.title("RP Translator")
        self.geometry("480x420")
        self.minsize(400, 300)

        # Apply always-on-top from settings
        self.attributes("-topmost", self.settings.get("always_on_top", False))

        self._hotkey_listener = None

        self._build_menu()
        self._build_ui()
        self._refresh_character_list()

        # Bind Ctrl+Enter to translate
        self.bind_all("<Control-Return>", lambda e: self._translate())

        # Protocol for close — just hide (hotkey brings it back; final quit via menu)
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

        # Start global hotkey listener
        self._start_hotkey_listener()

    # ── Menu ──────────────────────────────────────────────────────────────

    def _build_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)

        self.always_on_top_var = tk.BooleanVar(
            value=self.settings.get("always_on_top", False)
        )
        settings_menu.add_checkbutton(
            label="Always on Top",
            variable=self.always_on_top_var,
            command=self._toggle_always_on_top,
        )

        settings_menu.add_command(
            label="Configure Hotkey...",
            command=self._configure_hotkey,
        )

        settings_menu.add_separator()
        settings_menu.add_command(label="Exit", command=self._quit)

    def _toggle_always_on_top(self):
        on = self.always_on_top_var.get()
        self.attributes("-topmost", on)
        self.settings["always_on_top"] = on
        save_settings(self.settings)

    def _configure_hotkey(self):
        dialog = tk.Toplevel(self)
        dialog.title("Configure Hotkey")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=10)
        frame.pack()

        ttk.Label(
            frame, text="Press the key combination you want to use:"
        ).pack(pady=4)

        key_var = tk.StringVar(value=self.settings.get("hotkey", ""))
        ttk.Label(frame, textvariable=key_var, font=("TkDefaultFont", 12, "bold")).pack(
            pady=4
        )

        def on_key(event):
            parts = []
            if event.state & 0x4:
                parts.append("<ctrl>")
            if event.state & 0x1:
                parts.append("<shift>")
            if event.state & 0x20000:
                parts.append("<alt>")
            key = event.keysym.lower()
            if key not in ("control_l", "control_r", "shift_l", "shift_r",
                           "alt_l", "alt_r"):
                parts.append(f"<{key}>")
            if len(parts) > 1:  # at least one modifier + a key
                key_var.set("+".join(parts))

        dialog.bind("<KeyPress>", on_key)
        dialog.focus_set()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=8)

        def save_key():
            new_hotkey = key_var.get()
            if new_hotkey and "+" in new_hotkey:
                self.settings["hotkey"] = new_hotkey
                save_settings(self.settings)
                self._stop_hotkey_listener()
                self._start_hotkey_listener()
            dialog.destroy()

        ttk.Button(btn_frame, text="Save", command=save_key).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=4
        )

        dialog.update_idletasks()
        w, h = dialog.winfo_width(), dialog.winfo_height()
        px, py = self.winfo_rootx(), self.winfo_rooty()
        pw, ph = self.winfo_width(), self.winfo_height()
        dialog.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _quit(self):
        self._stop_hotkey_listener()
        self.destroy()

    # ── Hotkey ────────────────────────────────────────────────────────────

    def _start_hotkey_listener(self):
        """Start the global hotkey listener in a daemon thread.
        Updates the status bar label on success/failure."""
        hotkey_str = self.settings.get("hotkey", "<ctrl>+<shift>+t")

        try:
            from pynput.keyboard import GlobalHotKeys
        except ImportError:
            self._set_hotkey_status(f"Hotkey: pynput not installed", error=True)
            return

        def on_activate():
            self.deiconify()
            self.lift()
            self.focus_force()

        try:
            self._hotkey_listener = GlobalHotKeys({hotkey_str: on_activate})
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
            self._set_hotkey_status(f"Hotkey: {hotkey_str}")
        except Exception:
            self._set_hotkey_status(
                f"Hotkey: failed to register {hotkey_str}", error=True
            )

    def _set_hotkey_status(self, text, error=False):
        """Update the status bar hotkey label."""
        if hasattr(self, "hotkey_status"):
            self.hotkey_status.config(text=text)
            if error:
                self.hotkey_status.config(foreground="red")
            else:
                self.hotkey_status.config(foreground="gray")

    def _stop_hotkey_listener(self):
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top panel — Character selector
        top = ttk.LabelFrame(self, text="Character", padding=6)
        top.pack(fill="x", padx=8, pady=(8, 4))

        self.char_combo = ttk.Combobox(top, state="readonly", width=30)
        self.char_combo.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.char_combo.bind("<<ComboboxSelected>>", self._on_char_selected)

        ttk.Button(top, text="New", command=self._new_character).pack(
            side="left", padx=1
        )
        ttk.Button(top, text="Edit", command=self._edit_character).pack(
            side="left", padx=1
        )
        ttk.Button(top, text="Delete", command=self._delete_character).pack(
            side="left", padx=1
        )

        # Placeholder shown when no characters
        self.no_chars_label = ttk.Label(
            top, text="No characters — create one first", foreground="gray"
        )

        # Middle panel — Input
        mid = ttk.LabelFrame(self, text="Your Message", padding=6)
        mid.pack(fill="x", padx=8, pady=4)

        self.input_text = tk.Text(mid, height=3, wrap="word")
        self.input_text.pack(fill="x")
        # Update translate button state on input change
        self.input_text.bind("<KeyRelease>", lambda e: self._update_translate_state())

        btn_row = ttk.Frame(mid)
        btn_row.pack(fill="x", pady=(4, 0))

        self.translate_btn = ttk.Button(
            btn_row, text="Translate (Ctrl+Enter)", command=self._translate
        )
        self.translate_btn.pack(side="left")
        self.translate_btn.config(state="disabled")

        # Bottom panel — Result
        bot = ttk.LabelFrame(self, text="Translated", padding=6)
        bot.pack(fill="both", expand=True, padx=8, pady=4)

        self.result_text = tk.Text(bot, height=3, wrap="word", state="disabled")
        self.result_text.pack(fill="both", expand=True)

        copy_row = ttk.Frame(bot)
        copy_row.pack(fill="x", pady=(4, 0))

        self.copy_btn = ttk.Button(
            copy_row, text="Copy", command=self._copy_result
        )
        self.copy_btn.pack(side="left")

        # Status bar
        self.hotkey_status = ttk.Label(
            self, text="Hotkey: starting...", foreground="gray"
        )
        self.hotkey_status.pack(side="bottom", anchor="w", padx=8, pady=(2, 4))

    # ── Character management ──────────────────────────────────────────────

    def _refresh_character_list(self):
        chars = list_characters(self.conn)
        self._char_map = {c["name"]: c["id"] for c in chars}
        names = list(self._char_map.keys())
        self.char_combo["values"] = names

        if not names:
            self.char_combo.pack_forget()
            self.no_chars_label.pack(side="left", fill="x", expand=True)
            self.char_combo.set("")
            self.selected_character_id = None
        else:
            self.no_chars_label.pack_forget()
            self.char_combo.pack(side="left", fill="x", expand=True, padx=(0, 4))
            # Re-select if possible
            if self.char_combo.get() in self._char_map:
                pass  # keep selection
            elif names:
                self.char_combo.set(names[0])
                self.selected_character_id = self._char_map[names[0]]

        self._update_translate_state()

    def _on_char_selected(self, event=None):
        name = self.char_combo.get()
        self.selected_character_id = self._char_map.get(name)
        self._update_translate_state()

    def _new_character(self):
        dialog = CharacterDialog(self, self.conn)
        self.wait_window(dialog)
        if dialog.result:
            self._refresh_character_list()
            self.char_combo.set(dialog.result["name"])
            self.selected_character_id = dialog.result["id"]
            self._update_translate_state()

    def _edit_character(self):
        if not self.selected_character_id:
            return
        dialog = CharacterDialog(self, self.conn, self.selected_character_id)
        self.wait_window(dialog)
        if dialog.result:
            self._refresh_character_list()
            self.char_combo.set(dialog.result["name"])
            self.selected_character_id = dialog.result["id"]

    def _delete_character(self):
        if not self.selected_character_id:
            return
        char = get_character(self.conn, self.selected_character_id)
        if not char:
            return
        ok = messagebox.askyesno(
            "Delete Character",
            f'Delete "{char["name"]}"? This cannot be undone.',
        )
        if ok:
            delete_character(self.conn, self.selected_character_id)
            self.selected_character_id = None
            self._refresh_character_list()

    # ── Translation ───────────────────────────────────────────────────────

    def _update_translate_state(self):
        has_char = self.selected_character_id is not None
        has_input = bool(self.input_text.get("1.0", "end-1c").strip())
        if has_char and has_input:
            self.translate_btn.config(state="normal")
        else:
            self.translate_btn.config(state="disabled")

    def _translate(self):
        if not self.selected_character_id:
            return
        user_message = self.input_text.get("1.0", "end-1c").strip()
        if not user_message:
            return

        char = get_character(self.conn, self.selected_character_id)
        if not char:
            return

        voice_examples = get_voice_examples(self.conn, self.selected_character_id)
        system_prompt = build_system_prompt(char, voice_examples)

        self.translate_btn.config(text="Translating...", state="disabled")

        def run():
            result = call_llm(system_prompt, user_message)
            self.after(0, lambda: self._on_translate_done(result))

        threading.Thread(target=run, daemon=True).start()

    def _on_translate_done(self, result):
        self.translate_btn.config(text="Translate (Ctrl+Enter)")
        self._update_translate_state()

        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")

        if result.startswith("API") or result.startswith("Network") or \
           result.startswith("Translation timed") or result.startswith("Error"):
            self.result_text.insert("1.0", result)
            self.result_text.tag_add("error", "1.0", "end")
            self.result_text.tag_config("error", foreground="red")
        else:
            self.result_text.insert("1.0", result)
            self.result_text.tag_remove("error", "1.0", "end")
            # Auto-copy to clipboard
            self._copy_result()

        self.result_text.config(state="disabled")

    def _copy_result(self):
        text = self.result_text.get("1.0", "end-1c").strip()
        if not text:
            return
        try:
            import pyperclip
            pyperclip.copy(text)
            self.copy_btn.config(text="Copied!")
            self.after(1500, lambda: self.copy_btn.config(text="Copy"))
        except Exception:
            pass  # clipboard may not be available


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "characters.db")
    conn = sqlite3.connect(db_path)
    init_db(conn)
    app = MainWindow(conn)
    app.mainloop()
    conn.close()


if __name__ == "__main__":
    main()
