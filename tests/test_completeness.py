"""Answers are never cut: truncated outputs are continued, big prompts condensed."""

from langchain_core.messages import AIMessage

from app.agents.nodes import TravelAgents
from tests.fakes import FakeTools


class ScriptedLLM:
    """Returns the given replies in order and records every call."""

    def __init__(self, *replies: tuple[str, str]):
        self.replies = list(replies)
        self.calls: list[list] = []

    def invoke(self, messages, config=None):
        self.calls.append(messages)
        text, finish_reason = self.replies.pop(0)
        return AIMessage(content=text, response_metadata={"finish_reason": finish_reason})


def test_truncated_answer_is_continued():
    llm = ScriptedLLM(("Day 1: Arrive. Day 2: Vis", "length"), ("it the temples.", "stop"))
    agents = TravelAgents(llm, FakeTools())

    assert agents._ask("system", "plan") == "Day 1: Arrive. Day 2: Visit the temples."
    # The second call carries the partial answer and asks to continue.
    assert llm.calls[1][-2].content == "Day 1: Arrive. Day 2: Vis"
    assert "Continue exactly where you stopped" in llm.calls[1][-1].content


def test_continuations_are_bounded():
    llm = ScriptedLLM(("a", "length"), ("b", "length"), ("c", "length"))
    agents = TravelAgents(llm, FakeTools(), max_continuations=2)

    assert agents._ask("system", "plan") == "abc"
    assert len(llm.calls) == 3


def test_small_prompt_sections_pass_through_untouched():
    llm = ScriptedLLM()
    agents = TravelAgents(llm, FakeTools())
    sections = {"flight": "Short flight info.", "hotel": "Short hotel info."}

    assert agents._fit(sections) == sections
    assert llm.calls == []


def test_oversized_sections_are_condensed_not_cut():
    llm = ScriptedLLM(("Condensed hotel facts.", "stop"))
    agents = TravelAgents(llm, FakeTools(), prompt_budget_tokens=1000)
    huge_hotels = "Hotel Sakura is near Shinjuku station and costs 120 USD. " * 100

    fitted = agents._fit({"flight": "Fly BG376.", "hotel": huge_hotels})

    assert fitted == {"flight": "Fly BG376.", "hotel": "Condensed hotel facts."}
    condense_prompt = llm.calls[0][-1].content
    assert '"hotel" section' in condense_prompt
    assert huge_hotels.strip() in condense_prompt


def test_reviewed_draft_is_condensed_last():
    llm = ScriptedLLM(("Condensed budget.", "stop"))
    agents = TravelAgents(llm, FakeTools(), prompt_budget_tokens=1500)
    draft = "Day 1: Arrive and check in. " * 120
    budget = "Budget line with figures. " * 120

    fitted = agents._fit({"budget": budget, "itinerary": draft}, keep=("itinerary",))

    assert fitted["itinerary"] == draft.strip()
    assert fitted["budget"] == "Condensed budget."
