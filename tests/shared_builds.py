"""Shared builds for a test session (tasks/test-speed-2.md).

Many test files build the same flag cases and seeds (tests/archipelago_cases.py, seeds 1-4
above all), each in its own process under xdist. BUILD's generation (pipeline.generate_world)
is a function of its plan and base ROM, so a session's processes share its results through a
folder that lives as long as the session (tests/conftest.py makes and removes it): the first
process to ask for a (plan, base ROM) generates and stores the world, while others asking at
the same time wait for it, and another process's first request loads the stored copy.

Every later request in the same process generates afresh, so a test that builds twice and
compares (a determinism check, a recipe rebuilt) still compares two generations; a test that
monkeypatches anything neither loads nor stores (its generation may be patched).

prebuild() generates a list of plans in a few processes into the folder, so a test that walks
many seeds one after another loads them instead of generating each in turn.
"""
import os
import pickle
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha1
from pathlib import Path

import zora.generate.pipeline as pipeline
from zora.generate.context import GenerationResult
from zora.model.game_world import GameWorld
from zora.rom.base_rom import remember_base_rom, remember_repo_base_rom

FOLDER_ENV = "ZORA_TEST_SHARED_BUILDS"
WAIT_SECONDS = 120                      # past this, a waiting process generates its own
POLL_SECONDS = 0.05
PREBUILD_PROCESSES = 4                  # beside xdist's workers

World = tuple[GameWorld, GenerationResult]
GenerateWorld = Callable[[pipeline.GenerationPlan, bytes], World]


class SharedBuilds:
    """generate_world through the session's shared folder (see the module docstring)."""

    def __init__(self, generate_world: GenerateWorld) -> None:
        self.generate_world = generate_world
        self.handed_out: set[str] = set()       # keys this process has already had once
        self.patched_test = False                # the running test uses monkeypatch

    def folder(self) -> Path | None:
        folder = os.environ.get(FOLDER_ENV)
        return Path(folder) if folder and not self.patched_test else None

    def __call__(self, chosen: pipeline.GenerationPlan, base_rom: bytes) -> World:
        folder = self.folder()
        key = sha1(repr(chosen).encode() + sha1(base_rom).digest()).hexdigest()
        if folder is None or key in self.handed_out:
            return self.generate_world(chosen, base_rom)
        self.handed_out.add(key)
        path = folder / f"{key}.pickle"
        lock = folder / f"{key}.lock"
        if not path.exists():
            try:
                lock.open("x").close()           # this process generates; others wait for it
            except FileExistsError:
                deadline = time.monotonic() + WAIT_SECONDS
                while lock.exists() and not path.exists() and time.monotonic() < deadline:
                    time.sleep(POLL_SECONDS)
            else:
                try:
                    if not path.exists():        # stored between the check and the lock
                        return self._generate_and_store(chosen, base_rom, path)
                finally:
                    lock.unlink()
        if not path.exists():                    # the generating process failed or is slow
            return self.generate_world(chosen, base_rom)
        remember_base_rom(base_rom)              # generate_world's side effect, before any read
        with path.open("rb") as stored:
            world: World = pickle.load(stored)
        return world

    def _generate_and_store(self, chosen: pipeline.GenerationPlan, base_rom: bytes, path: Path) -> World:
        generated = self.generate_world(chosen, base_rom)
        # Waiting processes poll for the file: write privately, then rename.
        partial = path.with_name(f"{path.name}.part")
        partial.write_bytes(pickle.dumps(generated, protocol=pickle.HIGHEST_PROTOCOL))
        os.replace(partial, path)
        return generated


def install() -> SharedBuilds:
    """Route this process's generate_world through the shared folder (once)."""
    if not isinstance(pipeline.generate_world, SharedBuilds):
        pipeline.generate_world = SharedBuilds(pipeline.generate_world)
    return pipeline.generate_world


def _prebuild_one(flags: tuple[str, int, str]) -> None:
    flag_string, seed, zora_flag_string = flags
    try:
        install()(pipeline.plan(flag_string, seed, zora_flag_string), remember_repo_base_rom())
    except Exception:  # nothing is stored; the test's own call raises it again
        pass


def prebuild(flag_cases: Iterable[tuple[str, str]], seeds: Iterable[int]) -> None:
    """Store each (flag string, ZORA flag string) case's world at each seed, generated in a few
    processes. Without the session's folder (a monkeypatched test, or no conftest) it does
    nothing: the test then generates as before."""
    if install().folder() is None:
        return
    wanted = [(flag_string, seed, zora_flag_string)
              for flag_string, zora_flag_string in flag_cases for seed in seeds]
    with ProcessPoolExecutor(PREBUILD_PROCESSES) as pool:
        list(pool.map(_prebuild_one, wanted))
