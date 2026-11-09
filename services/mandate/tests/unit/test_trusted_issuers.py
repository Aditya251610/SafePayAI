"""Which service-token issuers mandate accepts (the signing key still has to verify)."""

from __future__ import annotations

from app_mandate.deps import TRUSTED_ISSUERS


def test_every_caller_that_mints_its_own_token_is_trusted() -> None:
    # gateway (sole minter), checkout (reservations), shopping-agent (summary read),
    # resolution (terms read when it opens a case).
    assert {
        "api-gateway",
        "checkout",
        "shopping-agent",
        "resolution",
    } <= TRUSTED_ISSUERS


def test_unknown_issuers_stay_untrusted() -> None:
    assert "tracking" not in TRUSTED_ISSUERS
    assert "attacker" not in TRUSTED_ISSUERS
