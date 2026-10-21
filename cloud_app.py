"""Single-process public 3D workspace; run with the included Gunicorn config.

The public service serves the existing Dash workspace directly. It does not
need Streamlit, a reverse proxy, external asset CDNs, or a second public port.
"""
import os

from flask import Flask,jsonify

from solar_model.config import Config
from solar_model.viewer_service import ViewerService
from solar_model.cloud_security import CloudGuard


def create_app():
    app=Flask(__name__)
    # Run admission/ownership checks before Dash's first-request layout setup.
    # A direct layout request must not allocate an unowned validation scene.
    @app.before_request
    def admit_request():
        return app.extensions["cloud_guard"].before()

    service=ViewerService(start_server=False,
        default_design=(Config(),"Africa/Nairobi"),title="BehnamProject-PVforAfrica",
        max_sessions=max(1,min(2,int(os.environ.get("PV_MAX_SESSIONS","2")))),idle_seconds=180,flask_server=app)
    app.config.update(DEBUG=False,TESTING=False,MAX_CONTENT_LENGTH=64*1024,
        MAX_FORM_MEMORY_SIZE=1024,MAX_FORM_PARTS=4,
        TRUSTED_HOSTS=[os.environ.get("RENDER_EXTERNAL_HOSTNAME","behnamproject-pvforafrica.onrender.com"),
            "localhost","127.0.0.1"])
    guard=CloudGuard(service)
    app.extensions["cloud_guard"]=guard
    app.after_request(guard.after)
    app.teardown_request(guard.release)
    csp="; ".join(["default-src 'self'","script-src 'self' "+" ".join(service.app.csp_hashes()),
        "style-src 'self' 'unsafe-inline'","img-src 'self' data: blob:","font-src 'self' data:",
        "connect-src 'self'","worker-src 'self' blob:","object-src 'none'","base-uri 'none'",
        "frame-ancestors 'none'","form-action 'self'"])
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
        response.headers["X-Frame-Options"]="DENY"
        response.headers["Content-Security-Policy"]=csp
        response.headers["Permissions-Policy"]="camera=(), microphone=(), geolocation=(), payment=()"
        if request_host_is_public():
            response.headers["Strict-Transport-Security"]="max-age=31536000"
        if not response.cache_control.max_age:
            response.headers["Cache-Control"]="no-store"
        return response

    return app


def request_host_is_public():
    from flask import request
    # Do not read request.host again while formatting an invalid-Host response.
    return request.environ.get("HTTP_HOST","").split(":",1)[0] not in {"localhost","127.0.0.1"}
