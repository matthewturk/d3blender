"""
Data-driven material shader parameters -- no new d3blender API here,
just get_attr/set_attr's existing generic path-walker reaching straight
into a material's node tree (confirmed against real bpy with zero
adapter changes; see README's "Material shader inputs" section and
CLAUDE.md for the full verification). Four spheres, one material each,
each material's Principled BSDF driven entirely from data: IOR,
Roughness, Transmission Weight, Base Color -- real, physically
plausible IOR values (glass ~1.45, water 1.33, diamond 2.42, a plastic
~1.45 but opaque), not arbitrary numbers.

Also demonstrates Selection.classed() -- tagging the transmissive
(glass/water/diamond) spheres with a real class, then querying by it
with a plain .filter('.transmissive') afterward, the same class
mechanism `.foo`-style selectors have always used.

**One material per object, deliberately.** Materials are shared
datablocks in Blender -- assigning the *same* material to two objects
means changing one changes both. Since the whole point here is each
sphere having its *own* IOR, this creates a fresh material per sphere
rather than reusing one, via .each() (the escape hatch for "do
something per element that isn't just setting one attribute", the same
role it plays in the nested_uv_sphere_deformation_*.py examples).

**Two real gotchas this pattern runs into, both verified, both worth
knowing before extending this:**
- Node names auto-suffix like objects/modifiers ("Principled BSDF" ->
  "Principled BSDF.001" for a second one in the same tree) -- not an
  issue here (one BSDF per material), but the same tuple-path rule
  applies if you ever have more than one.
- Setting `default_value` on an already-linked socket (e.g. if you'd
  plugged a texture into Base Color) succeeds silently and changes
  nothing visually -- the link keeps controlling the actual shading.
  Not an issue here either (nothing's linked), but worth knowing.

Run: blender --python examples/material_shader_params_blender.py
(or paste into Blender's Scripting workspace)

Verified against real bpy (PyPI's headless module, see tests/blender/):
confirmed the exact Principled BSDF socket names on this Blender
version ('IOR', 'Roughness', 'Transmission Weight', 'Base Color'),
confirmed get_attr/set_attr reach and change them correctly, confirmed
one material per object rather than one shared material. Not yet
verified against the full Blender application, and socket names are
version-sensitive (see CLAUDE.md) -- if a name doesn't resolve on your
Blender version, inspect
`material.node_tree.nodes['Principled BSDF'].inputs` directly.
"""

import bpy

from d3blender import select, scale_band
from d3blender.blender_adapter import get_adapter

# Real, physically plausible IOR values -- not arbitrary numbers.
spheres_data = [
    {'label': 'glass', 'ior': 1.45, 'roughness': 0.05, 'transmission': 1.0,
     'base_color': (0.9, 0.95, 1.0, 1.0)},
    {'label': 'water', 'ior': 1.33, 'roughness': 0.0, 'transmission': 1.0,
     'base_color': (0.8, 0.9, 1.0, 1.0)},
    {'label': 'diamond', 'ior': 2.42, 'roughness': 0.0, 'transmission': 1.0,
     'base_color': (1.0, 1.0, 1.0, 1.0)},
    {'label': 'plastic', 'ior': 1.45, 'roughness': 0.4, 'transmission': 0.0,
     'base_color': (0.9, 0.2, 0.2, 1.0)},
]

x = scale_band([d['label'] for d in spheres_data], range_=(0, 8), padding=0.3)


def bsdf_input(name):
    """Local convenience, not a d3blender API -- just spells out the
    tuple path get_attr/set_attr already resolve generically (see
    README's "Material shader inputs" section). 'Principled BSDF' is
    the node every use_nodes=True material starts with."""
    return ('active_material', 'node_tree', 'nodes', 'Principled BSDF', 'inputs', name, 'default_value')


def assign_material(el, d, i):
    """A fresh material per sphere -- see the module docstring for why
    this can't be one shared material."""
    mat = bpy.data.materials.new(f"mat_{d['label']}")
    mat.use_nodes = True
    el.active_material = mat


adapter = get_adapter()
chart = adapter.get_or_create_collection('Chart')

balls = (
    select(adapter, chart)
    .select('mesh')
    .data(spheres_data, key=lambda i, d: d['label'])
    .join('uv_sphere', collection=chart)
    .attr('name', lambda el, d, i: f"ball_{d['label']}")
    .attr('location', lambda el, d, i: (x(d['label']), 0, 1.5))
    .each(assign_material)
    .attr(bsdf_input('IOR'), lambda el, d, i: d['ior'])
    .attr(bsdf_input('Roughness'), lambda el, d, i: d['roughness'])
    .attr(bsdf_input('Transmission Weight'), lambda el, d, i: d['transmission'])
    .attr(bsdf_input('Base Color'), lambda el, d, i: d['base_color'])
    .classed('transmissive', lambda el, d, i: d['transmission'] > 0)
)

balls.each(lambda el, d, i: print(
    f"{el.name}: IOR={el.active_material.node_tree.nodes['Principled BSDF'].inputs['IOR'].default_value:.2f} "
    f"transmissive={adapter.classes_of(el)}"))

print()
print('transmissive spheres, queried by class:',
      [el.name for el in balls.filter('.transmissive').elements])
