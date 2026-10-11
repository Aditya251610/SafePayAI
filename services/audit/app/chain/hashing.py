"""Row-hash function (spec.md sec 4).

`row_hash = hex(SHA256( b"safepayai.audit.v1\\n" + prev_hash_hex_ascii + b"\\n" +
canonical_utf8 ))`. The domain prefix prevents cross-use of hashes from another system;
the `v1` in the prefix (not the content object's `"v": 1` field) is the hash-algorithm
version a verifier dispatches on (spec.md sec 4).

Must stay byte-identical to `migrations/versions/0001_baseline.py`'s `_row_hash` (which
seeds the genesis row at migration time, before this module exists in the running
service) -- see that migration's docstring and `tests/unit/test_canonical_hashing.py`.
"""

from __future__ import annotations

import hashlib

HASH_DOMAIN = b"safepayai.audit.v1\n"
GENESIS_PREV_HASH = "0" * 64
ALGORITHM_LABEL = "sha256/v1"


def row_hash(prev_hash: str, canonical: bytes) -> str:
    if len(prev_hash) != 64:
        raise ValueError(f"prev_hash must be 64 hex chars, got {len(prev_hash)}")
    return hashlib.sha256(HASH_DOMAIN + prev_hash.encode("ascii") + b"\n" + canonical).hexdigest()
