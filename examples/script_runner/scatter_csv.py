"""3D scatter plot from a CSV -- a Script Runner script built on d3blender.

One small ico-sphere per row, joined by an id column (or the row number
if "Key Column" is empty), so rerunning after changing a setting moves,
resizes and recolors the same spheres instead of adding new ones. Each
axis is scaled independently into a cube of side "Extent", with nice()
rounded domains. Leave "CSV File" empty to use the bundled stars.csv.

Point size changes go through each object's scale rather than the
sphere's creation radius: creation parameters only apply when a sphere
is first made (see the README's note on join('uv_sphere', ...)), while
scale updates in place.
"""

import os

import bpy

import d3blender as d3

HERE = os.path.dirname(os.path.abspath(__file__))

PALETTE = [(0.95, 0.55, 0.1, 1.0), (0.2, 0.5, 0.95, 1.0), (0.3, 0.8, 0.4, 1.0),
           (0.85, 0.25, 0.5, 1.0), (0.6, 0.45, 0.9, 1.0), (0.9, 0.85, 0.2, 1.0)]

PARAMS = {
    "label": "d3: Scatter Plot from CSV",
    "csv_path": {"type": "FILE_PATH", "name": "CSV File", "default": "",
                 "description": "Empty: the bundled stars.csv"},
    "target": {"type": "COLLECTION", "name": "Into Collection",
               "description": "Empty: a 'Scatter Plot' collection is created"},
    "x": {"type": "STRING", "name": "X Column", "default": "x"},
    "y": {"type": "STRING", "name": "Y Column", "default": "y"},
    "z": {"type": "STRING", "name": "Z Column", "default": "z",
          "description": "Empty: a flat plot at z = 0"},
    "key": {"type": "STRING", "name": "Key Column", "default": "id",
            "description": "Identifies a row across reruns. Empty: the row number"},
    "size_by": {"type": "STRING", "name": "Size Column", "default": "magnitude",
                "description": "Empty: every point the same size"},
    "color_by": {"type": "STRING", "name": "Color Column", "default": "class",
                 "description": "Categorical column; empty: one color"},
    "extent": {"type": "FLOAT", "name": "Extent", "default": 6.0, "min": 0.1},
    "radius": {"type": "FLOAT", "name": "Point Radius", "default": 0.12, "min": 0.001},
}


def _csv_path(params, sample):
    path = params.get("csv_path") or ""
    return bpy.path.abspath(path) if path else os.path.join(HERE, sample)


def _target(params, default_name):
    return params.get("target") or d3.collection(default_name, parent=bpy.context.scene.collection)


def _object_color_material():
    mat = bpy.data.materials.get("d3 Object Color")
    if mat is None:
        mat = bpy.data.materials.new("d3 Object Color")
        if mat.node_tree is None:  # 5.x creates the node tree already; use_nodes is deprecated
            mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
        info = nodes.new("ShaderNodeObjectInfo")
        links.new(info.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def _axis(rows, column, extent):
    if not column:
        return lambda d: 0.0
    lo, hi = d3.array.extent(rows, lambda r: r[column])
    s = d3.scale_linear().domain((lo, hi)).nice().range((-extent / 2, extent / 2))
    return lambda d: s(d[column])


def execute(context, params):
    rows = d3.csv(_csv_path(params, "stars.csv"))
    needed = [params[k] for k in ("x", "y", "z", "key", "size_by", "color_by") if params[k]]
    missing = [c for c in needed if c not in rows.columns]
    if missing:
        print(f"[d3 scatter] column(s) not in CSV: {missing}; have {rows.columns}")
        return {"CANCELLED"}
    numeric = [params[k] for k in ("x", "y", "z", "size_by") if params[k]]
    rows = [r for r in rows if all(isinstance(r[c], (int, float)) for c in numeric)]

    chart = _target(params, "Scatter Plot")
    extent = params["extent"]
    fx, fy, fz = (_axis(rows, params[k], extent) for k in ("x", "y", "z"))
    radius = params["radius"]
    if params["size_by"]:
        size = d3.scale_linear().domain(d3.array.extent(rows, lambda r: r[params["size_by"]])).range((0.5, 2.0))
        r_of = lambda d: radius * size(d[params["size_by"]])  # noqa: E731
    else:
        r_of = lambda d: radius  # noqa: E731
    color = d3.scale_ordinal().range(PALETTE)  # implicit domain: colors in order of appearance
    color_of = (lambda d: color(d[params["color_by"]])) if params["color_by"] else (lambda d: PALETTE[0])
    key = params["key"] or (lambda i, d: str(i))
    material = _object_color_material()

    points = (d3.select_all(chart)
              .data(rows, key=key)
              .join("ico_sphere", radius=1.0, subdivisions=2)
              .attr("location", lambda el, d, i: (fx(d), fy(d), fz(d)))
              .attr("scale", lambda el, d, i: (r_of(d),) * 3)
              .attr("color", lambda el, d, i: color_of(d)))
    points.entered.each(lambda el: el.data.materials.append(material))

    print(f"[d3 scatter] {len(points)} points in '{chart.name}' "
          f"({len(points.entered)} new, {len(points.updated)} updated)")
    return {"FINISHED"}
