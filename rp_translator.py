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
