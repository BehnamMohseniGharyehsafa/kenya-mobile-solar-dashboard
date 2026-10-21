"""Detailed, Python-authored VTK scene with explicit mechanical geometry.

Landscape is procedural illustration. Shadows are analytical projections onto
the local flat compound plane, so the browser and server see the same shadows.
"""
from collections import defaultdict
from functools import lru_cache
from io import BytesIO

import numpy as np
from PIL import Image
import pyvista as pv
from scipy.spatial import ConvexHull

from .mechanics import layout, module_poses, project_shadow, smoothstep, sun_vector, hatch_angle
from .landscape import terrain as _terrain, vegetation, FOLIAGE, BARK, STONE
from .equipment import panel_housing,display_mesh,button_mesh,rotor_mesh,BUTTONS
from .sky import add_sun

PALETTE = {"shell":"#e5e8df", "rib":"#c8cfc9", "steel":"#697e82", "dark":"#163542",
    "pv":"#174365", "cell":"#286183", "glass":"#3b789a", "copper":"#b88450",
    "battery":"#2c5764", "green":"#64d9ad", "amber":"#f5bb58", "concrete":"#b5b7a9"}


class Geometry:
    def __init__(self):
        self.parts = defaultdict(list)
        self.wires = defaultdict(list)

    def add(self, mesh, color, kind="solid"):
        (self.wires if kind == "wire" else self.parts)[color].append(mesh)

    def box(self, center, size, color):
        if min(size) > 1e-6:
            self.add(pv.Cube(center=center,x_length=size[0],y_length=size[1],z_length=size[2]),color)

    def tube(self, start, end, radius, color, sides=8):
        start,end = np.array(start),np.array(end)
        if np.linalg.norm(end-start)>1e-6:
            self.add(pv.Cylinder(center=(start+end)/2,direction=end-start,radius=radius,
                height=np.linalg.norm(end-start),resolution=sides),color)

    def line(self, points, color):
        self.add(pv.lines_from_points(np.asarray(points)),color,"wire")

    def ellipsoid(self, center, radii, color, resolution=14):
        mesh = pv.Sphere(radius=1,theta_resolution=resolution,phi_resolution=resolution)
        mesh.points *= np.asarray(radii)
        mesh.translate(center,inplace=True)
        self.add(mesh,color)

    def polygon(self, vertices, color):
        points=np.asarray(vertices)
        self.add(pv.PolyData(points,np.r_[len(points),np.arange(len(points))]),color)

    def merged(self):
        return {color:pv.merge(parts,merge_points=False) for color,parts in self.parts.items()}, {
            color:pv.merge(parts,merge_points=False) for color,parts in self.wires.items()}


def _fence(g,d):
    hx,hy=d["fence_half_x"],d["fence_half_y"]
    sides=[((-hx,-hy),(-hx,hy)),((hx,-hy),(hx,hy)),((-hx,hy),(hx,hy)),
        ((-hx,-hy),(-1.7,-hy)),((1.7,-hy),(hx,-hy))]
    for start,end in sides:
        a,b=np.array(start),np.array(end)
        length=np.linalg.norm(b-a)
        tangent=(b-a)/length
        for t in np.linspace(0,length,int(np.ceil(length/2.5))+1):
            x,y=a+t*tangent
            g.tube((x,y,0),(x,y,2.20),.038,"#bac3b8")
            g.box((x,y,.03),(.18,.18,.06),"#9c9e90")
        for z in (.18,2.04):
            g.tube((*a,z),(*b,z),.022,"#9eada5")
        # Slender diamond-chain lines retain an open view into the compound.
        for t in np.arange(-1.9,length+.4,.28):
            for slope in (-1,1):
                bottom=max(0,-t/slope) if slope>0 else max(0,(t-length))
                top=min(1.85,length-t) if slope>0 else min(1.85,t)
                if top>bottom:
                    q0=a+(t+slope*bottom)*tangent
                    q1=a+(t+slope*top)*tangent
                    g.line([(*q0,.20+bottom),(*q1,.20+top)],"#b3bdb0")
    # Two closed gate leaves; the centre seam is visible.
    for x in (-.85,.85):
        for z in (.24,1.96):
            g.tube((x-.83,-hy,z),(x+.83,-hy,z),.026,"#93a7a1")
        for a in (x-.83,x+.83):
            g.tube((a,-hy,.24),(a,-hy,1.96),.026,"#93a7a1")
        for a in np.arange(x-.75,x+.8,.18):
            g.line([(a,-hy,.25),(a,-hy,1.95)],"#a8b7ad")
    g.box((1.95,-hy,1.48),(.48,.035,.34),PALETTE["dark"])
    for x,y in [(-hx,-hy),(hx,-hy),(-hx,hy),(hx,hy)]:
        g.tube((x,y,0),(x,y,3.3),.045,PALETTE["steel"])
        g.box((x,y,3.25),(.32,.23,.10),PALETTE["dark"])
        g.box((x,y-.02,3.19),(.24,.17,.025),"#ffdda2")


