import json

import pytest

from app.agents.text import clip, compact_hotels, json_from_llm, short_sentences, tool_text


def test_clip_keeps_short_text_untouched():
    assert clip("  Short text.  ", 100) == "Short text."


def test_clip_cuts_at_last_complete_sentence():
    text = "First sentence here. Second sentence is longer. Third is cut in the middle"
    assert clip(text, 60) == "First sentence here. Second sentence is longer."


def test_clip_falls_back_to_word_boundary():
    assert clip("averyveryverylongword another word", 25) == "averyveryverylongword"


def test_short_sentences_collapses_whitespace():
    assert short_sentences("a\n\n   b   c", 100) == "a b c"


def test_tool_text_flattens_content_blocks():
    blocks = [{"type": "text", "text": "one"}, {"type": "text", "text": "two"}]
    assert tool_text(blocks) == "one\ntwo"


def test_compact_hotels_formats_tavily_results():
    payload = {
        "results": [
            {"title": f"Hotel {index}", "url": f"https://h/{index}", "content": "Nice. " * 100}
            for index in range(8)
        ]
    }
    compact = compact_hotels(json.dumps(payload))

    assert compact.count("\n   ") == 5
    assert compact.startswith("1. Hotel 0 - https://h/0")
    assert all(len(line) <= 260 for line in compact.splitlines())


def test_compact_hotels_handles_plain_text():
    assert compact_hotels("No JSON here.") == "No JSON here."


def test_json_from_llm_extracts_object_from_prose():
    assert json_from_llm('Sure: {"allowed": true} done') == {"allowed": True}


def test_json_from_llm_raises_without_object():
    with pytest.raises(ValueError):
        json_from_llm("no json")
