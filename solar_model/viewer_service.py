"""Automatically managed, loopback-only Dash VTK service for local Streamlit."""
import atexit
import hashlib
import json
import threading
import time
import uuid
from urllib.parse import parse_qs,urlparse

from dash import Dash,Input,Output,State,ALL,ctx,no_update,dcc,html
from flask import request,has_request_context
from werkzeug.serving import make_server,WSGIRequestHandler

from .config import Config
from .field_view import FieldView,interaction_settings
from .scene import CAMERAS
from .presentation import index_template


class QuietHandler(WSGIRequestHandler):
    def log_request(self,*args,**kwargs):
        pass


class ViewerService:
    def __init__(self):
        self.routes={}
        self.keys={}
        self.sessions={}
        self.lock=threading.Lock()
        self.app=Dash(__name__,title="Kenya · interactive container",update_title=None,
            suppress_callback_exceptions=True)
        self.app.index_string=index_template()
        self.app.layout=self._layout
        self._callbacks()
        self.server=make_server("127.0.0.1",0,self.app.server,threaded=True,request_handler=QuietHandler)
        self.port=self.server.server_port
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True,name="field-viewer")
        self.thread.start()
        atexit.register(self.close)

    def register(self,config,operator_zone):
        key=hashlib.sha256(json.dumps([config.to_dict(),operator_zone],sort_keys=True).encode()).hexdigest()
        with self.lock:
            if key not in self.keys:
                self.keys[key]=uuid.uuid4().hex
                self.routes[self.keys[key]]=(config,operator_zone)
            token=self.keys[key]
        return f"http://127.0.0.1:{self.port}/?design={token}"

    def _layout(self):
        if not has_request_context():
            return html.Div()
        token=request.args.get("design")
        if not token:
            token=parse_qs(urlparse(request.referrer or "").query).get("design",[None])[0]
        with self.lock:
            settings=self.routes.get(token)
            if settings is None:
                return html.P("Open the Container simulator from the main dashboard.")
            # Bound retained sessions and release abandoned VTK resources.
            expired=[k for k,v in self.sessions.items() if time.monotonic()-v.last_used>1800]
            for key in expired:
                self.sessions.pop(key).close()
            while len(self.sessions)>=12:
                key=min(self.sessions,key=lambda k:self.sessions[k].last_used)
                self.sessions.pop(key).close()
            session=uuid.uuid4().hex
            view=FieldView(*settings)
            self.sessions[session]=view
        return view.layout(session)

    def _callbacks(self):
        @self.app.callback(
            Output({"type":"moving-mesh","slot":ALL},"points"),
            Output({"type":"moving-actor","slot":ALL},"actor"),Output("vtk","triggerRender"),
            Output("status","children"),Output("progress","value"),
            Output("clocks","children"),Output("metrics","children"),Output("weather","children"),
            Output("technical","children"),Output("roof-state","children"),Output("plot","figure"),
            Output("deploy","disabled"),Output("retract","disabled"),Output("hold","disabled"),Output("hold","children"),
            Output("vtk","background"),
            Output("tick","interval"),
            Input("tick","n_intervals"),Input("deploy","n_clicks"),Input("retract","n_clicks"),
            Input("hold","n_clicks"),Input("refresh","n_clicks"),Input("clock","value"),Input("manual","value"),
            Input("speed","value"),Input("duration","value"),Input("options","value"),Input("detail-tab","value"),
            State("session","data"),
            running=[(Output("tick","disabled"),True,False)])
        def update(tick,deploy,retract,hold,refresh,clock,manual,speed,duration,options,detail,session):
            view=self.sessions.get(session)
            if view is None:
                return (no_update,)*17
            scene,*values=view.step(ctx.triggered_id or "tick",clock,manual,speed,duration,options,detail)
            return scene.points,scene.actors,scene.render,*values,view.interval_ms

        @self.app.callback(Output("clock","value"),Input("tour","n_clicks"),Input("live","n_clicks"),prevent_initial_call=True)
        def change_clock(tour,live):
            return "Accelerated solar day" if ctx.triggered_id=="tour" else "Live site clock"

        @self.app.callback(Output("vtk","cameraPosition"),Output("vtk","triggerResetCamera"),
            Input("camera","value"),Input("reset-view","n_clicks"),prevent_initial_call=True)
        def camera(name,clicks):
            return list(CAMERAS[name][0]),time.time()

        @self.app.callback(Output("vtk","interactorSettings"),Input("tool","value"))
        def interaction(tool):
            return interaction_settings(tool)

        @self.app.callback(Output("download","data"),Input("export","n_clicks"),Input("export-png","n_clicks"),
            State("session","data"),State("export-size","value"),State("camera","value"),prevent_initial_call=True)
        def export(clicks,png_clicks,session,size,camera):
            view=self.sessions.get(session)
            if view is None:
                return no_update
            with view.lock:
                if ctx.triggered_id=="export-png":
                    sizes={"1080p":(1920,1080),"1440p":(2560,1440),"4K":(3840,2160)}
                    view.scene.set_camera(camera if camera in CAMERAS else "Site overview")
                    return dcc.send_bytes(view.scene.png(sizes.get(size,sizes["1440p"])).getvalue(),"container_scene.png")
                return dcc.send_string(json.dumps(view.controller.snapshot(),indent=2,default=str),"container_snapshot.json")

    def close(self):
        if self.thread.is_alive():
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
            for view in self.sessions.values():
                view.close()
            self.sessions.clear()
