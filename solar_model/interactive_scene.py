"""Persistent, batched VTK geometry for a low-draw-call WebGL scene."""
from io import BytesIO
import numpy as np
import pyvista as pv
from PIL import Image

from .mechanics import layout,module_geometry,smoothstep,hatch_angle,project_shadow,sun_vector
from .scene import build_plotter,CAMERAS,PALETTE
from .landscape import BARK


def _module_template(c):
    d=layout(c)
    w,length=d["module_width_m"],d["module_length_m"]
    vertices,colors=[],[]
    def quad(x0,y0,x1,y1,z,color):
        vertices.extend([(x0,y0,z),(x1,y0,z),(x1,y1,z),(x0,y1,z)])
        colors.append(color)
    quad(-w/2,-length/2,w/2,length/2,0,(190,205,201))
    quad(-w/2+.025,-length/2+.025,w/2-.025,length/2-.025,.005,(18,49,72))
    for a in range(6):
        for b in range(12):
            quad(-w/2+(a+.07)*w/6,-length/2+(b+.05)*length/12,
                -w/2+(a+.93)*w/6,-length/2+(b+.95)*length/12,.009,
                (29,79,111) if (a+b)%2 else (35,88,119))
    mesh=pv.PolyData(np.asarray(vertices,np.float32),
        np.c_[np.full(len(colors),4),np.arange(len(vertices)).reshape(-1,4)])
    mesh.cell_data["rgb"]=np.asarray(colors,np.uint8)
    return mesh


