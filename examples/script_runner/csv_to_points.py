"""CSV to points -- a Script Runner script built on d3blender.

One mesh object with one vertex per CSV row. Position comes from three
columns; every other numeric column becomes a per-point attribute of the
same name (FLOAT, INT or BOOLEAN), readable in Geometry Nodes or a
shader's Attribute node. Leave "CSV File" empty to use the bundled
spiral_points.csv (2000 rows).

Rerunning updates the same object: it's found again through a one-item
d3blender join, values are rewritten in bulk with set_point_attr(), and
attributes this script made for columns that are no longer in the CSV
are removed. d3blender never resizes a mesh by itself (see its README),
so when the row count changes the script rebuilds the vertices
explicitly first.

"Display as Spheres" adds a small Geometry Nodes modifier (Mesh to
Points) so the points render; its Radius input is set by name through
d3blender's path-walker: ('modifiers', 'd3 Points', 'Radius').
"""

import os

import bpy

import d3blender as d3

HERE = os.path.dirname(os.path.abspath(__file__))
GROUP_NAME = "d3 Points Display"
MODIFIER_NAME = "d3 Points"
OWNED_PROP = "d3_point_columns"  # which attributes this script created, for cleanup

PARAMS = {
    "label": "d3: CSV to Points",
    "csv_path": {"type": "FILE_PATH", "name": "CSV File", "default": "",
                 "description": "Empty: the bundled spiral_points.csv"},
    "target": {"type": "COLLECTION", "name": "Into Collection",
               "description": "Empty: a 'Points' collection is created"},
    "object_name": {"type": "STRING", "name": "Object Name", "default": "CSV Points"},
    "x": {"type": "STRING", "name": "X Column", "default": "x"},
    "y": {"type": "STRING", "name": "Y Column", "default": "y"},
    "z": {"type": "STRING", "name": "Z Column", "default": "z",
          "description": "Empty: z = 0"},
    "fit": {"type": "BOOL", "name": "Fit to Size", "default": False,
            "description": "Rescale each axis into [-size/2, size/2] instead of using raw values"},
    "size": {"type": "FLOAT", "name": "Size", "default": 6.0, "min": 0.01},
    "spheres": {"type": "BOOL", "name": "Display as Spheres", "default": True},
    "radius": {"type": "FLOAT", "name": "Sphere Radius", "default": 0.03, "min": 0.0001},
}


def _csv_path(params, sample):
    path = params.get("csv_path") or ""
    return bpy.path.abspath(path) if path else os.path.join(HERE, sample)


def _target(params, default_name):
    return params.get("target") or d3.collection(default_name, parent=bpy.context.scene.collection)


def _column_values(rows, column):
    """A column as one consistent Python type, or None if it isn't
    numeric/boolean. Missing cells become 0 / False. Ints and floats
    mixed in one column (auto-typing reads "1" as int and "1.5" as
    float) become all floats, so the attribute type is stable."""
    values = [r[column] for r in rows]
    present = [v for v in values if v is not None]
    if not present:
        return None
    if all(isinstance(v, bool) for v in present):
        return [bool(v) for v in values]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in present):
        return None
    if all(isinstance(v, int) for v in present):
        return [v if v is not None else 0 for v in values]
    return [float(v) if v is not None else 0.0 for v in values]


def _display_group():
    group = bpy.data.node_groups.get(GROUP_NAME)
    if group is not None:
        return group
    group = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    radius = group.interface.new_socket(name="Radius", in_out="INPUT", socket_type="NodeSocketFloat")
    radius.default_value = 0.03
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes, links = group.nodes, group.links
    inp, out = nodes.new("NodeGroupInput"), nodes.new("NodeGroupOutput")
    to_points = nodes.new("GeometryNodeMeshToPoints")
    links.new(inp.outputs["Geometry"], to_points.inputs["Mesh"])
    links.new(inp.outputs["Radius"], to_points.inputs["Radius"])
    links.new(to_points.outputs["Points"], out.inputs["Geometry"])
    return group


def execute(context, params):
    rows = d3.csv(_csv_path(params, "spiral_points.csv"))
    axes = [params[k] for k in ("x", "y", "z")]
    missing = [c for c in axes if c and c not in rows.columns]
    if missing:
        print(f"[d3 points] column(s) not in CSV: {missing}; have {rows.columns}")
        return {"CANCELLED"}
    coords = [_column_values(rows, c) if c else [0.0] * len(rows) for c in axes]
    if any(c is None for c in coords):
        print("[d3 points] the position columns must be numeric")
        return {"CANCELLED"}
    if params["fit"]:
        half = params["size"] / 2
        coords = [[d3.scale_linear().domain(d3.array.extent(c)).range((-half, half))(v) for v in c]
                  if c and d3.array.extent(c)[0] != d3.array.extent(c)[1] else c
                  for c in coords]
    positions = list(zip(*coords)) if rows else []

    coll = _target(params, "Points")
    name = params["object_name"]
    obj = (d3.select_all(coll)
           .data([name], key=lambda d: d)
           .join(lambda d: bpy.data.objects.new(d, bpy.data.meshes.new(d)))
           .elements[0])
    mesh = obj.data
    adapter = d3.default_adapter()

    if len(mesh.vertices) != len(positions):
        mesh.clear_geometry()  # explicit resize; this also drops every point attribute
        mesh.from_pydata(positions, [], [])
        mesh.update()
    else:
        adapter.set_point_attr(obj, "position", positions)

    written = []
    for column in rows.columns:
        if column in axes:
            continue
        values = _column_values(rows, column)
        if values is None or not values:
            continue
        existing = mesh.attributes.get(column)
        wanted = {bool: "BOOLEAN", int: "INT", float: "FLOAT"}[type(values[0])]
        if existing is not None and (existing.data_type != wanted or existing.domain != "POINT"):
            mesh.attributes.remove(existing)
        adapter.set_point_attr(obj, column, values)
        written.append(column)

    for column in list(obj.get(OWNED_PROP, [])):
        if column not in written and mesh.attributes.get(column) is not None:
            mesh.attributes.remove(mesh.attributes[column])
    obj[OWNED_PROP] = written

    mod = obj.modifiers.get(MODIFIER_NAME)
    if params["spheres"]:
        if mod is None:
            mod = obj.modifiers.new(MODIFIER_NAME, "NODES")
            mod.node_group = _display_group()
        adapter.set_attr(obj, ("modifiers", MODIFIER_NAME, "Radius"), params["radius"])
    elif mod is not None:
        obj.modifiers.remove(mod)

    print(f"[d3 points] {len(positions)} points on '{obj.name}' in '{coll.name}', "
          f"attributes: {', '.join(written) or 'none'}")
    return {"FINISHED"}
