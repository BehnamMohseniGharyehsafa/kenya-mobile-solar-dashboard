"""Small, reusable HMI and fan meshes; no images, external assets or per-leaf actors."""
from functools import lru_cache
import math

import numpy as np
import pyvista as pv
from dash import html


BUTTONS={"start":(.42,"#58d59b"),"hold":(.65,"#f5c24d"),"stop":(.88,"#ef6655")}
SEGMENTS={"0":"abcdef","1":"bc","2":"abdeg","3":"abcdg","4":"bcfg",
    "5":"acdfg","6":"acdefg","7":"abc","8":"abcdefg","9":"abcdfg","-":"g"," ":"",".":"p"}


def fan_centre(config):
    return (config.dimensions[0]/2+.615,-.50,1.31)


def _text(text,height,origin):
    mesh=pv.Text3D(text,depth=.001,height=height)
    p=np.asarray(mesh.points).copy()
    p[:,:2]-=p[:,:2].min(axis=0)
    # Text's XY plane becomes the container's +X face (right = +Y, up = +Z).
    mesh.points=np.c_[origin[0]+p[:,2],origin[1]+p[:,0],origin[2]+p[:,1]]
    return mesh


def _colored(parts):
    for mesh,color in parts:
        rgb=tuple(int(color.lstrip("#")[i:i+2],16) for i in (0,2,4))
        mesh.cell_data["equipment_rgb"]=np.tile(np.array(rgb,np.uint8),(mesh.n_cells,1))
    return pv.merge([mesh for mesh,_ in parts],merge_points=False)


@lru_cache(maxsize=12)
def panel_housing(config):
    x=config.dimensions[0]/2
    parts=[]
    def box(center,size,color):
        parts.append((pv.Cube(center=center,x_length=size[0],y_length=size[1],z_length=size[2]),color))
    box((x+.09,.65,1.72),(.19,.84,1.12),"#35484e")
    box((x+.19,.65,1.72),(.025,.79,1.07),"#aebdb9")
    box((x+.21,.65,1.86),(.025,.70,.65),"#0b1921")
    box((x+.226,.65,1.86),(.012,.64,.56),"#10332d")
    for y in (.30,1.0):
        for z in (1.23,2.21):
            parts.append((pv.Cylinder(center=(x+.212,y,z),direction=(1,0,0),radius=.013,height=.008,resolution=6),"#54676b"))
    for text,h,y,z in [("PV / EMS",.035,.32,2.14),("PV",.034,.36,2.01),
        ("SOC",.034,.36,1.90),("BAT",.034,.36,1.79),("FAN",.034,.36,1.68),
        ("kW",.023,.88,2.01),("%",.023,.88,1.90),("C",.023,.88,1.79),("rpm",.023,.88,1.68),
        ("START",.026,.36,1.20),("HOLD",.026,.60,1.20),("STOP",.026,.83,1.20)]:
        parts.append((_text(text,h,(x+.24,y,z)),"#9fe6c5" if z>1.6 else "#132c31"))
    for key,(y,_) in BUTTONS.items():
        parts.append((pv.Cylinder(center=(x+.222,y,1.37),direction=(1,0,0),radius=.082 if key=="stop" else .063,
            height=.018,resolution=24),"#e6bd45" if key=="stop" else "#263f45"))
    return _colored(parts)


def button_mesh(config,key):
    y,_=BUTTONS[key]
    return pv.Cylinder(center=(config.dimensions[0]/2+.25,y,1.37),direction=(1,0,0),
        radius=.061 if key=="stop" else .049,height=.048 if key=="stop" else .025,resolution=24)


@lru_cache(maxsize=12)
def display_mesh(config):
    # A fixed topology of 160 quads. Only 480 colour bytes change on a reading.
    points=[]
    rects={"a":(.005,.055,.028,.061),"b":(.026,.032,.032,.057),"c":(.026,.004,.032,.029),
        "d":(.005,0,.028,.006),"e":(0,.004,.006,.029),"f":(0,.032,.006,.057),
        "g":(.005,.027,.028,.034),"p":(.029,0,.035,.006)}
    for row in range(4):
        for digit in range(5):
            y,z=.57+digit*.056,1.998-row*.11
            for y0,z0,y1,z1 in rects.values():
                points.extend([(config.dimensions[0]/2+.24,y+y0,z+z0),(config.dimensions[0]/2+.24,y+y1,z+z0),
                    (config.dimensions[0]/2+.24,y+y1,z+z1),(config.dimensions[0]/2+.24,y+y0,z+z1)])
    mesh=pv.PolyData(np.asarray(points,np.float32),np.c_[np.full(160,4),np.arange(640).reshape(-1,4)])
    mesh.cell_data["screen_rgb"]=display_colors(["-----"]*4)
    return mesh


