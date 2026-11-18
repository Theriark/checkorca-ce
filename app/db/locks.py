"""PostgreSQL advisory lock keys, kept in one place so no two features share one.

4_270_001 is the migration lock (migrations/env.py); 4_270_9xx belong to the
spikes in tests/spikes.
"""

# Held while the first-run page or the development seed creates users, so two
# requests (or a request and the seed) never both find an empty user table.
USER_BOOTSTRAP_LOCK = 4_270_002
