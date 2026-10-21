"""One shared process for Dash callbacks, with bounded concurrent HTTP threads."""
import os

bind=f"0.0.0.0:{int(os.environ.get('PORT','10000'))}"
workers=1
worker_class="gthread"
threads=4
timeout=120
graceful_timeout=30
accesslog=None
errorlog="-"
limit_request_line=4094
limit_request_fields=40
limit_request_field_size=8190
backlog=64
keepalive=2
# VTK builds scenes on demand; preloading would fork an initialized runtime.
preload_app=False
