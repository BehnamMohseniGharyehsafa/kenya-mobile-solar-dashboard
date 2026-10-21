"""Clock-driven, stateful plant calculations shared by the live container UI."""
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pvlib

from .pv import simulate_pv, _move
from .dispatch import simulate_dispatch


def solar_position(c, when, weather=None):
    when=pd.Timestamp(when)
    if when.tz is None:
        raise ValueError("Solar time must have an explicit timezone.")
    weather=weather or {}
    return pvlib.solarposition.get_solarposition(pd.DatetimeIndex([when]),c.latitude,c.longitude,
        altitude=c.altitude_m,pressure=weather.get("pressure"),
        temperature=weather.get("temp_air",20),method="nrel_numpy").iloc[0]


def instant_plant(c, when, weather, deployed, previous_pose=None, elapsed_seconds=1, isolation_state=None):
    sun=solar_position(c,when,weather)
    daylight=sun.apparent_elevation>0
    old_pose=previous_pose or {}
    wind=weather["gust_ms"]>=c.stow_on_ms or old_pose.get("wind_latched",False)
    recovery=0.0
    if weather["gust_ms"]>=c.stow_on_ms:
        wind=True
    elif wind:
        recovery=old_pose.get("wind_recovery_s",0)+max(elapsed_seconds,0) if weather["gust_ms"]<=c.stow_off_ms else 0.0
        if recovery>=c.stow_hold_minutes*60:
            wind=False
    state="TRANSPORT LOCKED" if not deployed else "WIND STOW" if wind else "TRACKING" if daylight else "NIGHT PARK"
    tilt,azimuth,rotation=0.0,90.0,0.0
    if c.tracking=="Fixed tilt":
        tilt,azimuth=c.fixed_tilt_deg,c.fixed_azimuth_deg
        state="FIXED" if deployed else "TRANSPORT LOCKED"
    elif c.tracking=="Single axis":
        target=pvlib.tracking.singleaxis(np.array([sun.apparent_zenith]),np.array([sun.azimuth]),
            axis_azimuth=c.axis_azimuth_deg,max_angle=c.max_rotation_deg,
            backtrack=c.backtracking,gcr=c.gcr)["tracker_theta"][0] if daylight else 0.0
        target=c.stow_tilt_deg if wind else float(np.nan_to_num(target))
        old=previous_pose.get("rotation",target) if previous_pose else target
        rotation,travel=_move(old,target,c.slew_deg_per_min*max(elapsed_seconds,0)/60,c.tracker_deadband_deg)
        tilt,azimuth=abs(rotation),(c.axis_azimuth_deg+(90 if rotation>0 else -90))%360
    else:
        target_tilt=c.stow_tilt_deg if wind else min(sun.apparent_zenith,c.max_rotation_deg) if daylight else 0.0
        target_az=float(sun.azimuth) if daylight and not wind else (previous_pose or {}).get("azimuth",90.0)
        old=previous_pose or {"tilt":target_tilt,"azimuth":target_az}
        tilt,_=_move(old["tilt"],target_tilt,c.slew_deg_per_min*max(elapsed_seconds,0)/60,c.tracker_deadband_deg)
        azimuth,_=_move(old["azimuth"],target_az,c.slew_deg_per_min*max(elapsed_seconds,0)/60,c.tracker_deadband_deg,True)
        rotation=tilt
    if not deployed:
        tilt,azimuth,rotation=0.0,90.0,0.0
    if isolation_state:
        state=isolation_state
        if deployed and previous_pose:
            tilt,azimuth,rotation=(previous_pose[key] for key in ("tilt","azimuth","rotation"))
    idx=pd.DatetimeIndex([pd.Timestamp(when)])
    data={k:[weather[k]] for k in ("temp_air","relative_humidity","pressure","wind_speed","ghi","dni","dhi")}
    data.update({"gust_proxy_ms":[weather["gust_ms"]],"fault_active":[False],"solar_time":idx})
    w=pd.DataFrame(data,index=idx)
    pose=pd.DataFrame({"surface_tilt_deg":[tilt],"surface_azimuth_deg":[azimuth],
        "tracker_rotation_deg":[rotation],"tracker_kw":[float(c.tracker_standby_kw if deployed and not isolation_state else 0.0)],
        "tracker_state":[state]},index=idx)
    pv=simulate_pv(w,c,pose_override=pose)
    potential=float(pv.pv_dc_kw.iloc[0])
    if not deployed or isolation_state:
        pv.loc[:,"pv_dc_kw"]=0.0
    return w,pv,{"tilt":float(tilt),"azimuth":float(azimuth),"rotation":float(rotation),
        "sun_elevation":float(sun.apparent_elevation),"sun_azimuth":float(sun.azimuth),
        "state":state,"potential_dc_kw":potential,"wind_stow":wind,"wind_latched":wind,"wind_recovery_s":recovery}


def advance_plant(c,when,weather,deployed,session,elapsed_seconds,moving=False,isolation_state=None):
    w,pv,pose=instant_plant(c,when,weather,deployed,session.get("pose"),elapsed_seconds,isolation_state)
    if moving:
        pv.loc[:,"tracker_kw"]=c.tracker_kw
    # Exact elapsed time is split into <=60 s dispatch/thermal steps so an
    # accelerated clock does not skip SOC or thermostat transitions.
    seconds=max(float(elapsed_seconds),0)
    count=max(1,int(np.ceil(seconds/60)))
    step=seconds/count
    state=session.get("dispatch")
    original_state=state
    totals=session.setdefault("totals",{"pv_kwh":0.0,"served_kwh":0.0,"cooling_kwh":0.0,"unserved_kwh":0.0})
    for _ in range(count):
        out,state=simulate_dispatch(w,pv,c,initial_state=state,return_state=True,dt_hours=max(step/3600,1e-10))
        sample=out.iloc[0]
        totals["pv_kwh"]+=float(pv.pv_dc_kw.iloc[0])*step/3600
        totals["served_kwh"]+=float(sample.user_served_kw)*step/3600
        totals["cooling_kwh"]+=float(sample.cooling_kw)*step/3600
        totals["unserved_kwh"]+=float(sample.unserved_kw)*step/3600
    if seconds>0:
        session["dispatch"]=state
    else:
        session["dispatch"]=original_state
        sample["soc"]=(original_state["energy"]/(c.battery_kwh*c.battery_soh)) if original_state else c.soc_initial
    session["pose"]=pose
    return {**pv.iloc[0].to_dict(),**sample.to_dict(),**pose,"totals":dict(totals)}
