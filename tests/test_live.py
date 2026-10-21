from dataclasses import replace
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from solar_model.config import Config
from solar_model.mechanics import module_poses, layout, project_shadow, phase
from solar_model.live_weather import sample_weather, parse_feed
from solar_model.live_simulation import instant_plant, advance_plant, solar_position
from solar_model.weather import demo_weather, prepare_weather
from solar_model.pv import simulate_pv
from solar_model.dispatch import simulate_dispatch
from tests.weather_fixture import forecast_fixture


def weather_at_noon():
    frame,meta=forecast_fixture()
    noon=frame.index[24]+pd.Timedelta(hours=12)
    return noon,sample_weather(frame,meta,noon)


@pytest.mark.parametrize("failure",["mkdir","write"])
def test_provider_weather_stays_usable_when_disk_cache_is_unwritable(monkeypatch,failure):
    import solar_model.live_weather as weather
    c=Config()
    frame,_=forecast_fixture()
    payload={"timezone":c.timezone,"latitude":c.latitude,"longitude":c.longitude,
        "hourly":{"time":frame.index.tz_localize(None).strftime("%Y-%m-%dT%H:%M").tolist(),
            **{source:(frame[target]/100 if target=="pressure" else frame[target]).tolist()
                for source,target in weather.VARIABLES.items()}}}

    class Response:
        url="https://api.open-meteo.com/v1/forecast?latitude=-1.2864&longitude=36.8172"
        def raise_for_status(self):
            pass
        def json(self):
            return payload

    class DeniedFile:
        def exists(self):
            return False
        def write_text(self,*args,**kwargs):
            raise PermissionError("Weather cache is read-only")

    class Cache:
        def mkdir(self,*args,**kwargs):
            if failure=="mkdir":
                raise PermissionError("Cache directory is read-only")
        def __truediv__(self,name):
            return DeniedFile()

    monkeypatch.setattr(weather,"CACHE",Cache())
    monkeypatch.setattr(weather.requests,"get",lambda *args,**kwargs:Response())
    actual,meta=weather.load_feed(c,force=True)
    assert actual.ghi.to_numpy()==pytest.approx(frame.ghi.to_numpy())
    assert actual.pressure.to_numpy()==pytest.approx(frame.pressure.to_numpy())
    assert meta["provider"]=="Open-Meteo"
    assert meta["cache_status"]=="Fetched from provider; disk cache unavailable"
    assert "read-only" in meta["cache_error"]


def test_all_modules_fit_inside_closed_container():
    c=Config()
    poses=module_poses(c,0)
    vertices=np.concatenate([p.vertices for p in poses])
    assert len(poses)==c.modules==36
    assert np.abs(vertices[:,0]).max()<c.dimensions[0]/2
    assert np.abs(vertices[:,1]).max()<c.dimensions[1]/2
    assert vertices[:,2].min()>.26
    assert vertices[:,2].max()<c.dimensions[2]+.26
    assert len(set(p.center for p in poses))==c.modules
    assert layout(c)["packed_top_m"]<c.dimensions[2]+.26


def test_deployment_has_finite_geometry_and_valid_extent():
    c=Config()
    for p in np.linspace(0,1,21):
        poses=module_poses(c,p,20,90)
        vertices=np.concatenate([m.vertices for m in poses])
        assert np.isfinite(vertices).all()
        assert vertices[:,2].min()>0
    d=layout(c)
    assert np.abs(vertices[:,0]).max()<d["fence_half_x"]
    assert np.abs(vertices[:,1]).max()<d["fence_half_y"]
    assert phase(0)=="TRANSPORT LOCKED"
    assert phase(1)=="DEPLOYED / LOCKED"


def test_shadow_follows_sun_vector_and_disappears_at_night():
    points=np.array([[0,0,2],[1,0,2],[1,1,2],[0,1,2]])
    shadow=project_shadow(points,45,90,0)
    assert shadow[:,0]==pytest.approx(points[:,0]-2)
    assert shadow[:,1]==pytest.approx(points[:,1])
    assert shadow[:,2]==pytest.approx(0)
    assert project_shadow(points,-5,90) is None


