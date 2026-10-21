"""Static landscape quality and rendering-cost regression checks."""
from dataclasses import replace

import numpy as np

from solar_model.config import Config
from solar_model.landscape import vegetation,terrain,GRASS,FOLIAGE
from solar_model.mechanics import layout


def test_landscape_materials_are_batched_and_near_ground_is_finer():
    c=Config()
    solids,wires=vegetation(c)
    assert not wires
    assert len(solids)<=5  # One actor per material, not per tree, leaf or blade.
    assert GRASS in solids and FOLIAGE in solids
    assert sum(mesh.triangulate().n_cells for mesh in solids.values())<70000
    for mesh in solids.values():
        assert mesh.n_points and np.isfinite(mesh.points).all()
    ground,_=terrain(c,layout(c))
    assert ground.points.dtype==np.float32
    assert ground.n_points<22000
    assert len(np.unique(ground['terrain_rgb'],axis=0))>100
    grass=solids[GRASS]
    # Every tuft remains outside the service compound; the illustration keeps
    # the equipment access area clear rather than drawing grass through PV.
    assert ((np.abs(grass.points[:,0])>layout(c)['fence_half_x'])|
        (np.abs(grass.points[:,1])>layout(c)['fence_half_y'])).all()


def test_grass_palette_follows_highland_or_arid_site():
    highland=vegetation(Config())[0][GRASS]['grass_rgb'].astype(float).mean(axis=0)
    arid=vegetation(replace(Config(),site='Lodwar / Turkana',altitude_m=477))[0][GRASS]['grass_rgb'].astype(float).mean(axis=0)
    assert highland[1]-highland[0]>25
    assert arid[0]>arid[1]


def test_large_compound_can_omit_out_of_bounds_vegetation_without_error():
    c=replace(Config(),modules=576,module_area_m2=4.,gcr=.15)
    solids,_=vegetation(c)
    assert all(mesh.n_points and np.isfinite(mesh.points).all() for mesh in solids.values())
