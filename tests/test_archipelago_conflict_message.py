"""OptionsConflict keeps its reasons when pickled (a process pool's scan sends it back to the parent):
it was rebuilt from its message, which it then joined letter by letter (2026-10-28)."""
import pickle

from zora.archipelago import OptionsConflict


def test_a_pickled_conflict_keeps_its_reasons_and_message() -> None:
    conflict = OptionsConflict(["first reason", "second reason"])
    copy = pickle.loads(pickle.dumps(conflict))
    assert copy.reasons == conflict.reasons
    assert str(copy) == str(conflict) == "ZORA cannot generate these options: first reason; second reason"
