"""Pure chain logic: canonicalization, hashing, append, verify.

Per spec.md sec 16's module layout ("app/chain/{canonical,hashing,append,verify}.py
(pure, no I/O in canonical/hashing)"). `canonical.py` and `hashing.py` take plain Python
values in, bytes/str out -- no DB, no network. `append.py` and `verify.py` do the I/O.
"""

from __future__ import annotations
