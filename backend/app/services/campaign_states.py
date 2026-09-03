"""Campaign state machine — rejects impossible transitions."""

CANCEL_FROM = {"draft", "scheduled"}
PAUSE_FROM = {"running"}

VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"scheduled", "cancelled", "running"},
    "scheduled": {"running", "cancelled", "paused"},
    "running": {"paused", "completed", "cancelled"},
    "paused": {"running", "cancelled", "completed", "draft"},
    "completed": set(),
    "cancelled": set(),
}


def can_transition(current: str, next_: str) -> bool:
    return next_ in VALID_TRANSITIONS.get(current, set())


def is_terminal(status: str) -> bool:
    return status in ("completed", "cancelled")