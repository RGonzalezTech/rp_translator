# test_rp_translator.py
import sqlite3
import pytest
from rp_translator import (
    init_db, add_character, get_character, list_characters, delete_character,
    get_voice_examples, add_voice_example, update_voice_example,
    delete_voice_example, clear_voice_examples,
)


@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


# ── Character CRUD ────────────────────────────────────────────────────────────

def test_add_and_get_character(conn):
    cid = add_character(conn, "Thrall", "Orc", "Shaman",
                        "Warchief", "Speaks in proverbs")
    char = get_character(conn, cid)
    assert char["name"] == "Thrall"
    assert char["race"] == "Orc"
    assert "voice_examples" not in char  # no longer a column


def test_list_characters_empty(conn):
    assert list_characters(conn) == []


def test_list_characters(conn):
    add_character(conn, "A", "Human", "Warrior", "", "")
    add_character(conn, "B", "Elf", "Mage", "", "")
    chars = list_characters(conn)
    assert len(chars) == 2


def test_update_character(conn):
    cid = add_character(conn, "Old", "Orc", "Rogue", "", "")
    from rp_translator import update_character
    update_character(conn, cid, name="New")
    assert get_character(conn, cid)["name"] == "New"


def test_delete_character(conn):
    cid = add_character(conn, "ToDelete", "Troll", "Priest", "", "")
    assert delete_character(conn, cid) is True
    assert get_character(conn, cid) is None


def test_delete_character_cascades_voice_examples(conn):
    """Voice examples are deleted when the character is deleted (ON DELETE CASCADE)."""
    cid = add_character(conn, "Cascade", "Human", "Mage", "", "")
    add_voice_example(conn, cid, "hello", "Greetings!")
    add_voice_example(conn, cid, "bye", "Farewell!")
    assert len(get_voice_examples(conn, cid)) == 2
    delete_character(conn, cid)
    assert get_voice_examples(conn, cid) == []


# ── Voice Examples CRUD ───────────────────────────────────────────────────────

def test_voice_examples_empty_for_new_character(conn):
    cid = add_character(conn, "New", "Elf", "Hunter", "", "")
    assert get_voice_examples(conn, cid) == []


def test_add_and_get_voice_examples(conn):
    cid = add_character(conn, "Garrosh", "Orc", "Warrior", "", "")
    add_voice_example(conn, cid, "gj team", "Lok'tar ogar!")
    add_voice_example(conn, cid, "retreat", "Cowards!")
    examples = get_voice_examples(conn, cid)
    assert len(examples) == 2
    assert examples[0]["before"] == "gj team"
    assert examples[0]["after"] == "Lok'tar ogar!"
    assert examples[1]["before"] == "retreat"
    assert examples[1]["after"] == "Cowards!"


def test_update_voice_example(conn):
    cid = add_character(conn, "Varian", "Human", "Warrior", "", "")
    eid = add_voice_example(conn, cid, "old before", "old after")
    updated = update_voice_example(conn, eid, "new before", "new after")
    assert updated is True
    examples = get_voice_examples(conn, cid)
    assert examples[0]["before"] == "new before"
    assert examples[0]["after"] == "new after"


def test_delete_voice_example(conn):
    cid = add_character(conn, "Jaina", "Human", "Mage", "", "")
    eid = add_voice_example(conn, cid, "hello", "Well met!")
    assert delete_voice_example(conn, eid) is True
    assert get_voice_examples(conn, cid) == []


def test_clear_voice_examples(conn):
    cid = add_character(conn, "Anduin", "Human", "Priest", "", "")
    add_voice_example(conn, cid, "a", "A")
    add_voice_example(conn, cid, "b", "B")
    add_voice_example(conn, cid, "c", "C")
    count = clear_voice_examples(conn, cid)
    assert count == 3
    assert get_voice_examples(conn, cid) == []


def test_voice_examples_isolated_per_character(conn):
    c1 = add_character(conn, "Char1", "Orc", "Warrior", "", "")
    c2 = add_character(conn, "Char2", "Human", "Mage", "", "")
    add_voice_example(conn, c1, "hi", "Hello!")
    add_voice_example(conn, c2, "bye", "Goodbye!")
    assert len(get_voice_examples(conn, c1)) == 1
    assert len(get_voice_examples(conn, c2)) == 1


# ── Migration ─────────────────────────────────────────────────────────────────

def test_migration_parses_old_format(conn):
    """Migration should parse old 'before -> after' lines into the new table."""
    # Manually insert a character with old-format voice_examples
    conn.execute(
        "INSERT INTO characters (name, race, class, voice_examples) "
        "VALUES ('OldChar', 'Troll', 'Shaman', 'gj -> Lok''tar!\nhey -> Greetings')"
    )
    conn.commit()
    # Re-run init_db which calls _migrate_voice_examples
    init_db(conn)
    char_id = conn.execute("SELECT id FROM characters WHERE name='OldChar'").fetchone()[0]
    examples = get_voice_examples(conn, char_id)
    assert len(examples) == 2
    assert examples[0]["before"] == "gj"
    assert examples[0]["after"] == "Lok'tar!"
    assert examples[1]["before"] == "hey"
    assert examples[1]["after"] == "Greetings"


