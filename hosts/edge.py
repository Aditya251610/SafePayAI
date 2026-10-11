"""Profile B host: edge. Public-facing, terminates buyer sessions. See _mount.py for caveats."""

from hosts._mount import build_host

app = build_host({"/gateway": "api-gateway"})
