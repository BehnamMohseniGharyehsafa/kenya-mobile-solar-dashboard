"""Python-only container field interface, driven by wall time and live weather."""
from datetime import datetime, time as daytime, timedelta, timezone
from io import BytesIO
import json
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .live_weather import load_feed, sample_weather, weather_label
from .live_simulation import advance_plant, instant_plant, solar_position
from .mechanics import layout, phase, module_poses, smoothstep
from .scene import render_scene, build_plotter, CAMERAS
from . import charts


@st.cache_data(ttl=900,show_spinner=False)
def weather_feed(config, refresh=0):
    return load_feed(config,force=bool(refresh))


@st.cache_data(max_entries=20,show_spinner=False)
def rendered_view(config,p,tilt,azimuth,elevation,sun_azimuth,cloud,view,cutaway,landscape,shadows,dimensions,stamp,condition):
    return render_scene(config,p,tilt,azimuth,elevation,sun_azimuth,cloud_pct=cloud,
        camera=view,cutaway=cutaway,landscape=landscape,shadows=shadows,dimensions=dimensions,
        size=(1440,810),stamp=stamp,condition=condition)


@st.cache_data(max_entries=16,show_spinner=False)
def day_sun(config,day):
    idx=pd.date_range(str(day),periods=145,freq="10min",tz=config.timezone)
    import pvlib
    position=pvlib.solarposition.get_solarposition(idx,config.latitude,config.longitude,altitude=config.altitude_m)
    return pd.DataFrame({"sun_elevation_deg":position.apparent_elevation,"sun_azimuth_deg":position.azimuth},index=idx)


def _initial_session(config):
    return {"config":config.to_dict(),"progress":0.0,"target":0.0,"hold":False,
        "mechanical_last":time.monotonic(),"energy_last":None,"plant":{},"history":[],
        "mode_last":None,"anchor_monotonic":time.monotonic(),"tour_anchor":None,
        "paused":False,"last_display":None,"weather_refresh":0,"notice":"Session initialized at the configured initial SOC."}


def _command(target):
    state=st.session_state.field_session
    state["target"],state["hold"],state["mechanical_last"]=target,False,time.monotonic()


def _clock_command(mode):
    st.session_state.field_clock=mode
    state=st.session_state.field_session
    state["mode_last"]=None
    state["paused"]=False


def _toggle_hold():
    state=st.session_state.field_session
    state["hold"]=not state["hold"]
    state["mechanical_last"]=time.monotonic()


def _refresh():
    state=st.session_state.field_session
    state["weather_refresh"]+=1
    weather_feed.clear()


def _reset_energy():
    state=st.session_state.field_session
    state["plant"],state["history"],state["energy_last"]={},[],None
    state["notice"]="Electrical/thermal session reset to the applied initial SOC."


def _metrics(items):
    for column,(label,value,detail) in zip(st.columns(len(items)),items):
        with column:
            st.metric(label,value,border=True)
            if detail:
                st.caption(detail)


def _timestamp(config,mode,manual_day,manual_time,speed,state,now):
    if state["mode_last"] != mode:
        state["mode_last"]=mode
        state["anchor_monotonic"]=time.monotonic()
        state["tour_anchor"]=pd.Timestamp(datetime.combine(now.tz_convert(config.timezone).date(),daytime(6)),tz=config.timezone)
        state["plant"],state["history"],state["energy_last"]={},[],None
        state["notice"]="Clock mode changed; electrical and thermal session states restarted."
    if mode=="Live site clock":
        return now.tz_convert(config.timezone)
    if mode=="Accelerated solar day":
        seconds=(time.monotonic()-state["anchor_monotonic"])*speed
        return state["tour_anchor"]+pd.Timedelta(seconds=seconds%(18*3600))
    return pd.Timestamp(datetime.combine(manual_day,manual_time),tz=config.timezone)


