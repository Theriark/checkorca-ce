"""Security headers on every response (rnd-report-2 5.9).

The policy allows scripts only from the site itself, never inline. Inline
styles stay allowed because the UI libraries of phase C2 (Radix) inject style
elements; they cannot run code.
"""

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("content-security-policy", CONTENT_SECURITY_POLICY),
    ("x-frame-options", "DENY"),
    ("referrer-policy", "no-referrer"),
    ("x-content-type-options", "nosniff"),
)