def _equipment(g,c,cutaway):
    length,width,height=c.dimensions
    base=.26
    # Discrete battery modules and busbars, visible in cutaway mode.
    for y in (-.65,.05,.70):
        center=(-length/2+.55,y,base+.96)
        g.box(center,(.72,.54,1.7),PALETTE["dark"])
        for z in np.arange(base+.28,base+1.7,.235):
            g.box((center[0]+.02,y,z),(.75,.48,.195),PALETTE["battery"])
            g.box((center[0]+.405,y,z),(.018,.31,.09),"#9ba8a0")
            g.ellipsoid((center[0]+.425,y+.15,z),(.017,.017,.017),PALETTE["green"],8)
        g.tube((center[0]+.45,y-.17,base+.15),(center[0]+.45,y-.17,base+1.6),.018,PALETTE["copper"])
    g.box((length/2-.55,0,base+.92),(.7,1.8,1.72),"#d4d9cd")
    for y in (-.55,.55):
        g.box((length/2-.94,y,base+1.2),(.035,.57,.36),PALETTE["dark"])
        g.box((length/2-.97,y,base+1.2),(.018,.43,.22),"#3f7b84")
        for z in (.48,.57,.66):
            g.box((length/2-.97,y,base+z),(.02,.46,.025),"#586c6c")
    # Floor cable trays, physically separate positive/negative cable colours.
    for y,color in [(-.90,"#b55c43"),(-.80,"#314657")]:
        g.tube((-length/2+.8,y,base+.08),(length/2-.8,y,base+.08),.026,color)
    # Exterior HVAC cabinet: condenser fan and grille, clear service access.
    x=length/2+.32
    g.box((x,-.50,base+1.03),(.55,1.05,.90),PALETTE["shell"])
    fan=pv.Cylinder(center=(x+.28,-.50,base+1.05),direction=(1,0,0),radius=.32,height=.008,resolution=36)
    g.add(fan,PALETTE["dark"])
    for z in np.arange(base+.79,base+1.36,.07):
        g.tube((x+.37,-.78,z),(x+.37,-.22,z),.006,"#9aa9a4")
    g.tube((x+.37,-.5,base+.75),(x+.37,-.5,base+1.35),.008,"#a7b0a6")
    g.ellipsoid((x+.37,-.5,base+1.05),(.025,.06,.06),"#a3b6b6",12)
    angles=np.linspace(0,2*np.pi,49)
    ring=np.c_[np.full(49,x+.37),-.5+.326*np.cos(angles),base+1.05+.326*np.sin(angles)]
    g.add(pv.lines_from_points(ring).tube(radius=.012,n_sides=8),"#9aa9a4")


@lru_cache(maxsize=12)
def cover_geometry(c,detail=True):
    """The near wall/nameplate hidden by cutaway, as a separate cached layer."""
    g=Geometry()
    length,width,height=c.dimensions
    y=-width/2
    g.box((0,y,.26+height/2),(length,.075,height),PALETTE["shell"])
    if detail:
        for x in np.arange(-length/2+.12,length/2,.115):
            g.box((x,y-.045,.26+height/2),(.037,.035,height-.16),PALETTE["rib"])
    g.box((-length*.18,y-.075,1.40),(length*.47,.025,.62),PALETTE["dark"])
    text=pv.Text3D("SOLAR / KENYA",depth=.005,height=.18)
    text.rotate_x(90,inplace=True)
    text.translate((-length*.18,y-.096,1.36),inplace=True)
    g.add(text,"#e6dfc8")
    return g.merged()


@lru_cache(maxsize=12)
def landscape_geometry(c):
    """Vegetation/rocks are independent of the permanent installation geometry."""
    return vegetation(c)


