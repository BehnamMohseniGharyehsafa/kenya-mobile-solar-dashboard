"""Persistent Dash VTK workspace, authored entirely in Python.

Coordinates are written directly to PolyData buffers. Updating View.children
would make every representation redraw the whole scene, including the terrain.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
import json
import threading
import time

import numpy as np
import pandas as pd
from dash import html, dcc, no_update
import dash_vtk
from dash_vtk.utils import to_mesh_state
from dash_vtk.utils.vtk import b64_encode_numpy
import plotly.graph_objects as go

from .field_controller import FieldController
from .interactive_scene import InteractiveScene
from .live_weather import load_feed, weather_label
from .mechanics import phase, hatch_angle, layout
from .scene import CAMERAS
from . import charts
from .equipment import inspector,cooling_rpm,display_colors,display_lines,fan_centre
from .branding import developer_banner

WEATHER_POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix="site-weather")
BUTTON={"background":"#203841","color":"#edf2ed","border":"1px solid #456169",
    "borderRadius":"7px","padding":"10px 14px","cursor":"pointer","fontSize":"12px"}
ROW={"display":"flex","flexWrap":"wrap","gap":"8px","alignItems":"center","marginBottom":"10px"}


@dataclass
class SceneUpdate:
    children: object
    points: list
    actors: list
    render: object

    def to_dict(self):
        return asdict(self)


def interaction_settings(tool="Orbit"):
    return [{"button":1,"action":{"Orbit":"Rotate","Pan":"Pan","Zoom":"Zoom"}[tool]},
        {"button":2,"action":"Pan"},{"button":3,"action":"Zoom","scrollEnabled":True},
        {"button":1,"shift":True,"action":"Pan"},{"button":1,"alt":True,"action":"Zoom"},
        {"button":1,"control":True,"action":"ZoomToMouse"}]


def actor_state(actor):
    matrix=actor.GetMatrix()
    state={"userMatrix":[matrix.GetElement(i,j) for j in range(4) for i in range(4)],
        "visibility":bool(actor.GetVisibility()),"useBounds":False}
    if not actor.GetPickable():
        state["pickable"]=False
    return state


class FieldView:
    def __init__(self, config, operator_zone="Europe/Dublin", feed=None):
        self.config=config
        self.operator_zone=operator_zone
        self.controller=FieldController(config)
        self.scene=InteractiveScene(config)
        self.lock=threading.Lock()
        self.last_fetch=time.monotonic()
        self.last_physics=self.last_chart=-np.inf
        self.last_used=time.monotonic()
        self.frame_ms=0.
        self.future=None
        self.closed=False
        self.render_options=(True,False)
        self.sent_values={}
        self.instrument_changes={}
        self.default_camera_bounds=tuple(self.scene.plotter.bounds)
        self._index_actors()
        if feed is not None:
            self.controller.set_feed(*feed)
        else:
            self.fetch_weather()
        self.controller.step_plant(pd.Timestamp.now(tz="UTC"))

    def _index_actors(self):
        self.actors=list(self.scene.plotter.renderer.actors.values())
        dynamic=self.scene.modules+self.scene.posts+self.scene.feet+self.scene.hatches+self.scene.rails+[self.scene.sun]
        self.dynamic_indices=[i for i,a in enumerate(self.actors) if any(a is b for b in dynamic)]
        self.shadow_indices=[i for i,a in enumerate(self.actors)
            if a is self.scene.shadow_actor or a is self.scene.box_shadow_actor]
        self.stream_indices=sorted(self.dynamic_indices+self.shadow_indices)
        self.stream_slots={index:slot for slot,index in enumerate(self.stream_indices)}
        self.option_indices=[i for i,a in enumerate(self.actors) if any(a is b for b in self.scene.option_actors)]
        # ALL outputs follow document order, which is also renderer actor order.
        self.actor_indices=sorted(self.stream_indices+self.option_indices)
        self.actor_slots={index:slot for slot,index in enumerate(self.actor_indices)}
        self.actor_states={i:actor_state(self.actors[i]) for i in self.actor_indices}
        self.mesh_mtimes={i:self.actors[i].mapper.dataset.GetMTime() for i in self.dynamic_indices+self.shadow_indices}

    def fetch_weather(self, force=False):
        if self.future is None or self.future.done():
            self.last_fetch=time.monotonic()
            self.future=WEATHER_POOL.submit(load_feed,self.config,force=force)

    def representations(self):
        result=[]
        for i,actor in enumerate(self.actors):
            mesh=actor.mapper.dataset
            field=mesh.active_scalars_name if actor.mapper.scalar_visibility else None
            mapper={"scalarVisibility":bool(field),"colorMode":2}
            if field:
                mapper.update(colorByArrayName=field,scalarMode=4 if field in mesh.cell_data else 3)
            prop=actor.GetProperty()
            slot=self.stream_slots.get(i)
            actor_slot=self.actor_slots.get(i)
            identity=f"part-{i}" if actor_slot is None else {"type":"moving-actor","slot":actor_slot}
            for key,button_actor in self.scene.button_actors.items():
                if actor is button_actor:
                    identity=f"world-{key}"
                    # Buttons have dedicated IDs for picking and get their
                    # occasional depression update through set_props.
            if actor is self.scene.fan_actor:
                identity="fan-rotor"
            elif actor is self.scene.display_actor:
                identity="world-hmi"
            elif field=="equipment_rgb":
                identity="world-panel"
            mesh_id=f"mesh-{i}" if slot is None else {"type":"moving-mesh","slot":slot}
            state=to_mesh_state(mesh,field)
            arrays={"PointData":[],"CellData":[]}
            if state.get("field"):
                data=dict(state["field"])
                location=data.pop("location")
                # dataRange is encoder metadata rather than a DataArray property.
                data.pop("dataRange",None)
                arrays[location].append(dash_vtk.DataArray(**data,
                    **({"id":"hmi-segments"} if actor is self.scene.display_actor else {})))
            # VTK's browser bridge does not export surface normals by default.
            # Preserve them for static smooth surfaces, once at initial load.
            # Moving meshes intentionally omit them because their vertices move.
            normals=mesh.GetPointData().GetNormals()
            if slot is None and normals is not None:
                from vtkmodules.util.numpy_support import vtk_to_numpy
                arrays["PointData"].append(dash_vtk.DataArray(name="Normals",registration="setNormals",
                    numberOfComponents=3,type="Float32Array",
                    values=b64_encode_numpy(vtk_to_numpy(normals).astype(np.float32,copy=False))))
            fields=[getattr(dash_vtk,location)(children) for location,children in arrays.items() if children]
            result.append(dash_vtk.GeometryRepresentation(id=identity,actor=actor_state(actor),mapper=mapper,
                property={"color":list(prop.GetColor()),"opacity":prop.GetOpacity(),
                    "ambient":prop.GetAmbient(),"diffuse":prop.GetDiffuse(),
                    "specular":prop.GetSpecular(),"specularPower":prop.GetSpecularPower(),
                    "interpolation":prop.GetInterpolation(),"lineWidth":prop.GetLineWidth(),
                    "lighting":bool(prop.GetLighting())},
                children=[dash_vtk.PolyData(id=mesh_id,**state["mesh"],children=fields)]))
        import pyvista as pv
        bounds=to_mesh_state(pv.Cube())
        result.append(dash_vtk.GeometryRepresentation(id="camera-bounds",actor=self.camera_bounds_actor("Site overview"),
            property={"opacity":0},children=[dash_vtk.PolyData(**bounds["mesh"])]))
        return result

    def camera_bounds_actor(self,name):
        x=self.config.dimensions[0]/2
        bounds=(x-.7,x+1.2,-1.13,1.2,.62,2.6) if name=="Control panel & fan" else self.default_camera_bounds
        x0,x1,y0,y1,z0,z1=bounds
        return {"useBounds":True,"visibility":True,"pickable":False,"userMatrix":[
            x1-x0,0,0,0,0,y1-y0,0,0,0,0,z1-z0,0,(x1+x0)/2,(y1+y0)/2,(z1+z0)/2,1]}

    @staticmethod
    def pick_action(info):
        info=info or {}
        if not isinstance(info,dict) or not isinstance(info.get("representationId"),str):
            return "pick"
        # A generous, non-overlapping target around each small physical cap.
        # The readable HMI supplies full-size keyboard/touch controls as well.
        point=info.get("worldPosition")
        if info.get("representationId")=="world-panel" and isinstance(point,list) and len(point)==3:
            try:
                if abs(float(point[2])-1.37)<.10:
                    for key,y in (("start",.42),("hold",.65),("stop",.88)):
                        if abs(float(point[1])-y)<.10:
                            return "panel-"+key
            except (TypeError,ValueError):
                pass
        return {"world-start":"panel-start","world-hold":"panel-hold","world-stop":"panel-stop",
            "world-hmi":"inspect","world-panel":"inspect","fan-rotor":"inspect"}.get(info.get("representationId"),"pick")

    def layout(self, session):
        button=lambda name,identity:html.Button(name,id=identity,n_clicks=0,style=BUTTON,className="control")
        c=self.config
        # Seed the first mesh with real digits. A slow initial browser mount
        # must not lose an early asynchronous DataArray update and show dashes.
        m=self.controller.model
        self.scene.display_mesh.cell_data["screen_rgb"]=display_colors(display_lines(m,cooling_rpm(m)))
        coordinates=f"{abs(c.latitude):.4f}° {'N' if c.latitude>=0 else 'S'} · {abs(c.longitude):.4f}° {'E' if c.longitude>=0 else 'W'}"
        return html.Div([
            developer_banner(),
            dcc.Store(id="session",data=session),dcc.Interval(id="tick",interval=1000,n_intervals=0),
            dcc.Store(id="fan-command",data=self.fan_command(False)),
            dcc.Store(id="fan-runtime"),
            html.Div([html.Div([html.P("FIELD SYSTEM 01 / RENEWABLE ENERGY",className="eyebrow"),
                html.H2(getattr(self,"public_title",None) or ["Mobile solar",html.Span(" / field lab")])]),
                html.Div([html.Strong(f"{c.site.upper()} · KENYA"),html.Br(),coordinates],className="site-chip")],
                className="viewer-heading"),
            html.Div([button("Deploy · open roof & install PV","deploy"),button("Retract · pack & close container","retract"),
                button("Hold motion","hold"),button("Refresh weather","refresh")],className="command-row"),
            html.Div([html.Label("Camera preset"),dcc.Dropdown(id="camera",options=list(CAMERAS),value="Site overview",
                clearable=False,style={"width":"200px","color":"#142832"}),button("Reset view","reset-view"),
                button("Inspect HMI & fan","inspect-equipment"),
                button("Run solar-day tour","tour"),button("Use live site clock","live"),
                html.Div([html.Label("Drag tool"),dcc.RadioItems(id="tool",options=["Orbit","Pan","Zoom"],value="Orbit",inline=True,
                    labelStyle={"marginRight":"12px","color":"#e9f0f1"})],className="drag-tools")],className="view-toolbar"),
            html.P("Drag to explore · Wheel / right-drag to zoom · Shift + drag to pan",className="camera-help"),
            html.Div([html.Strong("TRANSPORT LOCKED",id="status"),html.Small(id="roof-state")],className="mechanism-status"),
            html.Progress(id="progress",value=0,max=100),
            html.Div([html.Div("3D SITE VIEW / "+c.site.upper(),className="scene-label"),
                dash_vtk.View(id="vtk",children=self.representations(),cameraPosition=list(CAMERAS["Site overview"][0]),
                cameraViewUp=[0,0,1],background=[.57,.67,.72],
                pickingModes=["click"],
                interactorSettings=interaction_settings(),
                style={"width":"100%","height":"100%"}),
                inspector(),
                html.Div(f"{c.array_kwp:.1f} kWp PV · {c.battery_kwh:g} kWh LFP · {c.container_ft} ft container",className="scene-note")],
                className="scene-frame"),
            dcc.Markdown(id="clocks"),html.Div(id="metrics"),dcc.Markdown(id="weather"),
            html.Details([html.Summary("Clock, animation and view settings"),
                html.Div([html.Label("Simulation clock"),dcc.Dropdown(id="clock",options=["Live site clock","Accelerated solar day","Manual sun study"],
                    value="Live site clock",clearable=False,style={"width":"245px","color":"#142832"}),
                    dcc.Input(id="manual",type="text",debounce=True,value=pd.Timestamp.now(tz=self.config.timezone).strftime("%Y-%m-%d 12:00"),
                        placeholder="Study time · YYYY-MM-DD HH:MM EAT",style={"padding":"10px"}),
                    html.Label("Tour speed"),dcc.Dropdown(id="speed",options=[60,120,300,600,1200],value=600,clearable=False,
                        style={"width":"110px","color":"#142832"})],style=ROW),
                html.Label("Deployment animation duration (seconds)"),dcc.Slider(id="duration",min=2,max=20,step=1,value=6,
                    marks={2:"2",6:"6",12:"12",20:"20"}),
                dcc.Checklist(id="options",options=[{"label":"Geometric sun shadows","value":"shadows"},
                    {"label":"Landscape and vegetation","value":"landscape"},{"label":"Container cutaway","value":"cutaway"}],
                    value=["shadows","landscape"]),
                html.P("Presentation duration is not a measured installation speed. Manual study time must lie within the downloaded weather window.")],className="settings"),
            dcc.Tabs(id="detail-tab",value="power",children=[
                dcc.Tab(label="Power & thermal state",value="power"),dcc.Tab(label="Mechanism & interlocks",value="mechanism"),
                dcc.Tab(label="Weather & solar geometry",value="weather"),dcc.Tab(label="Export & performance",value="export")],
                colors={"border":"#40545c","primary":"#f4b657","background":"#192832"}),
            dcc.Markdown(id="technical"),dcc.Graph(id="plot",config={"displaylogo":False},style={"height":"300px"}),
            html.Div([button("Export technical snapshot JSON","export"),button("Export scene PNG","export-png"),
                html.Label("Image resolution"),dcc.Dropdown(id="export-size",value="1080p" if getattr(self,"public_demo",False) else "1440p",clearable=False,
                    options=[{"label":"Full HD · 1920 × 1080","value":"1080p"}] if getattr(self,"public_demo",False) else [
                        {"label":"Full HD · 1920 × 1080","value":"1080p"},
                        {"label":"QHD · 2560 × 1440","value":"1440p"},{"label":"4K · 3840 × 2160","value":"4K"}],
                    style={"width":"220px","color":"#142832","fontSize":"12px"}),
                dcc.Download(id="download")],className="export-row"),
            html.P("KENYA / MOBILE SOLAR LAB · Simulated energy and mechanism states. Illustrative landscape; weather provenance and engineering assumptions remain available below the view.",
                className="viewer-footer"),
        ],className="viewer-shell")

    def step(self, event, mode, manual, speed, duration, options, detail):
        with self.lock:
            return self._step(event,mode,manual,speed,duration,options,detail)

    def step_with_instruments(self,*args):
        # Drain the LCD updates while holding the same per-session lock, so a
        # fast subsequent command cannot mix another command's panel state in.
        with self.lock:
            result=self._step(*args)
            return result,self.take_instrument_changes()

    @property
    def interval_ms(self):
        if self.controller.moving:
            return 50
        return 100 if self.controller.mode=="Accelerated solar day" else 1000

    def _if_changed(self,key,value):
        if value is no_update or self.sent_values.get(key)==value:
            return no_update
        self.sent_values[key]=value
        return value

    def _step(self,event,mode,manual,speed,duration,options,detail):
        started=time.perf_counter()
        now=pd.Timestamp.now(tz="UTC")
        mono=time.monotonic()
        self.last_used=mono
        c=self.controller
        # A tab, duration or view-tool change does not advance the plant or
        # rebuild its chart. Commands still update the PV/drive interlocks now.
        force=event in ("deploy","retract","hold","clock","manual","refresh","panel-start","panel-hold","panel-stop")
        render_options=("landscape" in options,"cutaway" in options)
        options_changed=render_options!=self.render_options
        if options_changed:
            self.scene.set_options(*render_options)
            self.render_options=render_options
        if self.future is not None and self.future.done():
            try:
                c.set_feed(*self.future.result())
            except (RuntimeError,ValueError,OSError) as exc:
                c.weather_error=str(exc)
            self.future=None
            force=True
        if mono-self.last_fetch>900 or event=="refresh":
            self.fetch_weather(event=="refresh")
        if mode!=c.mode:
            c.set_mode(mode,now)
            force=True
        if mode=="Manual sun study":
            try:
                selected=pd.Timestamp(manual)
                if pd.isna(selected) or not 2000<=selected.year<=2100:
                    raise ValueError("Study date is outside the supported calendar.")
                selected=selected.tz_localize(c.config.timezone)
                if selected!=c.manual:
                    c.manual=selected
                    c.reset_energy()
                    force=True
            except (ValueError,TypeError):
                c.notice="Invalid study time; enter YYYY-MM-DD HH:MM in Nairobi time."
        c.speed=speed
        c.duration=duration
        if event=="deploy":
            c.command(1)
        elif event=="retract":
            c.command(0)
        elif event=="hold":
            c.hold()
        elif event=="panel-start":
            c.start_or_reset()
        elif event=="panel-hold":
            c.hold()
        elif event=="panel-stop":
            c.emergency_stop()
        before=c.deployed
        c.step_motion()
        physics=force or mono-self.last_physics>=1 or before!=c.deployed
        if physics:
            c.step_plant(now)
            self.last_physics=mono
        m=c.model
        if physics:
            self.update_instruments()
        changed=self.scene.update(c.progress,m["tilt"],m["azimuth"],m["sun_elevation"],m["sun_azimuth"],
            c.weather["cloud_pct"] if c.weather else 0,"shadows" in options)
        points=[no_update]*len(self.stream_indices)
        actors=[no_update]*len(self.actor_indices)
        scene_children=no_update
        render=no_update
        if changed or options_changed:
            for slot,i in enumerate(self.actor_indices):
                actor=self.actors[i]
                state=actor_state(actor)
                if state!=self.actor_states[i]:
                    actors[slot]=state
                    self.actor_states[i]=state
            for slot,i in enumerate(self.stream_indices):
                actor=self.actors[i]
                mesh=actor.mapper.dataset
                if mesh.GetMTime()!=self.mesh_mtimes[i]:
                    points[slot]=b64_encode_numpy(mesh.points)
                    self.mesh_mtimes[i]=mesh.GetMTime()
            # PolyData coordinate writes do not recursively update the parent
            # representations. Request one render after all buffer writes.
            render=time.time()
        scene_update=SceneUpdate(scene_children,points,actors,render)
        telemetry=self.telemetry(detail) if physics or event=="detail-tab" else (no_update,)*5
        figure=no_update
        if event in ("detail-tab","clock","manual") or mono-self.last_chart>5:
            figure=self.figure(detail)
            self.last_chart=mono
        self.frame_ms=(time.perf_counter()-started)*1000
        status=f"{'E-STOP LATCHED' if c.emergency_stopped else 'RESTART REQUIRED' if c.restart_required else 'DEPLOYING' if c.target>c.progress else 'RETRACTING' if c.target<c.progress else 'READY'} · {phase(c.progress)} · {c.progress*100:.0f}% deployed"+(" · MOTION HELD" if c.held else "")
        values=(status,c.progress*100,*telemetry,figure,
            c.emergency_stopped or (c.target==1 and not c.held) or c.wind_block or c.weather is None or not c.packing_ok,
            c.emergency_stopped or (c.target==0 and not c.held),c.emergency_stopped or c.restart_required or (not c.moving and not c.held),"Resume motion" if c.held else "Hold motion",
            ([.08,.12,.17] if m["sun_elevation"]<=0 else [.57,.67,.72]) if physics else no_update)
        return (scene_update,*(v if i==7 else self._if_changed(f"output-{i}",v) for i,v in enumerate(values)))

    def update_instruments(self):
        c,m=self.controller,self.controller.model
        rpm=cooling_rpm(m)
        def value(key,decimals=1,multiplier=1):
            v=m.get(key)
            return f"{v*multiplier:.{decimals}f}" if v is not None else "—"
        state=m["state"] if c.emergency_stopped or c.restart_required else "MOTION HELD" if c.held else "DEPLOYING" if c.moving and c.target==1 else "RETRACTING" if c.moving else m["state"]
        targets={"hmi-state":{"children":state},"hmi-pv":{"children":value("pv_dc_kw",2)},
            "hmi-soc":{"children":value("soc",1,100)},"hmi-temp":{"children":value("battery_temp_c")},
            "hmi-load":{"children":value("user_served_kw",2)},
            "hmi-contactor":{"children":"PV CONTACTOR · "+("CLOSED" if c.pv_connected else "ISOLATED")},
            "hmi-notice":{"children":c.notice},"hmi-start-label":{"children":"RESET STOP" if c.emergency_stopped else "START"},
            "hmi-start":{"disabled":not c.emergency_stopped and (c.wind_block or c.weather is None or not c.packing_ok)},
            "hmi-hold-label":{"children":"RESUME" if c.held else "HOLD"},
            "hmi-hold":{"disabled":c.emergency_stopped or c.restart_required or (not c.moving and not c.held)},
            "hmi-stop":{"disabled":c.emergency_stopped},
            "hmi-cooling":{"children":"Cooling · "+m.get("cooling_state","WAITING FOR WEATHER")},
            "hmi-rpm":{"children":f"{rpm} rpm assumed demand · {m.get('cooling_kw',0):.3f} kW"},
            "fan-command":{"data":self.fan_command(bool(rpm))}}
        self.scene.button_actors["stop"].position=(-.016 if c.emergency_stopped else 0,0,0)
        targets["world-stop"]={"actor":actor_state(self.scene.button_actors["stop"])}
        colors=display_colors(display_lines(m,rpm))
        mesh=self.scene.display_mesh
        if not np.array_equal(mesh.cell_data["screen_rgb"],colors):
            mesh.cell_data["screen_rgb"]=colors
            targets["hmi-segments"]={"values":b64_encode_numpy(colors)}
            targets["vtk"]={"triggerRender":time.time()}
        self.instrument_changes={identity:props for identity,props in targets.items()
            if self._if_changed("instrument-"+identity,props) is not no_update}

    def take_instrument_changes(self):
        changes=self.instrument_changes
        self.instrument_changes={}
        return changes

    def fan_command(self,running):
        return {"centre":list(fan_centre(self.config)),"visual_rpm":12 if running else 0,
            "geometry_count":len(self.actors)+1}  # includes the camera bounds proxy

    def telemetry(self, detail):
        c,m=self.controller,self.controller.model
        now=pd.Timestamp.now(tz="UTC")
        try:
            local=now.tz_convert(self.operator_zone)
        except (KeyError,ValueError):
            local=now
        clocks=f"**SITE:** {c.stamp:%a %d %b %Y · %H:%M:%S} EAT · **LOCAL:** {local:%H:%M:%S} {self.operator_zone} · **{c.mode}**"
        def card(label,value,unit,caption):
            return html.Div([html.Span(label,className="metric-label"),
                html.Strong([value,html.Span(unit,className="metric-unit")],className="metric-value"),
                html.Span(caption,className="metric-caption")],className="metric-card")
        pv=f"{m['pv_dc_kw']:.2f}" if m["pv_dc_kw"] is not None else "—"
        load=f"{m['user_served_kw']:.2f}" if "user_served_kw" in m else "—"
        battery=f"Battery {m['battery_temp_c']:.1f}°C" if "battery_temp_c" in m else "LFP energy storage"
        metrics=html.Div([html.Div([
            card("PV generation",pv,"kW DC",f"{self.config.array_kwp:.1f} kWp installed capacity"),
            card("Battery state",f"{m['soc']*100:.1f}","% SOC",battery),
            card("Load served",load,"kW AC",f"{m['unserved_kw']:.2f} kW unserved" if "unserved_kw" in m else "Waiting for site weather"),
            card("Sun elevation",f"{m['sun_elevation']:.1f}","°",f"Azimuth {m['sun_azimuth']:.0f}° clockwise from north")],className="metric-grid"),
            html.P(f"{m['state']} · Simulated plant · Initial stored energy is excluded from renewable generation.",className="plant-caption")])
        weather=c.weather_error or ""
        if c.weather:
            w=c.weather
            age=max((now-pd.Timestamp(c.meta["retrieved_utc"])).total_seconds()/60,0)
            weather=f"[Open-Meteo model weather](https://open-meteo.com/en/docs) · {weather_label(w['weather_code'])} · {w['temp_air']:.1f}°C · gust {w['gust_ms']:.1f} m/s · cloud {w['cloud_pct']:.0f}% · GHI {w['ghi']:.0f}, DNI {w['dni']:.0f}, DHI {w['dhi']:.0f} W/m²\n\nSample {c.meta.get('current_time')} · retrieved {age:.0f} min ago · {c.meta.get('cache_status')}"
            if age>60 or "OFFLINE" in c.meta.get("cache_status",""):
                weather+=" **STALE / CACHED CONDITIONS**"
        if c.wind_block:
            weather+="\n\n**Wind interlock: new deployment inhibited; tracker stow requested.**"
        if not c.packing_ok:
            weather+="\n\n**The selected module count exceeds the illustrated packing envelope.**"
        mechanism=f"""| Subsystem | State / logic |
