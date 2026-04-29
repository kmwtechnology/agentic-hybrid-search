"""Pre-flight guard: every backend event-type Literal must be declared in
the frontend TypeScript event union.

Catches drift like the 2026-04-29 review finding: backend rename of
`ConnectionError` -> `ConnectionErrorEvent` left the union including
the Python builtin, and would have only surfaced at runtime when a
ConnectionErrorEvent was emitted.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EVENTS_PY = REPO_ROOT / "api" / "schemas" / "events.py"
EVENTS_TS = REPO_ROOT / "web" / "src" / "types" / "events.ts"

PY_LITERAL = re.compile(r"""type:\s*Literal\[\s*["']([a-z_]+)["']\s*\]""")
TS_LITERAL = re.compile(r"""type:\s*['"]([a-z_]+)['"]""")


@pytest.mark.unit
def test_backend_event_types_exist_in_frontend() -> None:
    py_types = set(PY_LITERAL.findall(EVENTS_PY.read_text()))
    ts_types = set(TS_LITERAL.findall(EVENTS_TS.read_text()))

    assert py_types, "events.py exposes no `type: Literal[...]` declarations"
    assert ts_types, "events.ts exposes no `type: '...'` declarations"

    missing_in_ts = py_types - ts_types
    assert not missing_in_ts, (
        "Backend event types declared in api/schemas/events.py but missing "
        f"from web/src/types/events.ts: {sorted(missing_in_ts)}. Frontend "
        "will silently drop these events."
    )


@pytest.mark.unit
def test_no_python_builtin_in_event_union() -> None:
    """Catch unions that reference Python builtins instead of the renamed
    *Event class — e.g. `| ConnectionError` (builtin) vs
    `| ConnectionErrorEvent` (our class).
    """
    src = EVENTS_PY.read_text()
    union_match = re.search(r"AgentEvent\s*=\s*\(([^)]+)\)", src, re.DOTALL)
    assert union_match, "AgentEvent union not found in events.py"

    union_body = union_match.group(1)
    members = [m.strip().lstrip("|").strip() for m in union_body.split("\n") if m.strip()]
    builtins = {"ConnectionError", "Exception", "BaseException", "ValueError", "TypeError"}
    offenders = [m for m in members if m in builtins]
    assert not offenders, (
        "AgentEvent union references Python builtins instead of *Event classes: "
        f"{offenders}. Pydantic would silently accept any object of these types."
    )
