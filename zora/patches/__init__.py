import importlib
import inspect
import logging
import pkgutil

from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, VariableBehaviorPatch
from zora.serializer import Patch

log = logging.getLogger(__name__)

_REGISTRY: list[BehaviorPatch] = []


def _autodiscover() -> None:
    for _, module_name, _ in pkgutil.iter_modules(__path__):
        if module_name == "base":
            continue
        mod = importlib.import_module(f"zora.patches.{module_name}")
        for attr in vars(mod).values():
            if (isinstance(attr, type)
                    and issubclass(attr, BehaviorPatch)
                    and attr is not BehaviorPatch
                    and attr is not VariableBehaviorPatch
                    and not inspect.isabstract(attr)):
                _REGISTRY.append(attr())


_autodiscover()


def build_behavior_patch(config: GameConfig, rom_version: int | None = None) -> Patch:
    """
    Return a Patch containing all edits for patches active under this config.
    Raises ValueError if two patches write to the same ROM offset.
    """
    patch = Patch()
    seen: dict[int, str] = {}

    for bp in _REGISTRY:
        if not bp.is_active(config):
            continue
        edits = (
            bp.get_edits_for_config(config, rom_version)
            if isinstance(bp, VariableBehaviorPatch)
            else bp.get_edits(rom_version)
        )
        for edit in edits:
            if edit.offset in seen:
                raise ValueError(
                    f"Patch conflict at {edit.offset:#x}: "
                    f"{seen[edit.offset]} and {bp.name} both write this offset"
                )
            seen[edit.offset] = bp.name
            patch.add(edit.offset, edit.new_bytes)

    return patch