@lru_cache(maxsize=12)
def static_geometry(c,landscape=True,cutaway=False,detail=True):
    d=layout(c)
    terrain,_=_terrain(c,d)
    g=Geometry()
    length,width,height=c.dimensions
    base=.26
    g.box((0,0,.10),(length+2.1,width+2.25,.22),PALETTE["concrete"])
    for j in range(2):
        g.box((length/2+1.35+j*.32,-.45,.055-j*.02),(.55,1.25,.10-j*.03),"#a6aa9c")
    g.box((0,0,base),(length,width,.17),PALETTE["steel"])
    for y in (width/2,):
        g.box((0,y,base+height/2),(length,.075,height),PALETTE["shell"])
        if detail:
            for x in np.arange(-length/2+.12,length/2,.115):
                g.box((x,y+np.sign(y)*.045,base+height/2),(.037,.035,height-.16),PALETTE["rib"])
    for x in (-length/2,length/2):
        g.box((x,0,base+height/2),(.075,width,height),PALETTE["shell"])
        for y in (-.55,.55):
            g.tube((x+np.sign(x)*.05,y,base+.17),(x+np.sign(x)*.05,y,base+height-.15),.021,PALETTE["steel"])
        for z in (base+.15,base+height-.15):
            g.tube((x+.05,-width/2,z),(x+.05,width/2,z),.045,PALETTE["steel"])
    for x in (-length/2,length/2):
        for y in (-width/2,width/2):
            g.box((x,y,base+height/2),(.105,.105,height),"#9baaa6")
            g.box((x,y,base-.08),(.25,.25,.25),PALETTE["dark"])
    if not cutaway:
        for kind,groups in zip(("solid","wire"),cover_geometry(c,detail)):
            for color,mesh in groups.items():
                g.add(mesh,color,kind)
    _equipment(g,c,cutaway)
    _fence(g,d)
    # A sheltered operator cabinet, hardwired stop, telemetry and weather mast.
    g.add(panel_housing(c),"#64797c")
    mx,my=-length/2-.6,width/2+.45
    g.tube((mx,my,0),(mx,my,5.0),.035,PALETTE["steel"])
    g.tube((mx,my,4.85),(mx+.6,my,4.85),.022,PALETTE["steel"])
    for a in (0,120,240):
        r=np.radians(a)
        g.ellipsoid((mx+.6+.18*np.cos(r),my+.18*np.sin(r),4.85),(.065,.065,.04),PALETTE["dark"],10)
    g.box((mx,my,3.4),(.26,.23,.22),"#f0eee2")
    # North marker on the compound floor.
    g.tube((-d["fence_half_x"]+1,-d["fence_half_y"]+2,.04),(-d["fence_half_x"]+1,-d["fence_half_y"]+4,.04),.035,"#ece5d2")
    g.line([(-d["fence_half_x"]+.6,-d["fence_half_y"]+3.5,.04),
        (-d["fence_half_x"]+1,-d["fence_half_y"]+4,.04),
        (-d["fence_half_x"]+1.4,-d["fence_half_y"]+3.5,.04)],"#ece5d2")
    if landscape:
        for kind,groups in zip(("solid","wire"),landscape_geometry(c)):
            for color,mesh in groups.items():
                g.add(mesh,color,kind)
    return terrain,*g.merged()


