"""Bar chart from a CSV -- a Script Runner script built on d3blender.

One cube per CSV row, joined by the category column, so running it again
after changing a setting (or the CSV) updates the same bars in place:
rows that are still there keep their object, new rows get a new bar, rows
that disappeared lose theirs. Leave "CSV File" empty to use the bundled
sales.csv; leave "Into Collection" empty to build into a "Bar Chart"
collection.

Bars are colored through each object's Color property, which a shared
material ("d3 Object Color") reads with an Object Info node, so the
colors show up in renders as well as in Solid view (Object color mode).
"""

import os

import bpy

import d3blender as d3

HERE = os.path.dirname(os.path.abspath(__file__))

PARAMS = {
    "label": "d3: Bar Chart from CSV",
    "csv_path": {"type": "FILE_PATH", "name": "CSV File", "default": "",
                 "description": "Empty: the bundled sales.csv"},
    "target": {"type": "COLLECTION", "name": "Into Collection",
               "description": "Empty: a 'Bar Chart' collection is created"},
    "category": {"type": "STRING", "name": "Category Column", "default": "month"},
    "value": {"type": "STRING", "name": "Value Column", "default": "revenue"},
    "width": {"type": "FLOAT", "name": "Chart Width", "default": 8.0, "min": 0.1},
    "height": {"type": "FLOAT", "name": "Chart Height", "default": 4.0, "min": 0.1},
    "padding": {"type": "FLOAT", "name": "Bar Padding", "default": 0.2, "min": 0.0, "max": 0.95},
    "color_low": {"type": "COLOR", "name": "Low Color", "default": (0.15, 0.35, 0.8, 1.0)},
    "color_high": {"type": "COLOR", "name": "High Color", "default": (0.95, 0.55, 0.1, 1.0)},
    "animate": {"type": "BOOL", "name": "Grow In (Animate)", "default": False,
                "description": "Keyframe the bars growing from zero, staggered, from the scene's start frame"},
    "stagger": {"type": "INT", "name": "Stagger (frames)", "default": 3, "min": 0},
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


def execute(context, params):
    rows = d3.csv(_csv_path(params, "sales.csv"))
    cat, val = params["category"], params["value"]
    missing = [c for c in (cat, val) if c not in rows.columns]
    if missing:
        print(f"[d3 bar chart] column(s) not in CSV: {missing}; have {rows.columns}")
        return {"CANCELLED"}
    rows = [r for r in rows if isinstance(r[val], (int, float))]

    chart = _target(params, "Bar Chart")
    x = (d3.scale_band().domain([r[cat] for r in rows])
         .range((-params["width"] / 2, params["width"] / 2)).padding(params["padding"]))
    y = d3.scale_linear().domain((0, d3.array.max(rows, lambda r: r[val]) or 1)).nice().range((0, params["height"]))
    color = d3.scale_linear().domain(y.domain()).range((tuple(params["color_low"]), tuple(params["color_high"])))
    material = _object_color_material()
    bw = x.bandwidth()

    def place(el, d, i):
        return (x(d[cat]) + bw / 2, 0.0, y(d[val]) / 2)

    def size(el, d, i):
        return (bw, bw, max(y(d[val]), 1e-4))

    bars = (d3.select_all(chart)
            .data(rows, key=cat)
            .join("cube", size=1.0)
            .attr("color", lambda el, d, i: color(d[val]))
            .attr(val, lambda el, d, i: d[val]))  # the value, as a custom property

    def finish(el):
        if not el.data.materials:
            el.data.materials.append(material)
        el.animation_data_clear()  # a rerun re-keys from scratch (or removes the animation)

    bars.each(finish)

    if params["animate"]:
        start = context.scene.frame_start
        stagger = params["stagger"]
        (bars.attr("location", lambda el, d, i: (place(el, d, i)[0], 0.0, 0.0))
             .attr("scale", lambda el, d, i: (bw, bw, 1e-4))
             .transition(20, delay=lambda el, i: i * stagger, start=start)
             .attr("location", place)
             .attr("scale", size))
    else:
        bars.attr("location", place).attr("scale", size)

    print(f"[d3 bar chart] {len(bars)} bars in '{chart.name}' "
          f"({len(bars.entered)} new, {len(bars.updated)} updated)")
    return {"FINISHED"}
