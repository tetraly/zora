"""tests/shared_builds.py's rules (docs/design/test-speed.md 3.1): each test loads a stored plan
at most once, a later request in the same test generates afresh, and a monkeypatched test
neither loads nor stores. Each check uses its own SharedBuilds, with a counting generator, in
this session's folder; a plan that no other test makes keeps the checks apart from the suite's
real builds."""
import uuid
from dataclasses import dataclass, field
from typing import Any

from tests.shared_builds import SharedBuilds

BASE_ROM = b"not a ROM: the key only hashes it"


@dataclass(frozen=True)
class FakePlan:
    """Stands in for a GenerationPlan: the key is its repr, unique to each check."""
    name: str = field(default_factory=lambda: uuid.uuid4().hex)


class CountingGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, chosen: Any, base_rom: bytes) -> Any:
        self.calls += 1
        return (chosen.name, self.calls)


def shared() -> tuple[SharedBuilds, CountingGenerator]:
    generator = CountingGenerator()
    builds = SharedBuilds(generator)
    builds.begin_test(False)
    assert builds.folder() is not None, "the session's shared folder (tests/conftest.py)"
    return builds, generator


def test_another_test_loads_the_stored_plan() -> None:
    builds, generator = shared()
    plan = FakePlan()
    first = builds(plan, BASE_ROM)                # type: ignore[arg-type]
    builds.begin_test(False)                      # the next test, in this same process
    assert builds(plan, BASE_ROM) == first        # type: ignore[arg-type]
    assert generator.calls == 1


def test_a_later_request_in_the_same_test_generates_afresh() -> None:
    builds, generator = shared()
    plan = FakePlan()
    builds(plan, BASE_ROM)                        # type: ignore[arg-type]
    builds.begin_test(False)
    builds(plan, BASE_ROM)                        # type: ignore[arg-type]  # loaded
    builds(plan, BASE_ROM)                        # type: ignore[arg-type]  # the same test again: generated
    assert generator.calls == 2


def test_a_monkeypatched_test_neither_loads_nor_stores() -> None:
    builds, generator = shared()
    plan = FakePlan()
    builds.begin_test(True)
    builds(plan, BASE_ROM)                        # type: ignore[arg-type]  # generated, not stored
    builds.begin_test(False)
    builds(plan, BASE_ROM)                        # type: ignore[arg-type]  # nothing stored: generated and stored
    builds.begin_test(True)
    builds(plan, BASE_ROM)                        # type: ignore[arg-type]  # stored, but not loaded
    assert generator.calls == 3
