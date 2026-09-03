import pytest

from app.services.campaign_states import VALID_TRANSITIONS, can_transition, is_terminal

VALID = [
    ("draft", "scheduled"),
    ("draft", "cancelled"),
    ("draft", "running"),
    ("scheduled", "running"),
    ("scheduled", "cancelled"),
    ("scheduled", "paused"),
    ("running", "paused"),
    ("running", "completed"),
    ("running", "cancelled"),
    ("paused", "running"),
    ("paused", "cancelled"),
    ("paused", "completed"),
    ("paused", "draft"),
]

INVALID = [
    ("completed", "running"),
    ("completed", "paused"),
    ("completed", "draft"),
    ("cancelled", "running"),
    ("cancelled", "draft"),
    ("running", "draft"),
]


@pytest.mark.parametrize("src,dst", VALID)
def test_valid_transitions(src: str, dst: str):
    assert can_transition(src, dst) is True


@pytest.mark.parametrize("src,dst", INVALID)
def test_invalid_transitions(src: str, dst: str):
    assert can_transition(src, dst) is False


@pytest.mark.parametrize("state", ["completed", "cancelled"])
def test_terminal_states(state: str):
    assert is_terminal(state) is True


@pytest.mark.parametrize("state", ["draft", "scheduled", "running", "paused"])
def test_non_terminal_states(state: str):
    assert is_terminal(state) is False


def test_valid_transitions_table_is_symmetric():
    expected_keys = {"draft", "scheduled", "running", "paused", "completed", "cancelled"}
    for src, dst in VALID:
        assert can_transition(src, dst) is True
    for state in ("completed", "cancelled"):
        assert VALID_TRANSITIONS[state] == set()
    assert set(VALID_TRANSITIONS.keys()) == expected_keys