def dynamic_geometry(c,progress,tilt,azimuth,elevation,sun_azimuth,shadows=True,cloud_pct=0):
    g=Geometry()
    length,width,height=c.dimensions
    roof_z=height+.26
    hatch=np.radians(hatch_angle(progress))
    for sign in (-1,1):
        hinge=np.array([0,sign*width/2,roof_z])
        inward=np.array([0,-sign*np.cos(hatch),np.sin(hatch)])
        vertices=np.array([hinge+np.array([sx*length/2,0,0])+v*width/2*inward for sx,v in [(-1,0),(1,0),(1,1),(-1,1)]])
        g.polygon(vertices,PALETTE["shell"])
        g.tube(vertices[0],vertices[1],.025,PALETTE["steel"])
        g.tube(vertices[2],vertices[3],.025,PALETTE["steel"])
    poses=module_poses(c,progress,tilt,azimuth)
    for pose in poses:
        v=pose.vertices
        normal=np.cross(v[1]-v[0],v[3]-v[0])
        normal/=np.linalg.norm(normal)
        # Aluminium perimeter and individual silicon-cell grid.
        g.polygon(v-normal*.025,PALETTE["steel"])
        g.polygon(v+normal*.003,PALETTE["pv"])
        u,vaxis=v[1]-v[0],v[3]-v[0]
        for a in range(6):
            for b in range(12):
                if a%2==0 or b%2==0:
                    continue
                x0,x1=(a+.08)/6,(a+.92)/6
                y0,y1=(b+.04)/12,(b+.96)/12
                quad=[v[0]+x*u+y*vaxis+normal*.006 for x,y in [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]]
                g.polygon(quad,PALETTE["cell"])
        for a in np.linspace(0,1,7):
            g.line([v[0]+a*u+normal*.009,v[3]+a*u+normal*.009],"#8aaeb4")
        for b in np.linspace(0,1,13):
            g.line([v[0]+b*vaxis+normal*.009,v[1]+b*vaxis+normal*.009],"#8aaeb4")
        for j in range(4):
            g.line([v[j],v[(j+1)%4]],"#c3d2cc")
        if progress>.32:
            x,y,z=pose.center
            g.tube((x,y,.27),(x,y,z-.04),.032,PALETTE["steel"])
            if progress>.85:
                g.box((x,y,.07),(.38,.38,.12),"#9c9d8c")
                g.tube((x-.28,y,z-.5),(x,y,.16),.018,PALETTE["steel"])
        if shadows and elevation>.5:
            shadow=project_shadow(pose.vertices,elevation,sun_azimuth,.018)
            g.polygon(shadow,"#3b4237")
    # Telescopic deployment rails and the protected cable chain.
    extension=smoothstep((progress-.32)/.38)
    d=layout(c)
    for sign in (-1,1):
        for x in (-length*.30,length*.30):
            end=sign*(width/2+(d["fence_half_y"]-width/2-3)*extension)
            g.tube((x,sign*width/2,.33),(x,end,.33),.055,PALETTE["steel"])
        if extension>.05:
            g.line([(0,sign*width/2,.35),(0,sign*(width/2+6*extension),.35)],"#df9d49")
    if shadows and elevation>.5:
        vertices=np.array([[x,y,z] for x in (-length/2,length/2) for y in (-width/2,width/2) for z in (.27,roof_z)])
        projected=project_shadow(vertices,elevation,sun_azimuth,.012)
        hull=ConvexHull(projected[:,:2])
        g.polygon(projected[hull.vertices],"#454a3d")
    return g.merged()


CAMERAS={
    "Deployment camera":((26,-32,23),(0,0,1.7)),
    "Site overview":((26,-32,23),(0,0,1.7)),
    "Western horizon":((45,12,10),(0,0,4)),
    "Container detail":((11,-12,7.5),(0,0,1.7)),
    "Mechanism inspection":((10,5,9),(0,0,2.5)),
    "Battery & cooling":((-9,-8,5),(0,0,1.4)),
    "Top plan":((0,-.1,43),(0,0,0)),
    "Control panel & fan":((7.6,-.35,2.3),(3.28,.05,1.5)),
}


def camera_pose(config,name):
    position,focus=CAMERAS[name]
    if name=="Control panel & fan":
        shift=np.array([config.dimensions[0]/2-3.029,0,0])
        return np.asarray(position)+shift,np.asarray(focus)+shift
    return position,focus


