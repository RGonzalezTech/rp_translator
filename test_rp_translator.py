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


# ── LLM Client tests ──────────────────────────────────────────────────────────

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
    assert "api key" in result.lower()


def test_call_llm_timeout(monkeypatch):
    import requests as req_module
    from rp_translator import call_llm

    # Ensure API key is set so we get past the key check
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    # Mock requests.post to raise Timeout
    def mock_post(*args, **kwargs):
        raise req_module.exceptions.Timeout("timed out")

    monkeypatch.setattr("rp_translator.requests.post", mock_post)
    result = call_llm("system", "user message")
    assert "timed out" in result.lower()


def test_generate_voice_examples_returns_string(monkeypatch):
    from rp_translator import generate_voice_examples
    # Mock call_llm to avoid real API call
    def mock_call_llm(system_prompt, user_message, timeout=30):
        return "gj team -> The Light protects us!\nincoming -> They approach!"
    monkeypatch.setattr("rp_translator.call_llm", mock_call_llm)
    char = {"name": "Test", "race": "Human", "class": "Paladin",
            "backstory": "Knight of the Silver Hand", "notes": ""}
    result = generate_voice_examples(char)
    assert isinstance(result, str)
    assert len(result) > 0