def test_clock_timezone_invariance():
    c=Config()
    east=pd.Timestamp("2026-10-20T12:00:00+03:00")
    utc=east.tz_convert("UTC")
    assert solar_position(c,east).apparent_elevation==pytest.approx(solar_position(c,utc).apparent_elevation)


def test_weather_sampling_interpolates_and_rejects_outside_window():
    frame,meta=forecast_fixture()
    a=frame.index[36]
    sample=sample_weather(frame,meta,a+pd.Timedelta(minutes=30))
    assert sample["ghi"]==pytest.approx((frame.ghi.iloc[36]+frame.ghi.iloc[37])/2)
    with pytest.raises(ValueError,match="outside"):
        sample_weather(frame,meta,frame.index[-1]+pd.Timedelta(hours=2))


def test_packed_panels_cannot_deliver_power():
    c=Config()
    when,weather=weather_at_noon()
    _,packed,pose=instant_plant(c,when,weather,False)
    _,deployed,_=instant_plant(c,when,weather,True)
    assert packed.pv_dc_kw.iloc[0]==0
    assert deployed.pv_dc_kw.iloc[0]>0
    assert pose["state"]=="TRANSPORT LOCKED"


def test_live_wind_stow_has_recovery_hysteresis():
    c=Config()
    when,weather=weather_at_noon()
    _,_,pose=instant_plant(c,when,{**weather,"gust_ms":15},True)
    assert pose["wind_latched"]
    _,_,pose=instant_plant(c,when,{**weather,"gust_ms":8},True,pose,elapsed_seconds=600)
    assert pose["wind_latched"]
    _,_,pose=instant_plant(c,when,{**weather,"gust_ms":8},True,pose,elapsed_seconds=600)
    assert not pose["wind_latched"]


def test_stateful_dispatch_matches_unsplit_run():
    c=Config()
    w,m=demo_weather(c,1)
    w=prepare_weather(w,m,c)
    pv=simulate_pv(w,c)
    whole=simulate_dispatch(w,pv,c)
    first,state=simulate_dispatch(w.iloc[:40],pv.iloc[:40],c,return_state=True)
    second,state=simulate_dispatch(w.iloc[40:],pv.iloc[40:],c,initial_state=state,return_state=True)
    joined=pd.concat([first,second])
    assert joined.soc.to_numpy()==pytest.approx(whole.soc.to_numpy())
    assert joined.battery_temp_c.to_numpy()==pytest.approx(whole.battery_temp_c.to_numpy())


def test_live_session_conserves_power_and_retains_storage():
    c=Config()
    when,weather=weather_at_noon()
    state={}
    first=advance_plant(c,when,weather,False,state,60)
    second=advance_plant(c,when+pd.Timedelta(minutes=1),weather,False,state,60)
    assert second["soc"]<first["soc"]
    assert second["totals"]["pv_kwh"]==0
    assert abs(second["dc_balance_residual_kw"])<1e-10
    generated=advance_plant(c,when+pd.Timedelta(minutes=2),weather,True,state,60)
    assert generated["totals"]["pv_kwh"]>0
    assert abs(generated["dc_balance_residual_kw"])<1e-10


def test_moving_array_uses_drive_power_while_remaining_isolated():
    c=Config()
    when,weather=weather_at_noon()
    sample=advance_plant(c,when,weather,False,{},1,moving=True)
    assert sample["pv_dc_kw"]==0
    assert sample["tracker_kw"]==pytest.approx(c.tracker_kw)


def test_paused_manual_study_does_not_create_energy():
    c=Config()
    when,weather=weather_at_noon()
    state={}
    initial=advance_plant(c,when,weather,True,state,0)
    second=advance_plant(c,when,weather,True,state,0)
    assert initial["soc"]==second["soc"]==c.soc_initial
    assert second["totals"]["pv_kwh"]==0
    assert second["totals"]["served_kwh"]==0


def test_scene_renders_a_real_image():
    from solar_model.scene import render_scene
    data=render_scene(Config(),1,15,90,45,240,size=(480,300),landscape=False)
    image=np.asarray(Image.open(BytesIO(data)))
    assert image.shape[:2]==(300,480)
    assert image.std()>15
