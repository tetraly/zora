"""Tests for the ZORA Flask API — exercises the full request pipeline."""
import base64
from collections.abc import Generator

import pytest
from flask.testing import FlaskClient

from flags.flags_generated import FLAG_STRING_LENGTH
from zora.api import create_app


@pytest.fixture
def client() -> Generator[FlaskClient, None, None]:
    app = create_app({"TESTING": True})
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

def test_health(client: FlaskClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"
    assert "version" in data


# ---------------------------------------------------------------------------
# GET /flags
# ---------------------------------------------------------------------------

def test_flags_returns_schema(client: FlaskClient) -> None:
    r = client.get("/flags")
    assert r.status_code == 200
    data = r.get_json()
    assert data["schema_version"] == 3
    assert data["string_length"] == FLAG_STRING_LENGTH
    assert "cosmetic_string_length" in data
    assert isinstance(data["flags"], list)
    assert len(data["flags"]) > 0
    assert isinstance(data["item_enum"], list)
    assert isinstance(data["groups"], list)


def test_flags_only_enabled(client: FlaskClient) -> None:
    r = client.get("/flags")
    data = r.get_json()
    for flag in data["flags"]:
        assert flag.get("enabled", True) is True


def test_flags_cache_header(client: FlaskClient) -> None:
    r = client.get("/flags")
    assert "max-age=3600" in r.headers.get("Cache-Control", "")


def test_flags_no_phase_field(client: FlaskClient) -> None:
    r = client.get("/flags")
    data = r.get_json()
    for flag in data["flags"]:
        assert "phase" not in flag


# ---------------------------------------------------------------------------
# POST /generate — valid requests
# ---------------------------------------------------------------------------

def test_generate_all_defaults(client: FlaskClient) -> None:
    all_defaults = "A" * FLAG_STRING_LENGTH
    r = client.post("/generate", json={"flag_string": all_defaults})
    assert r.status_code == 200
    data = r.get_json()
    assert data["flag_string"] == all_defaults
    assert isinstance(data["seed"], str)
    assert int(data["seed"]) >= 0
    assert data["patch_format"] == "ips"
    # patch is valid base64
    patch_bytes = base64.b64decode(data["patch"])
    assert patch_bytes[:5] == b"PATCH"
    assert patch_bytes[-3:] == b"EOF"


def test_generate_with_explicit_seed(client: FlaskClient) -> None:
    r = client.post("/generate", json={"flag_string": "AAAAAAAA", "seed": 42})
    assert r.status_code == 200
    data = r.get_json()
    assert data["seed"] == "42"


def test_generate_seed_as_string(client: FlaskClient) -> None:
    r = client.post("/generate", json={"flag_string": "AAAAAAAA", "seed": "99999"})
    assert r.status_code == 200
    assert r.get_json()["seed"] == "99999"


def test_generate_short_flag_string_padded(client: FlaskClient) -> None:
    # 4-char string should be right-padded to FLAG_STRING_LENGTH
    r = client.post("/generate", json={"flag_string": "AAAA"})
    assert r.status_code == 200
    assert r.get_json()["flag_string"] == "A" * FLAG_STRING_LENGTH


def test_generate_spoiler_log_present(client: FlaskClient) -> None:
    r = client.post("/generate", json={"flag_string": "AAAAAAAA"})
    data = r.get_json()
    assert "spoiler_log" in data
    assert isinstance(data["spoiler_log"], str)
    assert "Item Placements" in data["spoiler_log"]


def test_generate_hash_code_present(client: FlaskClient) -> None:
    r = client.post("/generate", json={"flag_string": "AAAAAAAA", "seed": 1})
    assert r.status_code == 200
    data = r.get_json()
    assert "hash_code" in data
    assert isinstance(data["hash_code"], list)
    assert len(data["hash_code"]) == 4
    assert all(isinstance(s, str) for s in data["hash_code"])


def test_generate_hash_code_deterministic(client: FlaskClient) -> None:
    payload = {"flag_string": "AAAAAAAA", "seed": 42}
    r1 = client.post("/generate", json=payload)
    r2 = client.post("/generate", json=payload)
    assert r1.get_json()["hash_code"] == r2.get_json()["hash_code"]


def test_generate_deterministic_with_same_seed(client: FlaskClient) -> None:
    payload = {"flag_string": "AAAAAAAA", "seed": 12345}
    r1 = client.post("/generate", json=payload)
    r2 = client.post("/generate", json=payload)
    assert r1.get_json()["patch"] == r2.get_json()["patch"]


# ---------------------------------------------------------------------------
# POST /generate — invalid flag strings
# ---------------------------------------------------------------------------

def test_generate_missing_flag_string(client: FlaskClient) -> None:
    r = client.post("/generate", json={"seed": 1})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_flag_string"


def test_generate_invalid_character(client: FlaskClient) -> None:
    r = client.post("/generate", json={"flag_string": "!@#$%^&*"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_flag_string"


def test_generate_too_long_flag_string(client: FlaskClient) -> None:
    r = client.post("/generate", json={"flag_string": "A" * (FLAG_STRING_LENGTH + 1)})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_flag_string"


# ---------------------------------------------------------------------------
# POST /generate — invalid seeds
# ---------------------------------------------------------------------------

def test_generate_negative_seed(client: FlaskClient) -> None:
    r = client.post("/generate", json={"flag_string": "AAAAAAAA", "seed": -1})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_seed"


def test_generate_seed_too_large(client: FlaskClient) -> None:
    r = client.post("/generate", json={"flag_string": "AAAAAAAA", "seed": 2**64})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_seed"


def test_generate_non_numeric_seed(client: FlaskClient) -> None:
    r = client.post("/generate", json={"flag_string": "AAAAAAAA", "seed": "banana"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_seed"


# ---------------------------------------------------------------------------
# POST /generate — flag validation errors
# ---------------------------------------------------------------------------

def test_generate_validation_error_ladder_at_coast(client: FlaskClient) -> None:
    # Encode coast_item = ladder (index 13) at bit_offset 40, 5 bits
    # Build bitfield manually: ladder = 13 = 0b01101, at offset 40
    bitfield = 13 << 40
    from flags.flags_generated import BASE64_ALPHABET, FLAG_STRING_LENGTH
    chars = []
    for _ in range(FLAG_STRING_LENGTH):
        chars.append(BASE64_ALPHABET[bitfield & 0x3F])
        bitfield >>= 6
    flag_string = "".join(chars)

    r = client.post("/generate", json={"flag_string": flag_string})
    assert r.status_code == 400
    data = r.get_json()
    assert data["error"] == "validation_failed"
    assert any("coast" in msg.lower() or "ladder" in msg.lower() for msg in data["details"])


# ---------------------------------------------------------------------------
# POST /generate/race — stub
# ---------------------------------------------------------------------------

def test_generate_race_returns_501(client: FlaskClient) -> None:
    r = client.post("/generate/race", json={"flag_string": "AAAAAAAA"})
    assert r.status_code == 501
    assert r.get_json()["error"] == "not_implemented"