|---|---|
| Roof hatches | {hatch_angle(c.progress):.1f}° · closed in transport and installed states |
| Deployment | Open roof → lift → extend/unfold → lower/lock → close roof |
| Support locks | {'ENGAGED' if c.deployed else 'DISENGAGED'} |
| PV contactor | {'ENABLED' if c.pv_connected else 'ISOLATED'} |
| Panel count / packing height | {self.config.modules} / {layout(self.config)['packed_top_m']:.2f} m |
| Container dimensions | {' × '.join(f'{x:.3f}' for x in self.config.dimensions)} m |

Retract opens the roof before the modules return. Hold/reverse follows the same continuous trajectory.
Mechanics remain conceptual; actuator forces and complete structural/collision validation remain outstanding.
"""
        technical=mechanism
        if detail=="power" and c.weather:
            technical="\n".join(["| Channel | Simulated value |","|---|---:|",
                f"| User load served / unserved | {m['user_served_kw']:.2f} / {m['unserved_kw']:.2f} kW |",
                f"| Battery / enclosure | {m['battery_temp_c']:.2f} / {m['room_temp_c']:.2f} °C |",
                f"| Cooling mode / electricity | {m['cooling_state']} / {m['cooling_kw']:.3f} kW |",
                f"| Battery charge / discharge | {m['battery_charge_kw']:.2f} / {m['battery_discharge_kw']:.2f} kW |",
                f"| Module temperature / POA | {m['cell_temp_c']:.1f} °C / {m['poa_wm2']:.1f} W/m² |",
                f"| String Vmp / Voc | {m['string_vmp_v']:.1f} / {m['string_voc_v']:.1f} V |",
                f"| Session PV / served energy | {m['totals']['pv_kwh']:.3f} / {m['totals']['served_kwh']:.3f} kWh |",
                f"| DC balance residual | {m['dc_balance_residual_kw']:.3e} kW |"])
        elif detail=="weather":
            technical="Provider provenance and exact sampled model conditions are included in the JSON export. Landscape is illustrative; shadows are planar projections, not a surveyed shading study."
        elif detail=="export":
            technical=f"**Persistent vtk.js viewport** · motion timer 50 ms; idle timer 1 s; plant/clock 1 Hz; charts 0.2 Hz.\n\nLatest Python update: **{self.frame_ms:.1f} ms**, excluding network/browser rendering. Coordinates update individual buffers directly; static scene children stay mounted. One explicit render follows a buffer update. Unchanged labels and sky colour are not resent. Weather retrieval runs in a background worker."
        # Fifth channel is reserved for accessible deployment/roof confirmation.
        return clocks,metrics,weather,technical,f"Roof {hatch_angle(c.progress):.1f}° · {phase(c.progress)}"

    def figure(self, detail):
        c=self.controller
        fig=go.Figure()
        if detail=="power" and c.history:
            history=pd.DataFrame(c.history)
            for name in ("PV DC","Users AC"):
                fig.add_trace(go.Scatter(x=history.time,y=history[name],name=name))
            return charts.style(fig,300,"Power · kW")
        if detail=="weather" and c.frame is not None:
            today=c.frame[c.frame.index.date==c.stamp.date()]
            for name in ("ghi","dni","dhi"):
                fig.add_trace(go.Scatter(x=today.index,y=today[name],name=name.upper()))
            return charts.style(fig,300,"Forecast irradiance · W/m²")
        return charts.style(fig,160,"")

    def close(self):
        if not self.closed:
            self.closed=True
            if self.future is not None:
                self.future.cancel()
            self.scene.close()
