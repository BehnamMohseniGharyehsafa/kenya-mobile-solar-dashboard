"""Independent clock, deployment and plant state for a persistent field session."""
import time
import numpy as np
import pandas as pd

from .mechanics import hatch_angle, layout, phase, module_poses
from .live_simulation import advance_plant, solar_position
from .live_weather import sample_weather


class FieldController:
    def __init__(self, config, monotonic=time.monotonic):
        self.config=config
        self.monotonic=monotonic
        self.last_motion=monotonic()
        self.progress=self.target=0.
        self.held=False
        self.duration=6.
        self.mode="Live site clock"
        self.speed=600
        self.clock_anchor=monotonic()
        self.tour_anchor=None
        self.manual=None
        self.frame=None
        self.meta={}
        self.weather=None
        self.weather_error="Loading site weather…"
        self.plant={}
        self.model={}
        self.energy_last=None
        self.history=[]
        self.stamp=None
        self.notice="Simulated plant; initial stored energy is not counted as renewable production."

    @property
    def wind_block(self):
        return self.weather is not None and self.weather["gust_ms"]>=self.config.stow_on_ms

    @property
    def moving(self):
        return abs(self.target-self.progress)>1e-6 and not self.held

    @property
    def deployed(self):
        return self.progress>=1-1e-6 and self.target==1

    @property
    def packing_ok(self):
        return layout(self.config)["packed_top_m"]<self.config.dimensions[2]+.20

    def command(self, target):
        if target==1 and (self.wind_block or not self.packing_ok or self.weather is None):
            return False
        self.target=float(target)
        self.held=False
        self.last_motion=self.monotonic()
        return True

    def hold(self):
        self.held=not self.held
        self.last_motion=self.monotonic()

    def reset_energy(self):
        self.plant={}
        self.energy_last=None
        self.history=[]

    def set_mode(self, mode, now):
        self.mode=mode
        self.clock_anchor=self.monotonic()
        local=pd.Timestamp(now).tz_convert(self.config.timezone)
        self.tour_anchor=local.normalize()+pd.Timedelta(hours=6)
        self.manual=local.normalize()+pd.Timedelta(hours=12)
        self.reset_energy()

    def timestamp(self, now):
        if self.mode=="Live site clock":
            return pd.Timestamp(now).tz_convert(self.config.timezone)
        if self.mode=="Accelerated solar day":
            return self.tour_anchor+pd.Timedelta(seconds=((self.monotonic()-self.clock_anchor)*self.speed)%(18*3600))
        return self.manual

    def set_feed(self, frame, meta):
        self.frame,self.meta=frame,meta
        self.weather_error=None

    def step_motion(self):
        now=self.monotonic()
        dt=max(now-self.last_motion,0)
        self.last_motion=now
        if self.wind_block and self.target>self.progress:
            self.held=True
        if not self.held:
            self.progress+=float(np.clip(self.target-self.progress,-dt/self.duration,dt/self.duration))
        self.progress=float(np.clip(self.progress,0,1))

    def step_plant(self, now):
        self.stamp=self.timestamp(now)
        try:
            if self.frame is None:
                raise ValueError(self.weather_error or "Site weather is unavailable.")
            self.weather=sample_weather(self.frame,self.meta,self.stamp,live=self.mode=="Live site clock")
            self.weather_error=None
        except (ValueError,KeyError,RuntimeError) as exc:
            self.weather=None
            self.weather_error=str(exc)
        if self.weather is None:
            sun=solar_position(self.config,self.stamp)
            self.model={"tilt":0.,"azimuth":90.,"sun_elevation":float(sun.apparent_elevation),
                "sun_azimuth":float(sun.azimuth),"state":"WEATHER UNAVAILABLE","pv_dc_kw":None,
                "soc":self.config.soc_initial,"totals":{}}
            return
        elapsed=0 if self.energy_last is None else (self.stamp-self.energy_last).total_seconds()
        if elapsed<0 or elapsed>6*3600:
            self.reset_energy()
            elapsed=0
        self.model=advance_plant(self.config,self.stamp,self.weather,self.deployed,self.plant,
            max(elapsed,0),moving=self.moving)
        self.energy_last=self.stamp
        self.history.append({"time":self.stamp,"PV DC":self.model["pv_dc_kw"],
            "Users AC":self.model["user_served_kw"],"SOC (%)":self.model["soc"]*100})
        self.history=self.history[-240:]

    def snapshot(self):
        return {"config":self.config.to_dict(),"simulated_time":str(self.stamp),"clock_mode":self.mode,
            "deployment_progress":self.progress,"mechanical_phase":phase(self.progress),
            "hatch_angle_deg":hatch_angle(self.progress),"weather":self.weather,
            "weather_provenance":self.meta,"plant":self.model,
            "modules":[{"id":p.number,"centre_m":p.center,"corners_m":p.vertices.tolist()}
                for p in module_poses(self.config,self.progress,self.model.get("tilt",0),self.model.get("azimuth",90))]}
