"""Single-process public 3D workspace; run with the included Gunicorn config.

The public service serves the existing Dash workspace directly. It does not
need Streamlit, a reverse proxy, external asset CDNs, or a second public port.
"""
import os

from flask import jsonify

from solar_model.config import Config
from solar_model.viewer_service import ViewerService


def create_app():
    service=ViewerService(start_server=False,
        default_design=(Config(),"Africa/Nairobi"),title="BehnamProject-PVforAfrica",
        max_sessions=int(os.environ.get("PV_MAX_SESSIONS","2")),idle_seconds=180)
    app=service.app.server
    # Keep the controller alive for the process lifetime. A single threaded
    # worker keeps each browser's in-memory state on the same Python process.
    app.extensions["field_viewer"]=service

    @app.get("/healthz")
    def health():
        return jsonify(status="ok",project="BehnamProject-PVforAfrica",
            revision=os.environ.get("PV_UI_REVISION","base"))

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="same-origin"
        if not response.cache_control.max_age:
            response.headers["Cache-Control"]="no-store"
        return response

    return app
