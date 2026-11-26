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
    cid = add_character(conn, "Thrall", "Orc", "Shaman",
                        "Warchief", "Speaks in proverbs", "gj -> Lok'tar!")
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
