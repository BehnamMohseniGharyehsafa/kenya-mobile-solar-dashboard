"""Persistent Dash workspace, embedded locally or served directly in the cloud."""
import atexit
import hashlib
import json
import threading
import time
import uuid
from urllib.parse import parse_qs,urlparse

from dash import Dash,Input,Output,State,ALL,ctx,no_update,dcc,html,set_props,ClientsideFunction
from flask import request,has_request_context,g
from werkzeug.serving import make_server,WSGIRequestHandler

from .config import Config
from .field_view import FieldView,interaction_settings
from .scene import CAMERAS,camera_pose
from .presentation import index_template
from .equipment import cooling_rpm
from .branding import developer_banner


class QuietHandler(WSGIRequestHandler):
    def log_request(self,*args,**kwargs):
        pass


class ViewerService:
    def __init__(self, *, start_server=True, default_design=None,
                 title="Kenya · interactive container", max_sessions=12, idle_seconds=1800,flask_server=None):
        self.default_design=default_design
        self.title=title
        self.max_sessions=max_sessions
        self.idle_seconds=idle_seconds
        self.routes={}
        self.keys={}
        self.sessions={}
        self.owners={}
        self.lock=threading.Lock()
        self.app=Dash(__name__,title=title,update_title=None,
            suppress_callback_exceptions=True,server=flask_server if flask_server is not None else True)
        self.app.index_string=index_template()
        self.app.layout=self._layout
        self._callbacks()
        self.server=self.thread=None
        self.port=None
        if start_server:
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
        # Dash also evaluates callable layouts during index/asset validation.
        # Only the browser's layout request should allocate a VTK scene.
        if not has_request_context() or request.path!="/_dash-layout":
            return html.Div()
        token=request.args.get("design")
        if not token:
            token=parse_qs(urlparse(request.referrer or "").query).get("design",[None])[0]
        with self.lock:
            settings=self.routes.get(token) if token else self.default_design
            if settings is None:
                return html.P("Open the Container simulator from the main dashboard.")
            # Bound retained sessions and release abandoned VTK resources.
            expired=[k for k,v in self.sessions.items() if time.monotonic()-v.last_used>self.idle_seconds]
            for key in expired:
                view=self.sessions[key]
                gate=getattr(view,"request_gate",None)
                if gate is not None and not gate.acquire(blocking=False):
                    continue
                try:
                    self.sessions.pop(key).close()
                    self.owners.pop(key,None)
                finally:
                    if gate is not None:
                        gate.release()
            owner=getattr(g,"viewer_owner",None) if self.default_design else None
            if owner is not None:
                existing=next((k for k in self.sessions if self.owners.get(k)==owner),None)
                if existing:
                    view=self.sessions[existing]
                    if hasattr(view,"sent_values"):
                        # A refresh reuses the browser's scene, but its fresh
                        # DOM needs the initial telemetry and chart again.
                        with view.lock:
                            view.sent_values.clear()
                            view.last_physics=view.last_chart=float("-inf")
                            return view.layout(existing)
                    return view.layout(existing)
            if self.default_design and len(self.sessions)>=self.max_sessions:
                return html.Div([developer_banner(),html.H2(self.title),html.P(
                    "The free demonstration server is currently full. Close unused simulation tabs "
                    "and try refreshing in a few minutes.")],className="viewer-shell")
            while len(self.sessions)>=self.max_sessions:
                key=min(self.sessions,key=lambda k:self.sessions[k].last_used)
                self.sessions.pop(key).close()
            session=uuid.uuid4().hex
            view=FieldView(*settings)
            if self.default_design:
                view.public_title=self.title
                view.public_demo=True
                view.request_gate=threading.BoundedSemaphore(1)
            self.sessions[session]=view
            if owner is not None:
                self.owners[session]=owner
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
            Input("hmi-start","n_clicks"),Input("hmi-hold","n_clicks"),Input("hmi-stop","n_clicks"),Input("vtk","clickInfo"),
            State("session","data"),
            running=[(Output("tick","disabled"),True,False)])
        def update(tick,deploy,retract,hold,refresh,clock,manual,speed,duration,options,detail,hmi_start,hmi_hold,hmi_stop,pick,session):
            view=self.sessions.get(session)
            if view is None:
                return (no_update,)*17
            event={"hmi-start":"panel-start","hmi-hold":"panel-hold","hmi-stop":"panel-stop"}.get(ctx.triggered_id,ctx.triggered_id or "tick")
            if event=="vtk":
                event=view.pick_action(pick)
                if event=="inspect":
                    set_props("equipment-inspector",{"open":True})
            if hasattr(view,"step_with_instruments"):
                result,changes=view.step_with_instruments(event,clock,manual,speed,duration,options,detail)
            else:
                result,changes=view.step(event,clock,manual,speed,duration,options,detail),{}
            scene,*values=result
            for identity,props in changes.items():
                set_props(identity,props)
            return scene.points,scene.actors,scene.render,*values,view.interval_ms

        self.app.clientside_callback(ClientsideFunction(namespace="pv_fan",function_name="configure"),
            Output("fan-runtime","data"),Input("fan-command","data"),State("session","data"))

        @self.app.callback(Output("camera","value"),Output("equipment-inspector","open"),
            Input("inspect-equipment","n_clicks"),prevent_initial_call=True)
        def inspect_equipment(clicks):
            return "Control panel & fan",True

        @self.app.callback(Output("clock","value"),Input("tour","n_clicks"),Input("live","n_clicks"),prevent_initial_call=True)
        def change_clock(tour,live):
            return "Accelerated solar day" if ctx.triggered_id=="tour" else "Live site clock"

        @self.app.callback(Output("camera-bounds","actor"),Output("vtk","cameraPosition"),Output("vtk","triggerResetCamera"),
            Input("camera","value"),Input("reset-view","n_clicks"),State("session","data"),prevent_initial_call=True)
        def camera(name,clicks,session):
            view=self.sessions.get(session)
            if view is None:
                return no_update,no_update,no_update
            return view.camera_bounds_actor(name),list(camera_pose(view.config,name)[0]),time.time()

        @self.app.callback(Output("vtk","interactorSettings"),Input("tool","value"))
        def interaction(tool):
            return interaction_settings(tool)

        @self.app.callback(Output("download","data"),Input("export","n_clicks"),Input("export-png","n_clicks"),
            State("session","data"),State("export-size","value"),State("camera","value"),
            State("fan-rotor","actor"),prevent_initial_call=True)
        def export(clicks,png_clicks,session,size,camera,rotor):
            view=self.sessions.get(session)
            if view is None:
                return no_update
            with view.lock:
                if ctx.triggered_id=="export-png":
                    sizes={"1080p":(1920,1080),"1440p":(2560,1440),"4K":(3840,2160)}
                    view.scene.set_camera(camera if camera in CAMERAS else "Site overview")
                    matrix=(rotor or {}).get("userMatrix")
                    orientation=(rotor or {}).get("orientation")
                    origin=(rotor or {}).get("origin")
                    if isinstance(orientation,list) and len(orientation)==3 and isinstance(origin,list) and len(origin)==3:
                        import numpy as np
                        if np.isfinite(orientation).all() and np.isfinite(origin).all():
                            view.scene.fan_actor.origin=origin
                            view.scene.fan_actor.orientation=orientation
                    elif isinstance(matrix,list) and len(matrix)==16:
                        import numpy as np
                        pose=np.asarray(matrix,dtype=float).reshape(4,4,order="F")
                        if np.isfinite(pose).all():
                            view.scene.fan_actor.user_matrix=pose
                    resolution=sizes["1080p"] if getattr(view,"public_demo",False) else sizes.get(size,sizes["1440p"])
                    return dcc.send_bytes(view.scene.png(resolution).getvalue(),"container_scene.png")
                snapshot=view.controller.snapshot()
                snapshot["instrumentation"]={"fan_demand_rpm_assumed":cooling_rpm(view.controller.model),
                    "visual_rotor_rpm":12,"fan_basis":"Delivered HVAC power and cooling mode; not a measured or OEM fan curve",
                    "physical_button_actions":{"green":"Start; reset only when stop is latched",
                        "yellow":"Hold / resume mechanism","red":"Latched stop; isolate PV, retain automatic cooling"}}
                return dcc.send_string(json.dumps(snapshot,indent=2,default=str),"container_snapshot.json")

    def close(self):
        if self.thread is not None and self.thread.is_alive():
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
        for view in self.sessions.values():
            view.close()
        self.sessions.clear()
        self.owners.clear()
