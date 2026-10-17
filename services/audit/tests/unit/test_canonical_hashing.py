"""L1 tests for app/chain/canonical.py and app/chain/hashing.py (spec.md sec 4).

Includes a cross-check against migrations/versions/0001_baseline.py's own minimal
`_jcs_bytes`/`_row_hash` helpers for the genesis content object, so the general
canonicalizer introduced in Wave 5 cannot silently drift from the hash the migration
already committed to the database (spec.md sec 4 "byte-identical output... in writer,
verifier, and any third-party re-implementation"; prd.md risk R5).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import UTC
from pathlib import Path

import pytest

from app_audit.chain.canonical import CanonicalizationError, canonicalize
from app_audit.chain.content import build_content, format_ts
from app_audit.chain.hashing import GENESIS_PREV_HASH, HASH_DOMAIN, row_hash

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0001_baseline.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("audit_migration_0001", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class TestRowHashGoldenVector:
    def test_known_vector(self) -> None:
        """Golden vector: fixed prev_hash + fixed canonical bytes -> fixed SHA-256 digest,
        computed independently here via hashlib so this test is self-verifying."""
        prev = "0" * 64
        canonical = b'{"a":1,"b":"x"}'
        expected = hashlib.sha256(
            HASH_DOMAIN + prev.encode("ascii") + b"\n" + canonical
        ).hexdigest()
        assert row_hash(prev, canonical) == expected
        assert len(expected) == 64

    def test_rejects_short_prev_hash(self) -> None:
        with pytest.raises(ValueError):
            row_hash("abc", b"{}")

    def test_domain_prefix_is_stable(self) -> None:
        # This string is committed in both the migration and this module; a change here
        # without a matching migration change would silently break every past hash.
        assert HASH_DOMAIN == b"safepayai.audit.v1\n"
        assert GENESIS_PREV_HASH == "0" * 64


class TestCanonicalization:
    def test_sorts_keys(self) -> None:
        out = canonicalize({"b": 1, "a": 2})
        assert out == b'{"a":2,"b":1}'

    def test_omits_none_values(self) -> None:
        out = canonicalize({"a": 1, "b": None})
        assert out == b'{"a":1}'

    def test_no_whitespace(self) -> None:
        out = canonicalize({"a": [1, 2, {"c": 3}]})
        assert b" " not in out

    def test_rejects_floats(self) -> None:
        with pytest.raises(CanonicalizationError):
            canonicalize({"amount": 10.5})

    def test_nfc_normalizes_strings(self) -> None:
        # "e" + combining acute (NFD) must canonicalize the same as the precomposed "é" (NFC).
        nfd = "é"
        nfc = "é"
        assert canonicalize({"s": nfd}) == canonicalize({"s": nfc})

    def test_rejects_lone_surrogate(self) -> None:
        with pytest.raises(CanonicalizationError):
            canonicalize({"s": "\ud800"})

    def test_nested_object_keys_sorted_independently(self) -> None:
        out = canonicalize({"outer": {"z": 1, "a": 2}, "a_top": 1})
        assert out == b'{"a_top":1,"outer":{"a":2,"z":1}}'


class TestContentObjectShape:
    def test_format_ts_six_fractional_digits_and_z(self) -> None:
        from datetime import datetime

        dt = datetime(2026, 10, 20, 14, 3, 11, 120345, tzinfo=UTC)
        assert format_ts(dt) == "2026-10-20T14:03:11.120345Z"

    def test_build_content_omits_absent_optional_actor_and_refs_keys(self) -> None:
        from datetime import datetime

        now = datetime(2026, 1, 1, tzinfo=UTC)
        content = build_content(
            chain_id="ps-demo-1",
            event_id="e1",
            event_type="ORDER_CAPTURED",
            event_version=1,
            producer="checkout",
            occurred_at=now,
            recorded_at=now,
            actor={"type": "buyer", "id": "buyer_1", "auth_method": "session+csrf"},
            request_id="r1",
            trace_id="t1",
            refs={"buyer_id": "buyer_1", "mandate_id": None, "order_id": "ord_1", "case_id": None},
            payload={"total": 100},
        )
        assert "session_id_hash" not in content["actor"]
        assert content["refs"] == {"buyer_id": "buyer_1", "order_id": "ord_1"}

        canonical = canonicalize(content)
        parsed = json.loads(canonical)
        assert "session_id_hash" not in parsed["actor"]
        assert "mandate_id" not in parsed["refs"]
        assert "case_id" not in parsed["refs"]


class TestCrossCheckWithMigrationGenesisHash:
    """Both implementations must agree on the genesis content object's hash, otherwise
    the service's own general verify() would reject the migration-seeded genesis row."""

    def test_general_canonicalizer_matches_migration_minimal_one(self) -> None:
        migration = _load_migration_module()

        chain_id = "ps-demo-1"
        event_id = "00000000-0000-0000-0000-000000000000"
        occurred_at = "2026-10-20T14:03:11.120345Z"
        genesis_payload = {"note": "genesis", "created_by": "migration"}

        migration_content = {
            "v": 1,
            "chain_id": chain_id,
            "event_id": event_id,
            "event_type": "CHAIN_GENESIS",
            "event_version": 1,
            "producer": "migration",
            "occurred_at": occurred_at,
            "recorded_at": occurred_at,
            "actor": {"type": "system", "id": "migration", "auth_method": "none"},
            "request_id": "genesis",
            "trace_id": "genesis",
            "refs": {},
            "payload": genesis_payload,
        }
        migration_canonical = migration._jcs_bytes(migration_content)
        migration_hash = migration._row_hash(migration.GENESIS_PREV_HASH, migration_canonical)

        app_canonical = canonicalize(migration_content)
        app_hash = row_hash(GENESIS_PREV_HASH, app_canonical)

        assert app_canonical == migration_canonical
        assert app_hash == migration_hash
