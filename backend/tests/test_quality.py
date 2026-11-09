from datetime import date

import pytest
from meeting_agent.quality import (
    apply_deadlines,
    apply_grounding,
    find_context,
    remove_duplicates,
    resolve_deadline,
)
from meeting_agent.schemas import ActionItem

WEDNESDAY = date(2026, 11, 4)


def item(description="Send the budget", quote="I'll send the budget.", **fields):
    return ActionItem(description=description, source_quote=quote, **fields)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("by Friday", date(2026, 11, 6)),
        ("Monday", date(2026, 11, 9)),
        ("next Friday", date(2026, 11, 13)),
        ("next Monday", date(2026, 11, 9)),
        ("Wednesday", date(2026, 11, 11)),
        ("tomorrow", date(2026, 11, 5)),
        ("end of day", WEDNESDAY),
        ("by the end of the week", date(2026, 11, 6)),
        ("next week", date(2026, 11, 13)),
        ("end of the month", date(2026, 11, 30)),
        ("in 3 days", date(2026, 11, 7)),
        ("in two weeks", None),
        ("November 15th", date(2026, 11, 15)),
        ("15 Nov", date(2026, 11, 15)),
        ("January 5", date(2027, 1, 5)),
        ("2026-12-01", date(2026, 12, 1)),
    ],
)
def test_resolve_deadline(text, expected):
    assert resolve_deadline(text, WEDNESDAY) == expected


@pytest.mark.parametrize(
    "text", ["next meeting", "soon", "February 30", "2026-01-01", "2029-01-01"]
)
def test_unknown_impossible_past_or_far_dates_are_left_empty(text):
    assert resolve_deadline(text, WEDNESDAY) is None


def test_quote_not_in_transcript_is_rejected():
    assert apply_grounding([item(quote="I never said this.")], "Ana: I'll send the budget.") == []


def test_near_exact_spoken_quote_is_accepted():
    transcript = "Ana: I'll I'll send the the budget over to finance on Friday , okay ."
    assert (
        len(
            apply_grounding(
                [item(quote="I'll send the budget over to finance on Friday")], transcript
            )
        )
        == 1
    )


def test_loosely_similar_quote_is_still_rejected():
    transcript = "Ana: the budget review went well and finance was happy with it ."
    assert (
        apply_grounding([item(quote="finance will review the budget and approve it")], transcript)
        == []
    )


def test_find_context_returns_nearby_lines():
    lines = [f"Speaker{i}: filler {i}" for i in range(10)]
    lines[5] = "Boss: Ana, you'll send the budget."
    context = find_context("you'll send the budget", "\n".join(lines))
    assert "Speaker2" in context and "Boss" in context and "Speaker6" in context
    assert "Speaker1:" not in context


def test_quote_match_ignores_case_spacing_and_curly_quotes():
    kept = apply_grounding([item(quote="i’ll  SEND the budget.")], "Ana: I'll send the budget.")
    assert len(kept) == 1


@pytest.mark.parametrize("owner", ["Team", "the team", "Everyone", "Priya"])
def test_group_and_unmentioned_owners_are_cleared(owner):
    kept = apply_grounding([item(owner=owner)], "Team: everyone agreed. Ana: I'll send the budget.")
    assert kept[0].owner is None


def test_real_owner_is_kept():
    assert apply_grounding([item(owner="Ana")], "Ana: I'll send the budget.")[0].owner == "Ana"


def test_invented_deadline_is_cleared():
    kept = apply_grounding([item(deadline_text="by Friday")], "Ana: I'll send the budget.")
    assert kept[0].deadline_text is None


def test_apply_deadlines_fills_the_date():
    assert apply_deadlines([item(deadline_text="Friday")], WEDNESDAY)[0].deadline == date(
        2026, 11, 6
    )


def test_apply_deadlines_without_meeting_date_changes_nothing():
    assert apply_deadlines([item(deadline_text="Friday")], None)[0].deadline is None


def test_reworded_duplicate_is_merged_and_keeps_extra_details():
    kept = remove_duplicates(
        [item("Send the budget to finance"), item("Send budget to finance", owner="Ana")]
    )
    assert len(kept) == 1
    assert kept[0].owner == "Ana"


def test_same_task_from_chunk_overlap_is_merged():
    kept = remove_duplicates(
        [item("Send finance the budget file"), item("Email finance budget file")]
    )
    assert len(kept) == 1


def test_two_tasks_in_one_quote_are_both_kept():
    quote = "I'll send the budget and book the room."
    assert (
        len(remove_duplicates([item("Send the budget", quote), item("Book the room", quote)])) == 2
    )


def test_different_tasks_are_kept():
    assert len(remove_duplicates([item("Send budget"), item("Fix login page", "Fix login.")])) == 2