def render_live_site(config):
    if "field_session" not in st.session_state or st.session_state.field_session["config"]!=config.to_dict():
        st.session_state.field_session=_initial_session(config)
    state=st.session_state.field_session
    st.caption("FIELD SYSTEM 01 / CONTAINER DIGITAL MODEL")
    st.title("Kenya · Container field lab")
    st.write(f"**{config.site}** · {config.container_ft} ft high cube · {config.modules} modules · {config.array_kwp:.1f} kWp · {config.battery_kwh:g} kWh LFP")
    st.caption("Live model weather + a simulated plant. Every panel, hatch, fence and support is constructed in Python.")
    a,b,c,d=st.columns([1.3,1.1,1,1])
    with a:
        mode=st.selectbox("Simulation clock",["Live site clock","Accelerated solar day","Manual sun study"],key="field_clock")
    with b:
        camera=st.selectbox("Camera",list(CAMERAS),key="field_camera")
    with c:
        cutaway=st.toggle("Enclosure cutaway",False)
    with d:
        settings=st.popover("View & clock settings")
    with settings:
        dimensions=st.toggle("Engineering dimensions",False)
        automatic=st.toggle("Automatic clock and animation updates",True,key="field_auto")
        a,b=st.columns(2)
        with a:
            landscape=st.checkbox("Landscape and vegetation",True)
            shadows=st.checkbox("Geometric sun shadows",True)
        with b:
            speed=st.select_slider("Solar-day speed",options=[60,120,300,600,1200],value=600,format_func=lambda x:f"{x}× real time")
            duration=st.slider("Deployment animation duration (s)",8,40,18)
        with a:
            manual_day=st.date_input("Study date · within downloaded forecast",value=datetime.now(timezone.utc).astimezone(ZoneInfo(config.timezone)).date())
            manual_time=st.time_input("Study time · EAT",value=daytime(12))
        st.caption("Deployment duration is presentation time, not a measured installation speed. The landscape is procedural and is not a surveyed site. Shadow projection uses the local compound plane; terrain occlusion is not ray-traced.")
    drawing=st.fragment(run_every=2.0 if automatic else None)(draw_live)
    drawing(config,mode,camera,cutaway,dimensions,landscape,shadows,speed,duration,manual_day,manual_time)