# ── Settings ──────────────────────────────────────────────────────────────────

def test_settings_defaults():
    from rp_translator import load_settings
    settings = load_settings()
    assert "hotkey" in settings
    assert "always_on_top" in settings
    assert settings["always_on_top"] is False


# ── LLM Client tests ──────────────────────────────────────────────────────────

def test_build_system_prompt():
    from rp_translator import build_system_prompt
    char = {"name": "Thrall", "race": "Orc", "class": "Shaman",
            "backstory": "Warchief", "notes": "Speaks wisdom"}
    examples = [{"before": "gj", "after": "Lok'tar!"}]
    prompt = build_system_prompt(char, examples)
    assert "Thrall" in prompt
    assert "Orc" in prompt
    assert "Shaman" in prompt
    assert "Warchief" in prompt
    assert "Lok'tar" in prompt
    assert "gj -> Lok'tar!" in prompt
    assert "%t" in prompt  # token instruction present


def test_build_system_prompt_no_examples():
    from rp_translator import build_system_prompt
    char = {"name": "Solo", "race": "Troll", "class": "Rogue",
            "backstory": "", "notes": ""}
    prompt = build_system_prompt(char)  # no examples passed
    assert "Solo" in prompt
    assert "You talk like this" in prompt  # section header still present


def test_build_system_prompt_special_chars():
    from rp_translator import build_system_prompt
    char = {"name": "D'rath", "race": "Night Elf", "class": "Druid",
            "backstory": 'Follower of "Elune"', "notes": "Loves %t"}
    examples = [{"before": "hi", "after": "greetings"}]
    prompt = build_system_prompt(char, examples)
    assert "D'rath" in prompt
    assert 'Elune' in prompt
    assert "hi -> greetings" in prompt


def test_call_llm_missing_key(monkeypatch):
    from rp_translator import call_llm
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = call_llm("system", "user message")
    assert "api key" in result.lower()


def test_call_llm_timeout(monkeypatch):
    import requests as req_module
    from rp_translator import call_llm

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def mock_post(*args, **kwargs):
        raise req_module.exceptions.Timeout("timed out")

    monkeypatch.setattr("rp_translator.requests.post", mock_post)
    result = call_llm("system", "user message")
    assert "timed out" in result.lower()


def test_generate_voice_examples_returns_list(monkeypatch):
    from rp_translator import generate_voice_examples

    def mock_call_llm(system_prompt, user_message, timeout=30):
        return '[{"before": "gj team", "after": "The Light protects us!"}, {"before": "incoming", "after": "They approach!"}]'

    monkeypatch.setattr("rp_translator.call_llm", mock_call_llm)
    char = {"name": "Test", "race": "Human", "class": "Paladin",
            "backstory": "Knight of the Silver Hand", "notes": ""}
    result = generate_voice_examples(char)
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["before"] == "gj team"
    assert result[0]["after"] == "The Light protects us!"
    assert result[1]["after"] == "They approach!"


def test_generate_voice_examples_fallback_text_parse(monkeypatch):
    """When JSON parsing fails, fall back to 'before -> after' line parsing."""
    from rp_translator import generate_voice_examples

    def mock_call_llm(system_prompt, user_message, timeout=30):
        return "hello -> Greetings, mortal\nbye -> Farewell, champion!"

    monkeypatch.setattr("rp_translator.call_llm", mock_call_llm)
    char = {"name": "Test", "race": "Orc", "class": "Warrior",
            "backstory": "", "notes": ""}
    result = generate_voice_examples(char)
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["before"] == "hello"
    assert result[0]["after"] == "Greetings, mortal"
    assert result[1]["before"] == "bye"
    assert result[1]["after"] == "Farewell, champion!"


def test_call_llm_does_not_embed_user_message_in_system_prompt(monkeypatch):
    """call_llm must NOT put the user message inside the system prompt —
    it must only appear as the 'user' role in the messages array."""
    from rp_translator import call_llm, build_system_prompt
    import requests as req_module

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    captured_payload = {}
    def mock_post(url, **kwargs):
        captured_payload["json"] = kwargs.get("json", {})
        class FakeResp:
            status_code = 200
            def json(self):
                return {"choices": [{"message": {"content": "The Light protects us!"}}]}
        return FakeResp()

    monkeypatch.setattr("rp_translator.requests.post", mock_post)

    char = {"name": "Thrall", "race": "Orc", "class": "Shaman",
            "backstory": "Warchief", "notes": ""}
    examples = [{"before": "gj", "after": "Lok'tar!"}]
    system_prompt = build_system_prompt(char, examples)
    result = call_llm(system_prompt, "Hey, can you play tonight?")

    messages = captured_payload["json"]["messages"]
    system_content = messages[0]["content"]
    user_content = messages[1]["content"]

    assert "Hey, can you play tonight?" not in system_content, (
        "User message leaked into system prompt! "
        "The LLM gets confused when the message appears in both system and user roles."
    )
    assert user_content == "Hey, can you play tonight?"
    assert result == "The Light protects us!"
