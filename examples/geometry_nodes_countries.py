"""
Real-Blender example (like scatter_plot_3d_blender.py -- needs an actual
Blender install, not the mock): countries plotted by lat/lon, each with
its own Geometry Nodes modifier that scatters a small cluster of spheres
sized by the country's population -- built with nodebpy -- then
d3blender selects the populous subset and cranks up their Geometry Nodes
modifier's inputs, via the exact same select()/.attr() idiom used
everywhere else in this library.

Treats databpy and nodebpy as top-level libraries for this kind of
script: databpy creates the collection and the per-country anchor
objects (and stores population as a real point attribute, separately
from the custom property d3blender actually queries -- see the comment
where it's set); nodebpy builds the Geometry Nodes tree; d3blender does
the query/select/attr/animate layer on top of whatever real objects
those two produced. None of the three needs to know about the others.

REQUIRES, inside Blender's own Python:
    pip install databpy nodebpy

CAVEAT -- please verify before trusting this:
  - nodebpy versions its node-class definitions per Blender release
    (see its README/pyproject: bpy==5.2.* as of the v520.8.0 release,
    its latest published tag at the time this was written). There was
    no 5.3-targeted release yet -- if you're on Blender 5.3+, check
    https://github.com/BradyAJohnston/nodebpy/releases for a newer
    53x.x.x tag before relying on the exact node classes/sockets used
    below; a version mismatch could mean a node's socket names or
    defaults have quietly changed underneath this script.
  - Like blender_adapter.py itself, this script is written against the
    real, current APIs of nodebpy/databpy (verified by reading their
    source directly, not guessed), but has NOT been run against a live
    Blender install by anyone -- "written correctly against a real API"
    and "verified working" are different claims. See CLAUDE.md's
    "Testing status" section for the same caveat applied to d3blender's
    own Blender glue.

Run: paste into Blender's Scripting workspace and click "Run Script", or
    blender --python examples/geometry_nodes_countries.py
    (add --background for headless)
"""

import bpy
import numpy as np

import databpy as db
from nodebpy import geometry as g

from d3blender import select, scale_linear
from d3blender.blender_adapter import get_adapter

# Rounded, illustrative population figures -- not an authoritative
# dataset, just enough spread to demonstrate selecting a subset.
COUNTRIES = [
    {"name": "China", "population": 1_410_000_000, "lat": 35.0, "lon": 105.0},
    {"name": "India", "population": 1_430_000_000, "lat": 22.0, "lon": 79.0},
    {"name": "United_States", "population": 335_000_000, "lat": 39.8, "lon": -98.6},
    {"name": "Indonesia", "population": 277_000_000, "lat": -0.8, "lon": 113.9},
    {"name": "Brazil", "population": 216_000_000, "lat": -10.3, "lon": -53.2},
    {"name": "Nigeria", "population": 223_000_000, "lat": 9.1, "lon": 8.7},
    {"name": "Germany", "population": 84_000_000, "lat": 51.2, "lon": 10.5},
    {"name": "Japan", "population": 124_000_000, "lat": 36.2, "lon": 138.3},
    {"name": "Egypt", "population": 112_000_000, "lat": 26.8, "lon": 30.8},
    {"name": "Australia", "population": 26_000_000, "lat": -25.3, "lon": 133.8},
]
POPULOUS_THRESHOLD = 300_000_000  # China, India, United_States
MODIFIER_NAME = "PopulationMarker"


def build_population_marker_tree(name=MODIFIER_NAME):
    """A shared Geometry Nodes tree: scatter `Count` small spheres of
    `Radius` in a jittered cluster around the object's own origin.
    `Seed` reruns the jitter pattern per object. All three are exposed
    as modifier inputs (hide_in_modifier defaults to False in nodebpy),
    so every object using this tree can independently override them --
    the tree/graph is shared, the input *values* are per-object.
    """
    with g.tree(name) as tree:
        count = tree.inputs.integer("Count", 10, min_value=1, max_value=500)
        radius = tree.inputs.float("Radius", 0.05, min_value=0.001)
        seed = tree.inputs.integer("Seed", 0)

        jitter = g.RandomValue.vector(min=(-0.3, -0.3, 0.0), max=(0.3, 0.3, 0.3), seed=seed)
        points = g.Points(count=count, position=jitter.o.value, radius=0.01)
        sphere = g.IcoSphere(radius=radius, subdivisions=2)
        instanced = g.InstanceOnPoints(points=points.o.geometry, instance=sphere.o.mesh)
        realized = g.RealizeInstances(geometry=instanced.o.instances)

        realized.o.geometry >> tree.outputs.geometry("Geometry")

    tree.tree.is_modifier = True  # matches what Blender itself sets for modifier-intended trees
    return tree.tree


# -- Build the scene ---------------------------------------------------

countries_collection = db.create_collection("Countries")
node_group = build_population_marker_tree()

lon_scale = scale_linear(domain=(-180, 180), range_=(-8, 8))
lat_scale = scale_linear(domain=(-90, 90), range_=(-4, 4))

for country in COUNTRIES:
    bob = db.create_bob(
        vertices=np.array([[0.0, 0.0, 0.0]]),
        name=f"country_{country['name']}",
        collection=countries_collection,
    )
    obj = bob.object  # the real bpy.types.Object the BlenderObject wraps
    obj.location = (lon_scale(country["lon"]), lat_scale(country["lat"]), 0.0)

    # The custom property d3blender's selectors actually query below --
    # a plain object-level ID property, unrelated to the mesh attribute
    # stored two lines down.
    obj["population"] = country["population"]

    modifier = obj.modifiers.new(name=MODIFIER_NAME, type='NODES')
    modifier.node_group = node_group

    # Also store population as a genuine per-point geometry attribute via
    # databpy -- a *different* mechanism from the custom property above:
    # this one lives on the mesh/point domain, is what a "Named
    # Attribute" node inside the Geometry Nodes tree itself could read,
    # and is NOT visible to d3blender's selectors (see CLAUDE.md's
    # adapter.py notes on why: simple_attrs() only reads object-level ID
    # properties, not mesh attributes). Read back immediately as a sanity
    # check that the round-trip works.
    bob.store_named_attribute(
        np.array([country["population"]], dtype=np.float64), "population"
    )
    stored = db.named_attribute(obj, "population")
    assert stored[0] == country["population"]


# -- d3blender: select the populous subset, change their GN parameters --

adapter = get_adapter()

populous = select(adapter, f'#Countries mesh[population>{POPULOUS_THRESHOLD}]')
print("populous countries:", sorted(el.name for el in populous))

populous.attr(('modifiers', MODIFIER_NAME, 'Count'), 60)
populous.attr(('modifiers', MODIFIER_NAME, 'Radius'), 0.09)

# Inspect: confirm the change landed, via adapter.gn_inputs() -- the same
# introspection helper documented alongside get_attr/set_attr's path
# support.
for el in populous:
    gn_modifier = el.modifiers[MODIFIER_NAME]
    print(el.name, adapter.gn_inputs(gn_modifier))