def draw_live(config,mode,camera,cutaway,dimensions,landscape,shadows,speed,duration,manual_day,manual_time):
    if st.session_state.field_clock != mode:
        st.rerun(scope="app")
    state=st.session_state.field_session
    now=pd.Timestamp.now(tz="UTC")
    stamp=_timestamp(config,mode,manual_day,manual_time,speed,state,now)
    browser_zone=st.context.timezone or "Europe/Dublin"
    try:
        local=now.tz_convert(browser_zone)
    except Exception:
        browser_zone="UTC"
        local=now
    state["last_display"]=stamp
    feed_error=None
    try:
        frame,meta=weather_feed(config,state["weather_refresh"])
        weather=sample_weather(frame,meta,stamp,live=mode=="Live site clock")
        age=max((now-pd.Timestamp(meta["retrieved_utc"])).total_seconds()/60,0)
        stale=age>60 or "OFFLINE" in meta.get("cache_status","")
    except (RuntimeError,ValueError,KeyError) as exc:
        feed_error=str(exc)
        weather,meta,frame,age,stale=None,{},None,0,True
    # Mechanical progress depends on elapsed wall time, independent of sun speed.
    mechanical_dt=max(time.monotonic()-state["mechanical_last"],0)
    state["mechanical_last"]=time.monotonic()
    if weather and weather["gust_ms"]>=config.stow_on_ms and state["target"]>state["progress"] and state["progress"]<1:
        state["hold"]=True
    if not state["hold"]:
        difference=state["target"]-state["progress"]
        state["progress"]+=float(np.clip(difference,-mechanical_dt/duration,mechanical_dt/duration))
    progress=float(np.clip(state["progress"],0,1))
    moving=abs(state["target"]-progress)>1e-6 and not state["hold"]
    deployed=progress>=1-1e-6 and state["target"]>=1
    d=layout(config)
    packing_ok=d["packed_top_m"]<config.dimensions[2]+.20
    gust=weather["gust_ms"] if weather else None
    wind_block=gust is not None and gust>=config.stow_on_ms
    a,b,c,dcol=st.columns([1.3,1.3,.85,.85])
    with a:
        st.button("Deploy · open roof & install PV",type="primary",width="stretch",on_click=_command,args=(1.0,),
            disabled=(state["target"]==1 and not state["hold"]) or not packing_ok or wind_block,
            key="field_deploy",help="One sequence: open roof, lift cassettes, extend/unfold, lower supports and enable generation.")
    with b:
        st.button("Retract · pack & close container",width="stretch",on_click=_command,args=(0.0,),
            disabled=(state["target"]==0 and not state["hold"]),key="field_retract")
    with c:
        st.button("Resume motion" if state["hold"] else "Hold motion",width="stretch",on_click=_toggle_hold,
            disabled=not moving and not state["hold"],key="field_hold")
    with dcol:
        st.button("Refresh weather",width="stretch",on_click=_refresh,key="field_refresh")
    a,b,c=st.columns([1.2,1.2,2])
    with a:
        st.button("Run solar-day tour",width="stretch",on_click=_clock_command,args=("Accelerated solar day",),key="field_tour")
    with b:
        st.button("Use live site clock",width="stretch",on_click=_clock_command,args=("Live site clock",),key="field_live")
    with c:
        direction="DEPLOYING" if state["target"]>progress else "RETRACTING" if state["target"]<progress else "READY"
        st.caption(f"{direction} · {phase(progress)} · {progress*100:.0f}% deployed"+(" · MOTION HELD" if state["hold"] else ""))
        st.progress(progress)
    if not packing_ok:
        st.error("The selected module count exceeds the illustrated packing envelope. Reduce the array or specify a larger packing arrangement.")
    if wind_block:
        st.warning(f"Weather-model gust {gust:.1f} m/s exceeds the assumed deployment/stow threshold {config.stow_on_ms:g} m/s. New deployment is inhibited; a deployed tracker commands stow.")
    if feed_error:
        st.warning(feed_error+" Solar geometry remains available; current generation and plant dynamics are unavailable.")
        sun=solar_position(config,stamp)
        model={"tilt":0,"azimuth":90,"rotation":0,"sun_elevation":float(sun.apparent_elevation),
            "sun_azimuth":float(sun.azimuth),"state":"WEATHER UNAVAILABLE","pv_dc_kw":None,"soc":config.soc_initial,
            "battery_temp_c":None,"room_temp_c":None,"totals":{}}
    else:
        if stale:
            st.warning(f"Weather response is {age:.0f} minutes old · {meta.get('cache_status')}. These are cached model conditions, not a fresh observation.")
        previous=state["energy_last"]
        elapsed=(stamp-pd.Timestamp(previous)).total_seconds() if previous else 0.0
        if elapsed<0 or elapsed>6*3600:
            state["plant"]={}
            state["history"]=[]
            elapsed=0
            state["notice"]="Time jumped; electrical/thermal states restarted at configured initial SOC."
        model=advance_plant(config,stamp,weather,deployed,state["plant"],max(elapsed,0.0),moving=moving)
        state["energy_last"]=stamp.isoformat()
        state["history"].append({"time":stamp,"PV DC":float(model["pv_dc_kw"]),
            "Users AC":float(model["user_served_kw"]),"SOC (%)":float(model["soc"])*100})
        state["history"]=state["history"][-240:]
    # Image geometry is cached at 0.1-degree precision. The clock and plant
    # values still update each second without needlessly rerendering night sky.
    cloud=float(weather["cloud_pct"]) if weather else 0
    condition=weather_label(weather["weather_code"]) if weather else "Weather unavailable"
    scene_stamp=f"{stamp.strftime('%d %b %Y  %H:%M')} EAT  /  SUN {model['sun_elevation']:.1f}°  /  {phase(progress)}"
    image=rendered_view(config,round(progress,3),round(model["tilt"],1),round(model["azimuth"],1),
        round(model["sun_elevation"],1),round(model["sun_azimuth"],1),round(cloud/5)*5,
        camera,cutaway,landscape,shadows,dimensions,scene_stamp,condition)
    st.image(image,width="stretch")
    st.caption(f"SITE CLOCK  {stamp.strftime('%a %d %b %Y · %H:%M:%S')} EAT  |  YOUR LOCAL CLOCK  {local.strftime('%H:%M:%S')} {browser_zone}  |  "+("LIVE CLOCK" if mode=="Live site clock" else f"SIMULATED TIME · {mode}"))
    _metrics([
        ("PV at DC bus",f"{model['pv_dc_kw']:.2f} kW" if model["pv_dc_kw"] is not None else "Unavailable",
            "Contactor enabled" if deployed else "Array isolated during packing / deployment"),
        ("Sun elevation / azimuth",f"{model['sun_elevation']:.1f}° / {model['sun_azimuth']:.0f}°",model["state"]),
        ("Air / model gust",f"{weather['temp_air']:.1f}°C / {weather['gust_ms']:.1f} m/s" if weather else "Unavailable",condition),
        ("Battery SOC",f"{model['soc']*100:.1f}%","Simulated session state; not hardware telemetry")])
    if weather:
        st.caption(f"[Open-Meteo weather source](https://open-meteo.com/en/docs) · current model sample {meta.get('current_time')} · fetched {age:.0f} min ago · GHI {weather['ghi']:.0f}, DNI {weather['dni']:.0f}, DHI {weather['dhi']:.0f} W/m² · cloud {cloud:.0f}% · {meta.get('cache_status')}")
    power,mechanism,weather_tab,inspection=st.tabs(["Power & thermal state","Mechanism & interlocks","Weather & solar geometry","3D inspection & export"])
    with power:
        if weather:
            _metrics([
                ("Users served · AC",f"{model['user_served_kw']:.2f} kW",f"Unserved {model['unserved_kw']:.2f} kW"),
                ("Battery / enclosure",f"{model['battery_temp_c']:.1f}°C / {model['room_temp_c']:.1f}°C",model["cooling_state"]),
                ("Battery DC",f"{model['battery_discharge_kw']-model['battery_charge_kw']:+.2f} kW","Positive discharging; negative charging"),
                ("Session PV energy",f"{model['totals']['pv_kwh']:.3f} kWh",f"Cooling {model['totals']['cooling_kwh']:.3f} kWh")])
            fig=go.Figure()
            history=pd.DataFrame(state["history"])
            for col,color in [("PV DC",charts.COLORS["solar"]),("Users AC",charts.COLORS["load"])]:
                fig.add_trace(go.Scatter(x=history.time,y=history[col],name=col,line=dict(color=color,width=2)))
            st.plotly_chart(charts.style(fig,260,"Power (kW)"),width="stretch",key="field_history")
            st.caption(state["notice"]+" States persist between ticks; changing clock mode restarts them. Annual yield remains on the Overview page and is not mixed with current forecast output.")
            st.button("Reset electrical / thermal session",on_click=_reset_energy,key="field_reset")
            with st.expander("Instantaneous electrical and thermal channels"):
                channels=[("String Vmp",model["string_vmp_v"],"V"),("String Voc",model["string_voc_v"],"V"),
                    ("Module temperature",model["cell_temp_c"],"°C"),("POA irradiance",model["poa_wm2"],"W/m²"),
                    ("PV if mechanically ready",model["potential_dc_kw"],"kW"),("Cooling electricity",model["cooling_kw"],"kW"),
                    ("DC-bus balance residual",model["dc_balance_residual_kw"],"kW")]
                st.dataframe(pd.DataFrame(channels,columns=["Channel","Value","Unit"]),hide_index=True,width="stretch")
    with mechanism:
        st.dataframe(pd.DataFrame([
            ["Roof hatches",f"{108*smoothstep(progress/.2):.1f}°", "Open before cassette lift"],
            ["Cassette lift", "Complete" if progress>=.40 else "Packed / moving", "Top extraction, not through a closed roof"],
            ["Rails / fold-out",f"{smoothstep((progress-.4)/.42)*100:.0f}%", "Telescopic extension and unfolding"],
            ["Support locks","ENGAGED" if deployed else "DISENGAGED","PV contactor remains open until fully deployed"],
            ["PV isolation","GENERATION ENABLED" if deployed else "OPEN / ISOLATED","Stowed or moving panels generate zero accepted DC"],
            ["Packing height",f"{layout(config)['packed_top_m']:.2f} m","Discrete module stack; no overlapping packed panels"],
            ["Panel count",str(config.modules),"Every module is modelled in packed and deployed positions"],
            ["Wind permission","INHIBITED" if wind_block else "PERMITTED" if weather else "UNKNOWN","Uses modelled gust; not a certified safety input"],
        ],columns=["Subsystem","State","Logic / constraint"]),hide_index=True,width="stretch")
        st.write("Deploy is one command for roof opening → cassette lift → rail extension / unfolding → support engagement → PV enable. Retract automatically isolates the array and reverses the sequence. Motion can be held or reversed at any point.")
        st.caption("The shown kinematics are a transport-and-deployment concept. Actuator forces, hinge loads, cable fatigue, stow aerodynamics and full collision clearance still require a mechanical design. Default module positions fit inside the closed shell; equipment packing is an indicative layout.")
    with weather_tab:
        sunrow=pd.Series({"sun_elevation_deg":model["sun_elevation"],"sun_azimuth_deg":model["sun_azimuth"],
            "surface_tilt_deg":model["tilt"],"surface_azimuth_deg":model["azimuth"]})
        left,right=st.columns(2)
        with left:
            st.plotly_chart(charts.sun_path(day_sun(config,stamp.date()),sunrow),width="stretch",key="field_sunpath")
        with right:
            if frame is not None:
                today=frame[frame.index.date==stamp.date()]
                fig=go.Figure()
                for col,label in [("ghi","GHI"),("dni","DNI"),("dhi","DHI")]:
                    fig.add_trace(go.Scatter(x=today.index,y=today[col],name=label))
                st.plotly_chart(charts.style(fig,370,"Instantaneous forecast irradiance (W/m²)"),width="stretch",key="field_weather")
        if meta:
            st.json(meta,expanded=False)
        st.caption("Current weather is numerical weather-model output. For Kenya, display interpolation adds no measured subhourly detail. Shadow lengths and directions use site solar geometry. The sun marker is shown at a reduced distance for legibility; shadow rays are parallel. Landscape is illustrative, not surveyed terrain or a validated shading-energy model.")
    with inspection:
        orbit=st.toggle("Enable interactive orbit inspection",False,key="field_orbit")
        if orbit:
            from stpyvista import stpyvista
            plotter=build_plotter(config,progress,model["tilt"],model["azimuth"],model["sun_elevation"],model["sun_azimuth"],
                cloud_pct=cloud,camera=camera,cutaway=cutaway,landscape=landscape,shadows=shadows,
                dimensions=dimensions,size=(1200,620),stamp=scene_stamp,condition=condition)
            try:
                stpyvista(plotter,key="field_orbit_view",panel_kwargs={"orientation_widget":True})
            finally:
                plotter.close()
            st.caption("Drag to orbit; scroll to zoom. Switch off automatic updates above for an uninterrupted inspection of this snapshot.")
        export={"site":config.site,"simulated_time":stamp.isoformat(),"clock_mode":mode,
            "deployment_progress":progress,"mechanical_phase":phase(progress),"config":config.to_dict(),
            "weather":{k:str(v) if isinstance(v,pd.Timestamp) else v for k,v in (weather or {}).items()},
            "weather_provenance":meta,"plant":model,
            "module_centres_m":[{"id":p.number,"centre":p.center} for p in module_poses(config,progress,model["tilt"],model["azimuth"])]}
        st.download_button("Export technical snapshot JSON",json.dumps(export,indent=2,default=str),"container_snapshot.json","application/json",key="field_snapshot")
        st.download_button("Save current scene PNG",image,"container_scene.png","image/png",key="field_png")
