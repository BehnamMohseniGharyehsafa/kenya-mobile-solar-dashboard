"""Deterministic visual kinematics and ground-plane solar shadow geometry.

These trajectories describe a concept; they are not a collision-certified machine.
All 36 default modules occupy discrete packed positions inside the closed shell.
"""
from dataclasses import dataclass
import numpy as np


def smoothstep(x):
    x = float(np.clip(x, 0, 1))
    return x*x*(3-2*x)


def phase(progress):
    if progress <= 0:
        return "TRANSPORT LOCKED"
    if progress < .12:
        return "ROOF HATCHES"
    if progress < .32:
        return "LIFT CASSETTES"
    if progress < .70:
        return "EXTEND / UNFOLD"
    if progress < .84:
        return "LOWER / LOCK SUPPORTS"
    if progress < 1:
        return "CLOSE ROOF HATCHES"
    return "DEPLOYED / LOCKED"


def hatch_angle(progress):
    """Open for extraction only; close after arrays clear the roof envelope.

    Reversing the same trajectory opens the roof before repacking starts.
    """
    return 108*smoothstep(progress/.12)*(1-smoothstep((progress-.84)/.16))


@dataclass(frozen=True)
class ModulePose:
    number: int
    center: tuple
    vertices: np.ndarray
    deployed_center: tuple
    bank: int


def panel_basis(tilt_deg, azimuth_deg):
    t, a = np.radians([tilt_deg, azimuth_deg])
    normal = np.array([np.sin(t)*np.sin(a), np.sin(t)*np.cos(a), np.cos(t)])
    across = np.array([np.cos(t)*np.sin(a), np.cos(t)*np.cos(a), -np.sin(t)])
    along = np.cross(normal, across)
    return across, along, normal


def layout(c):
    module_length = 2.278
    module_width = c.module_area_m2/module_length
    cols = min(6, max(1, int(np.ceil(np.sqrt(c.modules)))))
    pitch = module_width/c.gcr
    rows_per_bank = int(np.ceil(c.modules/(2*cols)))
    half_x = max(c.dimensions[0]/2+2.5, (cols-1)*pitch/2+module_width+2.5)
    half_y = c.dimensions[1]/2+2+rows_per_bank*(module_length+.12)+2.0
    return {"columns":cols, "rows_per_bank":rows_per_bank, "pitch_m":pitch,
        "module_length_m":module_length, "module_width_m":module_width,
        "fence_half_x":half_x,"fence_half_y":half_y,
        "packed_layers":int(np.ceil(c.modules/3)),
        "packed_top_m":1.45+(int(np.ceil(c.modules/3))-1)*.075+.04,
        "array_ground_m2": (2*half_x-5)*(2*half_y-5)}


def module_geometry(c, progress, tilt_deg=0, azimuth_deg=90):
    """Vectorised version of the same cassette trajectories, in module order."""
    p = float(np.clip(progress, 0, 1))
    d = layout(c)
    cols, ml, mw = d["columns"], d["module_length_m"], d["module_width_m"]
    lift = smoothstep((p-.12)/.20)
    extend = smoothstep((p-.32)/.38)
    lower = smoothstep((p-.70)/.14)
    i=np.arange(c.modules)
    bank=np.where((i//cols)%2==0,1,-1)
    rank,col=i//(2*cols),i%cols
    target=np.column_stack([(col-(cols-1)/2)*d["pitch_m"],
        bank*(c.dimensions[1]/2+1.1+ml/2+rank*(ml+.12)),np.full(c.modules,1.65)])
    center=np.column_stack([((i%3)-1)*(mw+.025),np.zeros(c.modules),1.45+(i//3)*.075])
    center[:,2]=center[:,2]*(1-lift)+(c.dimensions[2]+.95+(i//3)*.025)*lift
    center[:,:2]=center[:,:2]*(1-extend)+target[:,:2]*extend
    center[:,2]=center[:,2]*(1-lower)+target[:,2]*lower
    tilt=np.full(c.modules,tilt_deg*lower) if p>=.70 else np.where(col%2,1,-1)*65*np.sin(np.pi*extend)
    t=np.radians(tilt)
    a=np.radians(azimuth_deg if p>=.70 else 90)
    normal=np.column_stack([np.sin(t)*np.sin(a),np.sin(t)*np.cos(a),np.cos(t)])
    across=np.column_stack([np.cos(t)*np.sin(a),np.cos(t)*np.cos(a),-np.sin(t)])
    along=np.cross(normal,across)
    basis=np.stack([across,along,normal],axis=2)
    corners=np.array([[-mw/2,-ml/2,0],[mw/2,-ml/2,0],[mw/2,ml/2,0],[-mw/2,ml/2,0]])
    vertices=np.einsum("kj,nij->nki",corners,basis)+center[:,None,:]
    return center,basis,vertices,target,bank


def module_poses(c, progress, tilt_deg=0, azimuth_deg=90):
    centers,_,vertices,targets,banks=module_geometry(c,progress,tilt_deg,azimuth_deg)
    return [ModulePose(i+1,tuple(centers[i]),vertices[i],tuple(targets[i]),int(banks[i]))
        for i in range(c.modules)]


def sun_vector(elevation_deg, azimuth_deg):
    e,a = np.radians([elevation_deg, azimuth_deg])
    return np.array([np.cos(e)*np.sin(a), np.cos(e)*np.cos(a), np.sin(e)])


def project_shadow(vertices, elevation_deg, azimuth_deg, ground_z=.035):
    if elevation_deg <= .5:
        return None
    points = np.asarray(vertices,dtype=float)
    sun = sun_vector(elevation_deg,azimuth_deg)
    distance = np.maximum(points[:,2]-ground_z,0)/sun[2]
    projected = points-distance[:,None]*sun
    projected[:,2] = ground_z
    return projected
