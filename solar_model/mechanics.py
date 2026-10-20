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
    if progress < .20:
        return "ROOF HATCHES"
    if progress < .40:
        return "LIFT CASSETTES"
    if progress < .82:
        return "EXTEND / UNFOLD"
    if progress < 1:
        return "LOWER / LOCK SUPPORTS"
    return "DEPLOYED / LOCKED"


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


def module_poses(c, progress, tilt_deg=0, azimuth_deg=90):
    p = float(np.clip(progress, 0, 1))
    d = layout(c)
    cols, ml, mw = d["columns"], d["module_length_m"], d["module_width_m"]
    lift = smoothstep((p-.18)/.22)
    extend = smoothstep((p-.40)/.42)
    lower = smoothstep((p-.82)/.18)
    output = []
    for i in range(c.modules):
        bank = 1 if (i//cols) % 2 == 0 else -1
        rank = i//(2*cols)
        col = i % cols
        target = np.array([(col-(cols-1)/2)*d["pitch_m"],
            bank*(c.dimensions[1]/2+1.1+ml/2+rank*(ml+.12)), 1.65])
        packed = np.array([((i%3)-1)*(mw+.025), 0, 1.45+(i//3)*.075])
        raised = packed.copy()
        raised[2] = c.dimensions[2]+.95+(i//3)*.025
        center = packed*(1-lift)+raised*lift
        center[:2] = center[:2]*(1-extend)+target[:2]*extend
        center[2] = center[2]*(1-lower)+target[2]*lower
        # Folded cassettes fan around their long axes during extension.
        fold_angle = (1 if col%2 else -1)*65*np.sin(np.pi*extend)
        if p >= .82:
            tilt = tilt_deg*lower
            azimuth = azimuth_deg
        else:
            tilt, azimuth = fold_angle, 90
        across, along, normal = panel_basis(tilt, azimuth)
        vertices = np.array([center+sx*mw/2*across+sy*ml/2*along
            for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]])
        output.append(ModulePose(i+1, tuple(center), vertices, tuple(target), bank))
    return output


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
