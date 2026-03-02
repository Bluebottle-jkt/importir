# gunicorn.conf.py — SR15 Analytics production WSGI config
# Run: gunicorn app:server -c gunicorn.conf.py

bind              = "0.0.0.0:8050"
workers           = 6          # Rule of thumb: 2 × cores + 1 (Core Ultra 9 = ~16P+8E)
threads           = 4          # gthread: each worker runs N threads
worker_class      = "gthread"  # Thread-based; safe for Dash callbacks
timeout           = 180        # Long-running pareto/export won't timeout
keepalive         = 5
preload_app       = True       # Load app once in master → fork to workers (saves ~RAM)
                               # Tradeoff: code changes need restart; large initial load
max_requests      = 2000       # Recycle worker after N requests (prevent memory leak)
max_requests_jitter = 200      # Random offset so workers don't restart simultaneously
accesslog         = "-"        # stdout
errorlog          = "-"        # stderr
loglevel          = "info"