class InteractiveScene:
    def __init__(self,config,landscape=True,cutaway=False,camera="Site overview"):
        self.config=config
        self.plotter=build_plotter(config,0,0,90,40,150,camera=camera,landscape=landscape,
            cutaway=cutaway,dynamic=False,annotations=False,size=(1200,660),option_layers=True)
        self.landscape_actors=[a for name,a in self.plotter.renderer.actors.items() if name.startswith("option-landscape-")]
        self.cover_actors=[a for name,a in self.plotter.renderer.actors.items() if name.startswith("option-cover-")]
        self.option_actors=self.landscape_actors+self.cover_actors
        self.last_signature=None
        self.transforms_sent=0
        self.module_template=_module_template(config)
        self.post_template=pv.Cylinder(direction=(0,0,1),radius=.034,height=1,resolution=8)
        self.foot_template=pv.Cube(x_length=.38,y_length=.38,z_length=.12)
        self.rail_template=pv.Cylinder(direction=(0,1,0),radius=.055,height=1,resolution=8)
        length,width,height=config.dimensions
        self.roof_template=pv.Cube(center=(0,width/4,0),x_length=length,y_length=width/2,z_length=.065)
        # PyVista point access wraps the VTK array. Read each immutable template
        # once, rather than doing thousands of wrapper lookups per second.
        self.template_points={name:np.array(getattr(self,f"{name}_template").points,copy=True)
            for name in ("module","post","foot","roof","rail")}
        self.module_mesh=self._batch(self.module_template,config.modules)
        self.post_mesh=self._batch(self.post_template,config.modules)
        self.foot_mesh=self._batch(self.foot_template,config.modules)
        self.roof_mesh=self._batch(self.roof_template,2)
        self.rail_mesh=self._batch(self.rail_template,4)
        self.modules=[self.plotter.add_mesh(self.module_mesh,scalars="rgb",rgb=True,show_scalar_bar=False,
            ambient=.32,diffuse=.7,specular=.2,name="all-modules")]
        self.posts=[self.plotter.add_mesh(self.post_mesh,color=PALETTE["steel"],name="all-posts")]
        self.feet=[self.plotter.add_mesh(self.foot_mesh,color="#9c9d8c",name="all-feet")]
        self.hatches=[self.plotter.add_mesh(self.roof_mesh,color=PALETTE["shell"],name="both-hatches")]
        self.rails=[self.plotter.add_mesh(self.rail_mesh,color=PALETTE["steel"],name="all-rails")]
        self.shadow_mesh=pv.PolyData(np.zeros((config.modules*4,3),np.float32),
            np.c_[np.full(config.modules,4),np.arange(config.modules*4).reshape(-1,4)])
        self.shadow_actor=self.plotter.add_mesh(self.shadow_mesh,color="#3b4237",opacity=.42,lighting=False)
        self.box_shadow=pv.PolyData(np.zeros((8,3),np.float32),
            np.array([[4,0,1,3,2],[4,4,5,7,6],[4,0,1,5,4],[4,2,3,7,6],[4,0,2,6,4],[4,1,3,7,5]]))
        self.box_shadow_actor=self.plotter.add_mesh(self.box_shadow,color="#454a3d",opacity=.14,lighting=False)
        self.sun=self.plotter.add_mesh(pv.Sphere(radius=.6,theta_resolution=16,phi_resolution=12),color="#ffe4a0",lighting=False)
        self.light=self.plotter.renderer.lights[0]
        self.update(0,0,90,40,150)
        d=layout(config)
        for name,actor in self.plotter.renderer.actors.items():
            bounds=actor.GetBounds()
            if max(abs(bounds[0]),abs(bounds[1]))>d["fence_half_x"]+3 or max(abs(bounds[2]),abs(bounds[3]))>d["fence_half_y"]+3:
                actor.SetUseBounds(False)
            # Bark spans each whole tree from ground to crown. Including this
            # compact layer in camera bounds prevents far-plane cuts leaving
            # floating crowns after reset/orbit; distant terrain stays excluded.
            if name==f"option-landscape-{BARK}":
                actor.SetUseBounds(True)
        # Fit/reset focuses on the installation rather than the distant terrain,
        # projected shadows or the deliberately scaled sun marker.
        for actor in (self.sun,self.shadow_actor,self.box_shadow_actor):
            actor.SetUseBounds(False)

    @staticmethod
    def _batch(template,count):
        # One dataset/actor for the entire group, with fixed connectivity.
        return pv.merge([template.copy() for _ in range(count)],merge_points=False)

    @staticmethod
    def _set_points(mesh,points):
        points=np.asarray(points,np.float32).reshape(-1,3)
        if not np.array_equal(mesh.points,points):
            mesh.points=points

    def update(self,progress,tilt,azimuth,elevation,sun_azimuth,cloud=0,shadows=True):
        signature=(round(progress,5),round(tilt,2),round(azimuth,2),round(elevation,2),round(sun_azimuth,2),round(cloud/5),shadows)
        if signature==self.last_signature:
            return False
        old=self.last_signature
        self.last_signature=signature
        c=self.config
        centers,basis,vertices,_,_=module_geometry(c,progress,tilt,azimuth)
        self.module_centers,self.module_bases=centers,basis
        if old is None or signature[:3]!=old[:3]:
            template=self.template_points
            self._set_points(self.module_mesh,np.einsum("kj,nij->nki",template["module"],basis)+centers[:,None,:])
            scales=np.ones_like(centers)
            scales[:,2]=np.maximum(centers[:,2]-.31,.01)
            post_centers=centers.copy()
            post_centers[:,2]=(centers[:,2]+.23)/2
            self._set_points(self.post_mesh,template["post"][None,:,:]*scales[:,None,:]+post_centers[:,None,:])
            foot_centers=centers.copy()
            foot_centers[:,2]=.07
            self._set_points(self.foot_mesh,template["foot"][None,:,:]+foot_centers[:,None,:])
            self.posts[0].visibility=progress>.32
            self.feet[0].visibility=progress>.74
            length,width,height=c.dimensions
            angle=np.radians(hatch_angle(progress))
            roofs=[]
            for sign in (-1,1):
                basis=np.column_stack([(1,0,0),(0,-sign*np.cos(angle),np.sin(angle)),(0,-sign*np.sin(angle),-np.cos(angle))])
                roofs.append(template["roof"]@basis.T+[0,sign*width/2,height+.26])
            self._set_points(self.roof_mesh,np.concatenate(roofs))
            ext=smoothstep((progress-.32)/.38)
            distance=max((layout(c)["fence_half_y"]-width/2-3)*ext,.001)
            rails=[]
            for sign in (-1,1):
                for x in (-length*.30,length*.30):
                    rails.append(template["rail"]*np.array([1,distance,1])+[x,sign*(width/2+distance/2),.33])
            self._set_points(self.rail_mesh,np.concatenate(rails))
        visible=shadows and elevation>.5
        self.shadow_actor.visibility=self.box_shadow_actor.visibility=visible
        if visible:
            self._set_points(self.shadow_mesh,project_shadow(vertices.reshape(-1,3),elevation,sun_azimuth,.025))
            length,width,height=c.dimensions
            points=np.array([[x,y,z] for x in (-length/2,length/2) for y in (-width/2,width/2) for z in (.27,height+.26)])
            self._set_points(self.box_shadow,project_shadow(points,elevation,sun_azimuth,.015))
        self.sun.visibility=elevation>0
        self.sun.position=sun_vector(elevation,sun_azimuth)*15+np.array([0,0,1.5])
        self.light.position=sun_vector(max(elevation,12),sun_azimuth)*100
        self.light.intensity=.25 if elevation<=0 else max(.30,1.05-cloud*.006)
        self.transforms_sent+=1
        return True

    def set_camera(self,name):
        position,focus=CAMERAS[name]
        self.plotter.camera_position=[position,focus,(0,0,1)]

    def set_options(self,landscape,cutaway):
        for actor in self.landscape_actors:
            actor.visibility=landscape
        for actor in self.cover_actors:
            actor.visibility=not cutaway

    def png(self,size=(2560,1440)):
        output=BytesIO()
        original_size=tuple(self.plotter.window_size)
        try:
            Image.fromarray(self.plotter.screenshot(return_img=True,window_size=size)).save(output,format="PNG")
        finally:
            self.plotter.window_size=original_size
        output.seek(0)
        return output

    def close(self):
        self.plotter.close()
