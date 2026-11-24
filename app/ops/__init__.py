"""Operations of the running server (phase C10): the retention purge
(retention.py), the Prometheus metrics (metrics.py) and the external
heartbeat watcher (heartbeat.py).

Every module is a worker tick hook or an endpoint outside /api/v1 (/metrics
is the one HTTP route); the /api/v1 contract is untouched.
"""
