"""Persistent Dash VTK workspace, authored entirely in Python.

Only actor properties and the small projected-shadow meshes change during a
tick. Static geometry and the vtk.js View remain mounted in the browser.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time

import numpy as np
import pandas as pd
from dash import html, dcc, Patch, no_update
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

WEATHER_POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix="site-weather")
BUTTON={"background":"#223641","color":"#edf2ed","border":"1px solid #4b6269",
    "borderRadius":"6px","padding":"10px 15px","cursor":"pointer","fontSize":"14px"}
ROW={"display":"flex","flexWrap":"wrap","gap":"8px","alignItems":"center","marginBottom":"10px"}


def interaction_settings(tool="Orbit"):
    return [{"button":1,"action":{"Orbit":"Rotate","Pan":"Pan","Zoom":"Zoom"}[tool]},
        {"button":2,"action":"Pan"},{"button":3,"action":"Zoom","scrollEnabled":True},
        {"button":1,"shift":True,"action":"Pan"},{"button":1,"alt":True,"action":"Zoom"},
        {"button":1,"control":True,"action":"ZoomToMouse"}]


def actor_state(actor):
    matrix=actor.GetMatrix()
    return {"userMatrix":[matrix.GetElement(i,j) for j in range(4) for i in range(4)],
        "visibility":bool(actor.GetVisibility()),"useBounds":bool(actor.GetUseBounds())}


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
        self.actor_states={i:actor_state(self.actors[i]) for i in self.dynamic_indices+self.shadow_indices}
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
            result.append(dash_vtk.GeometryRepresentation(id=f"part-{i}",actor=actor_state(actor),mapper=mapper,
                property={"color":list(prop.GetColor()),"opacity":prop.GetOpacity(),
                    "ambient":prop.GetAmbient(),"diffuse":prop.GetDiffuse(),
                    "specular":prop.GetSpecular(),"lineWidth":prop.GetLineWidth(),
                    "lighting":bool(prop.GetLighting())},
                children=[dash_vtk.Mesh(id=f"mesh-{i}",state=to_mesh_state(mesh,field))]))
        return result

    def layout(self, session):
        button=lambda name,identity:html.Button(name,id=identity,n_clicks=0,style=BUTTON)
        return html.Div([
            dcc.Store(id="session",data=session),dcc.Interval(id="tick",interval=80,n_intervals=0),
            html.Div([button("Deploy · open roof & install PV","deploy"),button("Retract · pack & close container","retract"),
                button("Hold motion","hold"),button("Refresh weather","refresh")],style=ROW),
            html.Div([html.Label("Camera preset"),dcc.Dropdown(id="camera",options=list(CAMERAS),value="Site overview",
                clearable=False,style={"width":"240px","color":"#142832"}),button("Reset view","reset-view"),
                button("Run solar-day tour","tour"),button("Use live site clock","live")],style=ROW),
            html.Div([html.Strong("Drag tool:"),dcc.RadioItems(id="tool",options=["Orbit","Pan","Zoom"],value="Orbit",inline=True,
                labelStyle={"marginRight":"16px"})],style=ROW),
            html.P("Drag in the scene with the selected tool. Wheel / right-drag also zooms; Shift + left-drag pans. Camera movement is preserved during updates."),
            html.Strong("TRANSPORT LOCKED",id="status"),html.Small(id="roof-state",style={"marginLeft":"15px"}),
            html.Progress(id="progress",value=0,max=100,style={"width":"100%","height":"8px"}),
            html.Div(dash_vtk.View(id="vtk",children=self.representations(),cameraPosition=list(CAMERAS["Site overview"][0]),
                cameraViewUp=[0,0,1],background=[.57,.67,.72],
                interactorSettings=interaction_settings(),
                style={"width":"100%","height":"100%"}),
                style={"height":"min(66vh,660px)","minHeight":"400px","marginTop":"10px","borderRadius":"8px","overflow":"hidden"}),
            dcc.Markdown(id="clocks"),dcc.Markdown(id="metrics"),dcc.Markdown(id="weather"),
            html.Details([html.Summary("Clock, animation and view settings"),
                html.Div([html.Label("Simulation clock"),dcc.Dropdown(id="clock",options=["Live site clock","Accelerated solar day","Manual sun study"],
                    value="Live site clock",clearable=False,style={"width":"245px","color":"#142832"}),
                    dcc.Input(id="manual",type="text",value=pd.Timestamp.now(tz=self.config.timezone).strftime("%Y-%m-%d 12:00"),
                        placeholder="Study time · YYYY-MM-DD HH:MM EAT",style={"padding":"10px"}),
                    html.Label("Tour speed"),dcc.Dropdown(id="speed",options=[60,120,300,600,1200],value=600,clearable=False,
                        style={"width":"110px","color":"#142832"})],style=ROW),
                html.Label("Deployment animation duration (seconds)"),dcc.Slider(id="duration",min=2,max=20,step=1,value=6,
                    marks={2:"2",6:"6",12:"12",20:"20"}),
                dcc.Checklist(id="options",options=[{"label":"Geometric sun shadows","value":"shadows"},
                    {"label":"Landscape and vegetation","value":"landscape"},{"label":"Container cutaway","value":"cutaway"}],
                    value=["shadows","landscape"]),
                html.P("Presentation duration is not a measured installation speed. Manual study time must lie within the downloaded weather window.")]),
            dcc.Tabs(id="detail-tab",value="power",children=[
                dcc.Tab(label="Power & thermal state",value="power"),dcc.Tab(label="Mechanism & interlocks",value="mechanism"),
                dcc.Tab(label="Weather & solar geometry",value="weather"),dcc.Tab(label="Export & performance",value="export")],
                colors={"border":"#40545c","primary":"#f4b657","background":"#192832"}),
            dcc.Markdown(id="technical"),dcc.Graph(id="plot",config={"displaylogo":False},style={"height":"300px"}),
            html.Div([button("Export technical snapshot JSON","export"),button("Export scene PNG","export-png"),
                dcc.Download(id="download")],style=ROW),
        ],style={"position":"absolute","top":0,"left":0,"right":0,"minHeight":"100vh","boxSizing":"border-box",
            "background":"#101a21","color":"#e9f0f1","padding":"16px","fontFamily":"Segoe UI, Arial, sans-serif","fontSize":"14px"})

    def step(self, event, mode, manual, speed, duration, options, detail):
        with self.lock:
            return self._step(event,mode,manual,speed,duration,options,detail)

    def _step(self,event,mode,manual,speed,duration,options,detail):
        started=time.perf_counter()
        now=pd.Timestamp.now(tz="UTC")
        mono=time.monotonic()
        self.last_used=mono
        c=self.controller
        force=event!="tick"
        render_options=("landscape" in options,"cutaway" in options)
        rebuilt=render_options!=self.render_options
        if rebuilt:
            old=self.scene
            self.scene=InteractiveScene(self.config,landscape=render_options[0],cutaway=render_options[1])
            self.render_options=render_options
            self._index_actors()
            old.close()
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
                selected=pd.Timestamp(manual).tz_localize(c.config.timezone)
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
        before=c.deployed
        c.step_motion()
        physics=force or mono-self.last_physics>=1 or before!=c.deployed
        if physics:
            c.step_plant(now)
            self.last_physics=mono
        m=c.model
        changed=self.scene.update(c.progress,m["tilt"],m["azimuth"],m["sun_elevation"],m["sun_azimuth"],
            c.weather["cloud_pct"] if c.weather else 0,"shadows" in options)
        patch=no_update
        if rebuilt:
            patch=self.representations()
        elif changed:
            patch=Patch()
            for i in self.dynamic_indices+self.shadow_indices:
                actor=self.actors[i]
                state=actor_state(actor)
                if state!=self.actor_states[i]:
                    patch[i]["props"]["actor"]=state
                    self.actor_states[i]=state
                mesh=actor.mapper.dataset
                if mesh.GetMTime()!=self.mesh_mtimes[i]:
                    # Topology and colours are fixed throughout motion. Send
                    # only changed coordinates, retaining the browser buffers.
                    patch[i]["props"]["children"][0]["props"]["state"]["mesh"]["points"]=b64_encode_numpy(mesh.points)
                    self.mesh_mtimes[i]=mesh.GetMTime()
        telemetry=self.telemetry(detail) if physics else (no_update,)*5
        figure=no_update
        if force or mono-self.last_chart>5:
            figure=self.figure(detail)
            self.last_chart=mono
        self.frame_ms=(time.perf_counter()-started)*1000
        status=f"{'DEPLOYING' if c.target>c.progress else 'RETRACTING' if c.target<c.progress else 'READY'} · {phase(c.progress)} · {c.progress*100:.0f}% deployed"+(" · MOTION HELD" if c.held else "")
        return (patch,status,c.progress*100,*telemetry,figure,
            (c.target==1 and not c.held) or c.wind_block or c.weather is None or not c.packing_ok,
            c.target==0 and not c.held,not c.moving and not c.held,"Resume motion" if c.held else "Hold motion",
            ([.08,.12,.17] if m["sun_elevation"]<=0 else [.57,.67,.72]) if physics else no_update)

    def telemetry(self, detail):
        c,m=self.controller,self.controller.model
        now=pd.Timestamp.now(tz="UTC")
        try:
            local=now.tz_convert(self.operator_zone)
        except (KeyError,ValueError):
            local=now
        clocks=f"**SITE:** {c.stamp:%a %d %b %Y · %H:%M:%S} EAT · **LOCAL:** {local:%H:%M:%S} {self.operator_zone} · **{c.mode}**"
        pv=f"{m['pv_dc_kw']:.2f} kW" if m["pv_dc_kw"] is not None else "Unavailable"
        metrics=f"### PV DC: {pv} | SOC: {m['soc']*100:.1f}% | Sun: {m['sun_elevation']:.1f}° / {m['sun_azimuth']:.0f}°\n**{m['state']}** · simulated plant, not hardware telemetry"
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
| PV contactor | {'ENABLED' if c.deployed else 'ISOLATED'} |
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
            technical=f"**Persistent vtk.js viewport** · motion targets 12.5 updates/s; plant/clock 1 Hz; charts 0.2 Hz.\n\nLatest Python update: **{self.frame_ms:.1f} ms**, excluding network/browser rendering. Static meshes are sent at initial load; subsequent messages patch actor transformations and small shadow meshes. No frame screenshots or full-page reruns occur. Weather retrieval runs in a background worker."
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
