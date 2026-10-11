"""Profile B host: paypal. The only service holding real PayPal sandbox credentials.
See _mount.py for caveats."""

from hosts._mount import build_host

app = build_host({"/paypal-adapter": "paypal-adapter"})
