"""
A complex/asset-style material -- its interesting shader inputs buried
inside a nested node group, the way a downloaded asset's actual shader
setup often is -- driven entirely through plain custom object
properties, via Blender's own driver system, instead of path-walking
into the material at all. See material_shader_params_blender.py for
the direct-path-walking answer, which is the right tool for a material
whose structure you actually know; this is the answer for one you
don't (or don't want to hardcode a fragile path through).

**rig_driven_input() is a one-time setup cost, however deeply the
socket is actually nested.** It wires a driver from a specific node
socket to a plain custom property, using bpy's own driver API
(`socket.driver_add('default_value')`, a `SINGLE_PROP` variable). After
it runs once, d3blender never needs to know where that socket actually
lives again -- `.attr('ior_value', ...)` reaches it exactly the way it
reaches any other custom property, e.g. `amplitude`/`phase` in the
sphere-deformation examples.

**`driver.type = 'AVERAGE'`, not `'SCRIPTED'`, deliberately.** A
single-variable average is a clean passthrough, and unlike `'SCRIPTED'`
(which evaluates an arbitrary Python expression string), it doesn't
require Blender's "Auto Run Python Scripts" preference to be enabled --
`'SCRIPTED'` drivers are silently disabled without it, which would make
this example fail in exactly the hard-to-notice way a security
restriction should.

**Verified, not assumed: changing the driving custom property doesn't
propagate to the driven value on its own in headless scripting, and
this needed two rounds of checking to pin down precisely.** The first
change after a driver is created *does* show up with only
`bpy.context.view_layer.update()` -- but every change after that first
one silently doesn't, `view_layer.update()` alone or not. Adding
`el.update_tag()` immediately before `view_layer.update()`, on *every*
change, fixed it completely (confirmed across four consecutive
changes) -- the same two-call pattern Geometry Nodes' segment-count
case needed, just easier to miss here since the first change alone
looking right could pass for "it works." In a real interactive Blender
session, ordinary redraws likely make this unnecessary on their own --
not separately verified, same "verified headless, not the full
application" caveat as everywhere else in this project (see CLAUDE.md's
Testing status section).

Run: blender --python examples/material_shader_params_driven_blender.py
(or paste into Blender's Scripting workspace)
"""

import bpy

from d3blender import select, scale_band
from d3blender.blender_adapter import get_adapter

# Same real, physically plausible IOR values as material_shader_params_blender.py.
spheres_data = [
    {'label': 'glass', 'ior': 1.45, 'roughness': 0.05},
    {'label': 'water', 'ior': 1.33, 'roughness': 0.0},
    {'label': 'diamond', 'ior': 2.42, 'roughness': 0.0},
    {'label': 'plastic', 'ior': 1.45, 'roughness': 0.4},
]

x = scale_band([d['label'] for d in spheres_data], range_=(0, 8), padding=0.3)


def make_asset_material(name):
    """Stands in for a complicated downloaded asset material -- the
    interesting inputs are nested one level inside a sub node group,
    the way an asset's actual shader setup is often buried a few groups
    deep for organization/reuse. Returns (material, the buried
    Principled BSDF node) -- the caller uses that direct node reference
    once, to rig drivers, and never needs the path again afterward."""
    inner = bpy.data.node_groups.new(f'{name}_inner', 'ShaderNodeTree')
    inner.interface.new_socket(name='BSDF', in_out='OUTPUT', socket_type='NodeSocketShader')
    inner_in = inner.nodes.new('NodeGroupInput')
    inner_out = inner.nodes.new('NodeGroupOutput')
    bsdf = inner.nodes.new('ShaderNodeBsdfPrincipled')
    inner.links.new(bsdf.outputs['BSDF'], inner_out.inputs['BSDF'])

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.node_tree.nodes.remove(mat.node_tree.nodes['Principled BSDF'])  # replaced by the group below
    group_node = mat.node_tree.nodes.new('ShaderNodeGroup')
    group_node.name = 'Shader'
    group_node.node_tree = inner
    mat.node_tree.links.new(
        group_node.outputs['BSDF'], mat.node_tree.nodes['Material Output'].inputs['Surface'])
    return mat, bsdf


def rig_driven_input(obj, socket, prop_name):
    """Wires socket.default_value to obj[prop_name] via a driver -- see
    the module docstring for why AVERAGE, not SCRIPTED. After this,
    .attr(prop_name, ...) is all that's ever needed again, regardless
    of how deeply `socket` is actually nested."""
    driver = socket.driver_add('default_value').driver
    driver.type = 'AVERAGE'
    var = driver.variables.new()
    var.name = prop_name
    var.type = 'SINGLE_PROP'
    var.targets[0].id_type = 'OBJECT'
    var.targets[0].id = obj
    var.targets[0].data_path = f'["{prop_name}"]'


def rig_asset_material(el, d, i):
    """The .each() escape hatch, one-time setup: build this sphere's
    own (simulated) asset material -- one per sphere, not shared, same
    reason as material_shader_params_blender.py -- and rig its buried
    IOR/Roughness inputs to plain custom properties. Everything after
    this in the chain below only ever touches ior_value/roughness_value,
    never the material's internal node structure."""
    mat, bsdf = make_asset_material(f"mat_{d['label']}")
    el.active_material = mat
    rig_driven_input(el, bsdf.inputs['IOR'], 'ior_value')
    rig_driven_input(el, bsdf.inputs['Roughness'], 'roughness_value')


def report(el, d, i):
    el.update_tag()  # see the module docstring's verified gotcha -- both
    bpy.context.view_layer.update()  # calls, every time, not just the first
    bsdf = el.active_material.node_tree.nodes['Shader'].node_tree.nodes['Principled BSDF']
    print(f"{el.name}: ior_value={el['ior_value']:.2f} -> driven material IOR="
          f"{bsdf.inputs['IOR'].default_value:.2f} (path never touched after rigging)")


adapter = get_adapter()
chart = adapter.get_or_create_collection('Chart')

# -- one chain, start to finish: select -> select -> data -> join -----
#    -> attr -> attr -> each -> attr -> attr -> each. rig_asset_material
#    is the one-time cost (build + wire the driver); the two .attr()
#    calls after it are the *only* thing a later update to these
#    spheres' shader parameters would ever need to look like again --
#    plain custom properties, zero knowledge of the material required.
balls = (
    select(adapter, chart)
    .select('mesh')
    .data(spheres_data, key=lambda i, d: d['label'])
    .join('uv_sphere', collection=chart)
    .attr('name', lambda el, d, i: f"ball_{d['label']}")
    .attr('location', lambda el, d, i: (x(d['label']), 0, 1.5))
    .each(rig_asset_material)
    .attr('ior_value', lambda el, d, i: d['ior'])
    .attr('roughness_value', lambda el, d, i: d['roughness'])
    .each(report)
)