def display_colors(lines):
    bits=[letter in SEGMENTS.get(char,"") for line in lines for char in line.ljust(5)[:5] for letter in "abcdefgp"]
    return np.where(np.asarray(bits)[:,None],np.array([134,255,205],np.uint8),np.array([22,61,49],np.uint8))


def display_lines(model,rpm):
    def number(value,decimals=1):
        if value is None or not math.isfinite(value):
            return "-----"
        text=f"{value:05.{decimals}f}"
        return text if len(text)<=5 else f"{value:05.1f}" if abs(value)<1000 else "-----"
    return [number(model.get("pv_dc_kw"),2),number(model.get("soc",0)*100),
        number(model.get("battery_temp_c")),f"{rpm:04d} "]


def cooling_rpm(model):
    # Illustrative demand indication, not an OEM fan curve or a measured RPM.
    if model.get("cooling_kw",0)<=.001:
        return 0
    return {"COMPRESSOR":900,"FREE COOLING":600}.get(model.get("cooling_state"),0)


def rotor_mesh(config):
    centre=np.asarray(fan_centre(config))
    parts=[]
    profile=np.array([[.002,.075,-.025],[.012,.22,-.080],[.022,.295,-.025],
        [.014,.27,.055],[.003,.13,.075],[0,.075,.025]],np.float32)
    for angle in (0,120,240):
        a=math.radians(angle)
        rotation=np.array([[1,0,0],[0,math.cos(a),-math.sin(a)],[0,math.sin(a),math.cos(a)]])
        parts.append(pv.PolyData(profile@rotation.T+centre,np.r_[6,np.arange(6)]))
    return pv.merge(parts,merge_points=False).triangulate()


def rotor_matrix(centre,angle):
    _,y,z=centre
    a=math.radians(angle)
    c,s=math.cos(a),math.sin(a)
    return [1.,0.,0.,0., 0.,c,s,0., 0.,-s,c,0., 0.,y-c*y+s*z,z-s*y-c*z,1.]


def inspector():
    def readout(label,identity,unit):
        return html.Div([html.Span(label),html.Strong("N/A",id=identity),html.Small(unit)],className="hmi-reading")
    def button(key,label):
        return html.Button([html.Span(className="push-cap"),html.Span(label,id=f"hmi-{key}-label")],
            id=f"hmi-{key}",n_clicks=0,className=f"hmi-button hmi-{key}",title=label)
    return html.Details([html.Summary("HMI / COOLING · INSPECT"),
        html.Div([html.Div([html.Strong("PV / EMS"),html.Small("LOCAL OPERATOR STATION")],className="hmi-brand"),
            html.Div([html.Div("INITIALISING",id="hmi-state",className="hmi-state"),
                readout("PV OUTPUT","hmi-pv","kW DC"),readout("BATTERY SOC","hmi-soc","%"),
                readout("BATTERY TEMP","hmi-temp","°C"),readout("AC LOAD","hmi-load","kW"),
                html.Div("PV CONTACTOR · ISOLATED",id="hmi-contactor",className="hmi-contactor")],className="hmi-lcd"),
            html.Div([button("start","START"),button("hold","HOLD"),button("stop","E-STOP")],className="hmi-buttons"),
            html.Div([html.Div([html.Div([html.I(),html.I(),html.I()],className="fan-blades"),
                html.Span(className="fan-hub")],id="fan-indicator",className="fan-indicator"),
                html.Div([html.Strong("Cooling · automatic",id="hmi-cooling"),html.Div("0 rpm demand",id="hmi-rpm")])],className="hmi-cooling"),
            html.P("INITIALISING",id="hmi-notice",className="hmi-notice"),
            html.Small("Simulated controls. Fan RPM is assumed; rotor motion is slowed for inspection.",className="hmi-footnote")],className="hmi-enclosure")],
        id="equipment-inspector",className="equipment-inspector",open=False)