def build_plotter(c,progress,tilt,azimuth,elevation,sun_azimuth,cloud_pct=0,
                  camera="Site overview",cutaway=False,landscape=True,shadows=True,dimensions=False,
                  size=(1440,810),stamp="",condition="",dynamic=True,annotations=True,option_layers=False):
    plotter=pv.Plotter(off_screen=True,window_size=size,lighting="none")
    night=elevation<=0
    plotter.set_background("#263b4a" if night else "#91acb7",top="#0d1828" if night else "#c3d5d6")
    terrain,solids,wires=static_geometry(c,False if option_layers else landscape,True if option_layers else cutaway,True)
    plotter.add_mesh(terrain,scalars="terrain_rgb",rgb=True,show_scalar_bar=False,
        ambient=.35 if night else .30,diffuse=.75,smooth_shading=True)
    def add(groups,prefix=None,visible=True):
        for color,mesh in groups[0].items():
            is_shadow=color in ("#3b4237","#454a3d")
            emissive=color in ("#ffe4a0","#ffdda2")
            field=mesh.active_scalars_name
            colored=field in ("foliage_rgb","grass_rgb","stone_rgb","contact_rgba","equipment_rgb")
            appearance={"scalars":field,"rgb":True} if colored else {"color":color}
            contact=field=="contact_rgba"
            grass=field=="grass_rgb"
            plotter.add_mesh(mesh,**appearance,show_scalar_bar=False,show_edges=False,
                name=f"{prefix}-{color}" if prefix else None,
                ambient=1 if is_shadow or emissive or contact or grass else .46 if color==FOLIAGE else .43 if night else .28,
                lighting=not (contact or grass),
                diffuse=0 if is_shadow or contact or grass else .54 if color==FOLIAGE else .75,
                specular=.23 if color in (PALETTE["pv"],PALETTE["steel"]) else 0 if color==FOLIAGE else .03,
                specular_power=26,opacity=.46 if is_shadow else 1,
                smooth_shading=color in (FOLIAGE,BARK,STONE))
            if prefix:
                plotter.renderer.actors[f"{prefix}-{color}"].visibility=visible
        for color,mesh in groups[1].items():
            plotter.add_mesh(mesh,color=color,line_width=1.1,lighting=False,opacity=.68)
    add((solids,wires))
    if option_layers:
        add(cover_geometry(c),"option-cover",not cutaway)
        add(landscape_geometry(c),"option-landscape",landscape)
    if dynamic:
        add(dynamic_geometry(c,progress,tilt,azimuth,elevation,sun_azimuth,shadows,cloud_pct))
        add_sun(plotter,elevation,sun_azimuth)
    plotter.add_mesh(display_mesh(c).copy(),scalars="screen_rgb",rgb=True,show_scalar_bar=False,
        lighting=False,name="equipment-display")
    plotter.add_mesh(rotor_mesh(c),color="#c8d7d8",ambient=.45,diffuse=.6,specular=.5,
        specular_power=32,name="equipment-rotor")
    for key,(_,color) in BUTTONS.items():
        plotter.add_mesh(button_mesh(c,key),color=color,ambient=.5,specular=.35,
            specular_power=25,name=f"equipment-button-{key}")
    direction=sun_vector(max(elevation,12),sun_azimuth)
    sunlight=pv.Light(position=direction*100,focal_point=(0,0,0),light_type="scene light",
        intensity=.25 if night else max(.30,1.05-cloud_pct*.006),color="#8aa7d1" if night else "#fff1d3")
    plotter.add_light(sunlight)
    fill=pv.Light(position=(-35,-25,35),focal_point=(0,0,0),intensity=.30 if night else .38,color="#bbd7e9")
    plotter.add_light(fill)
    if night:
        plotter.add_light(pv.Light(position=(3,-4,5),focal_point=(0,0,0),intensity=.65,color="#ffe2ad"))
    if cloud_pct>30 and landscape and not night:
        clouds=Geometry()
        for i in range(min(9,int(cloud_pct/12))):
            x=-24+i*6.5
            clouds.ellipsoid((x,22+(i%3)*6,16+(i%2)*3),(4.2,2.1,1.05),"#d4d9d4",16)
        for color,mesh in clouds.merged()[0].items():
            plotter.add_mesh(mesh,color=color,opacity=.45,ambient=.8)
    pos,focus=camera_pose(c,camera)
    if camera=="Deployment camera":
        mix=smoothstep((progress-.28)/.52)
        pos=(1-mix)*np.array(CAMERAS["Container detail"][0])+mix*np.array(CAMERAS["Site overview"][0])
        focus=(0,0,1.7)
    scale=max(1,max(layout(c)["fence_half_x"],layout(c)["fence_half_y"])/13)
    pos=np.array(pos)*scale if camera in ("Site overview","Top plan") else pos
    plotter.camera_position=[pos,focus,(0,0,1)]
    plotter.camera.view_angle=43
    plotter.camera.clipping_range=(.1,350)
    plotter.enable_anti_aliasing("fxaa")
    if dimensions:
        plotter.show_bounds(bounds=(-c.dimensions[0]/2,c.dimensions[0]/2,-c.dimensions[1]/2,c.dimensions[1]/2,.26,c.dimensions[2]+.26),
            grid=False,location="outer",color="#e1e6d9",font_size=11,
            xtitle="East / m",ytitle="North / m",ztitle="Height / m")
    # Restrained viewport labels; technical values remain in the live UI.
    if annotations:
        plotter.add_text(f"{c.site.upper()}  /  FIELD SYSTEM 01",position="upper_left",font_size=12,color="#f2eee0",shadow=False)
        if stamp:
            plotter.add_text(stamp,position="lower_left",font_size=10,color="#e3eadf",shadow=False)
        plotter.add_text("NIGHT OPERATION" if night else condition.upper() or "SOLAR GEOMETRY",position="upper_right",font_size=10,color="#f1d899",shadow=False)
    return plotter


def render_scene(c,progress,tilt,azimuth,elevation,sun_azimuth,**kwargs):
    plotter=build_plotter(c,progress,tilt,azimuth,elevation,sun_azimuth,**kwargs)
    try:
        image=plotter.screenshot(return_img=True)
        output=BytesIO()
        Image.fromarray(image).save(output,format="PNG",optimize=False)
        return output.getvalue()
    finally:
        plotter.close()
