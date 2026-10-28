# d3blender

A d3.js-flavored selector, join/reconciliation, and animation layer over
Blender's scene graph. Written in Python, for Python.

```python
from d3blender import select

select(adapter, '.enemy[hp>0]').attr('hp', lambda el, i: el.get('hp') - 10)
```

If you like d3's `select` / `.attr()` / `.data().join()` idiom and would
rather write plain Python against `bpy` than wire up a web frontend, this
is for you. There's no UI here at all -- it's a library, not a tool.

## Why this exists

Two things `bpy` scripting doesn't really give you:

1. **A selector language.** Finding "every mesh in the Weapons collection
   with more than 25 hit points" in raw `bpy` means writing a loop with an
   `if`. Here it's `select(adapter, '#Weapons mesh[hp>25]')`.
2. **Rerun-safe scene construction.** d3's `selection.data(array).join()`
   reconciles the DOM against an array by identity: change the array,
   rerun, and only what actually changed gets touched. `d3blender` brings
   the same pattern to Blender objects -- rerun a script with a shorter
   array and the extra objects get removed, not orphaned.

## Two hierarchies, not one

CSS assumes one tree. Blender has two, and they're genuinely independent:

- **Collection containment** -- `.users_collection`, `Collection.children`
- **Transform parenting** -- `obj.parent` (rigs, instancing)

So there are two combinator axes instead of one:

| Combinator | Axis | Meaning |
|---|---|---|
| ` ` (space) | collection | descendant, anywhere in the containment tree |
| `>` | collection | direct child |
| `~` | parent | descendant, anywhere in the parenting tree |
| `~>` | parent | direct child |

A single selector has to stay on one axis -- `Rig ~ Weapons > mesh` mixes
both and raises `ValueError`. Split it into two queries instead.

## Selector grammar

```
type            mesh, camera, light, collection, armature, ...
*               universal selector
.class          a space-separated "d3_class" custom property, like HTML class=
#name           exact name match (bare words are types, not names -- see below)
[key]           attribute exists / is truthy
[key=val]       attribute equals val
[key>val]       [key<val] [key>=val] [key<=val] [key!=val] -- numeric comparison
:pseudo         a predicate registered on the adapter (:selected, :visible, :hidden, ...)
:pseudo(arg)    a predicate with an argument (:has-modifier(BEVEL), :has-material(Enemy_Red))
a, b            union, same as CSS
```

**Materials** aren't a custom property, but they're queryable the same
way: `material` is a synthetic attribute exposing `obj.active_material`,
so `[material=Enemy_Red]` and `[material]` (has *some* active material)
work like any other attribute selector. That only sees the *active*
material, though -- an object can have several material slots, so
`:has-material(Enemy_Red)` checks membership across all of them, mirroring
`:has-modifier`. (A custom property literally named `material` would
shadow the synthetic one -- unlikely, but worth knowing.)

**Bare word = type, `#name` = a specific instance.** `Weapons > mesh` does
*not* mean "children of the Weapons collection" -- `Weapons` there is
parsed as a type name (and won't match anything, since nothing has that
type). You want `#Weapons > mesh`. This mirrors CSS's own `tag` vs. `#id`
split and is the single most common mistake when writing these selectors.

## How matching actually works

Structural matching (type/class/id/attribute-equality, and the two
combinator axes) is delegated entirely to
[soupsieve](https://facelessuser.github.io/soupsieve/) -- the real CSS
engine BeautifulSoup uses -- by serializing the current scene into two
small synthetic HTML-ish documents (one per axis) and running a real
`.select()` against them. Numeric comparisons and pseudo-classes aren't
expressible in CSS, so those are stripped out beforehand and applied as a
plain Python filter afterward. See `d3blender/query.py` and
`d3blender/scene_doc.py` for the full mechanism.

This means the only genuinely custom code in this library is: the
axis/combinator split, the numeric/pseudo predicate layer, and the
join/reconciliation pattern (`d3blender/selection.py`) -- there's no
existing library for rerun-safe scene reconciliation, so that part really
is bespoke.

## Quickstart

```bash
pip install -e ".[dev]"
pytest
python examples/bar_chart.py
```

That's the full mock-backed suite -- no Blender required. To also run
against real `bpy` (a separate Python 3.13 venv, since PyPI's headless
`bpy` module only ships `cp313` wheels), see `tests/blender/README.md`.

```python
from d3blender import select, scale_linear
from d3blender.blender_adapter import get_adapter   # only import this inside Blender

adapter = get_adapter()

height = scale_linear(domain=(0, 100), range_=(0.2, 4.0))

(select(adapter, 'mesh.bar')
    .each(lambda el, i: setattr(el, 'scale', (1, 1, height(el.get('value', 0))))))
```

## API

### `select(adapter, target) -> Selection`
Top-level query against the whole scene. `target` is usually a selector
string, but -- mirroring d3's `d3.select(node)` -- it can also be an
element, or an iterable of elements, to wrap directly with no CSS
involved. Reach for that form to re-wrap an element you already have
(e.g. to `.keyframe()` it on a rerun): Blender's own auto-suffixed names
like `"Cube.001"` aren't valid `#name` selector text, since CSS reads the
`.` as a class.

### `Selection`

Every callable a `Selection` method accepts -- `.attr()`'s `value`,
`.each()`'s `fn`, `.keyframe()`'s attr values, `.filter()`'s
`predicate` -- can be written as `fn(el)`, `fn(el, i)`, or
`fn(el, d, i)`, and the right one is picked automatically by the
callable's own arity. `d` is this element's own bound datum -- the same
thing real d3's `(d, i) => ...` accessors receive directly, because a
d3 selection keeps data bound to its DOM nodes permanently once joined.
d3blender mirrors that with `Selection.datum`, a list parallel to
`.elements` that `Join.join()` populates (one entry per element, in
data order) -- not every adapter's elements can hold arbitrary Python
attributes the way a DOM node can, so it's tracked alongside the
elements rather than on them. A `Selection` with no bound data (a plain
`select()` query, or `.select()`'s scoped descendant results -- see
below) has `.datum` full of `None`s; a 3-arg callable against one just
gets `d=None`, no error.

- `.each(fn)` -- calls `fn` for every element, returns `self`
- `.attr(key, value=None)` -- getter if `value` is `None` (reads the first
  element), setter otherwise; `value` can be a plain value or a callable.
  `key` reaches into nested properties (modifiers, geometry nodes inputs --
  see below) as either a dot-joined string (`'modifiers.Bevel.width'`) or
  a tuple of segments (`('modifiers', 'Scatter.001', 'Size')`); use the
  tuple form whenever a name in the chain might itself contain a `.`
  (Blender auto-suffixes duplicate modifiers/node groups the same way it
  does object names)
- `.classed(names, value=None)` -- d3's `selection.classed()`: toggles
  one or more classes (space-separated, like `'enemy boss'`) in the
  `d3_class` custom property that `.foo`-style selectors already read,
  without disturbing other classes already on the element. Getter
  (`value=None`) reads whether the *first* element has *all* of
  `names`; setter takes a plain bool or a callable, same shapes as
  `.attr()`
- `.keyframe(frame, **attrs)` -- sets each attr and drops a real Blender
  keyframe at `frame`. Blender's own F-curves do the interpolation, so
  this is the whole "transition" story: `sel.keyframe(1, location=a).keyframe(30, location=b)`
- `.filter(predicate)` -- a selector string, or a callable as above;
  survivors keep their own bound datum (`kept.datum` lines up with
  `kept.elements`)
- `.select(selector_str, axis='collection'|'parent')` -- scoped descendant
  query within the current selection's subtree. Returns an *unbound*
  Selection -- there's no 1:1 parent-datum-to-child mapping to fall back
  on (one element can have many matching descendants), so this doesn't
  try to guess one; rebind with a fresh `.data()` if you need one
- `.remove()` -- removes every element in the selection
- `.data(items, key=None) -> Join`

### `Join`
- `.join(enter, update=None, exit=None) -> Selection` -- reconciles by
  identity (a stamped `d3_key` custom property). `enter(d)` must return
  the created element; `update(el, d)` and `exit(el)` are optional (a
  missing `exit` just calls `adapter.remove(el)`). The returned
  `Selection`'s `.datum` is each element's own item from `items`, in the
  same order -- rerunning `.data(newItems).join(...)` rebinds it to the
  new items, not stale ones.
- `enter` can also be a shape name string (e.g. `.join('uv_sphere',
  collection=chart)`) -- real d3's own `selection.join("circle")`
  shorthand, dispatched through `adapter.creator(name, collection,
  **create_kwargs)`. `collection` is required (there's no DOM-like
  implicit parent to default to, and defaulting to Blender's ambient
  "active collection" risks landing objects somewhere invisible to
  `select()` -- see Known limitations); other kwargs are creation-time
  parameters (radius, segments, ring_count, ...), each a plain value or
  a per-datum `fn(d) -> value`. Real bpy only (`LiveBlenderAdapter`) --
  the mock's `creator()` raises clearly, since there's no `bpy.ops`
  equivalent to dispatch to; build your own base shape with
  `mock.spawn()`/`spawn_points()` and pass a plain callable `enter`
  instead. Available names: `uv_sphere`, `ico_sphere`, `cube`,
  `cylinder`, `cone`, `plane`, `torus`, `circle` -- the standard bpy.ops
  mesh primitives, not a d3blender-invented geometry generator. **Shape
  parameters only exist at creation time** -- unlike an SVG circle's
  `r`, a UV sphere's `segments`/`ring_count`/`radius` are baked into the
  mesh's vertex data, not settable object properties afterward
  (confirmed: `obj['segments'] = 32` on an already-created sphere
  changes nothing). Everything genuinely mutable -- name, location,
  scale, custom props -- is still an ordinary `.attr()` call after the
  join, same as always; `.attr('scale', lambda el, d, i: (d['radius'],) * 3)`
  is the right way to vary a primitive's *apparent* size per datum
  without needing a creation-time parameter at all.

### Modifiers and Geometry Nodes inputs
`adapter.get_attr`/`.set_attr` (and therefore `Selection.attr`) walk
nested paths generically -- `getattr` → `.get()` → subscript at each
segment -- so a plain modifier's ordinary properties are already
reachable: `select(adapter, '#Rig mesh').attr('modifiers.Bevel.width', 0.4)`.

Geometry Nodes inputs are the one case plain attribute access can't
reach on its own: they're stored under opaque keys ("Input_2"), and the
human-readable name ("Size") only exists in the node group's interface.
The path-walker has one extra fallback for exactly this: when a segment
lands on a `NODES` modifier, the next segment is looked up by name
against `modifier.node_group.interface.items_tree` (the Blender
4.0+/5.x shape -- no legacy `node_group.inputs` support) and resolved to
its real key automatically. Reading/writing the value at that key goes
through `modifier.properties.inputs[key].value` -- as of Blender 5.2,
GN modifier inputs stopped being plain ID properties
(`modifier[key] = value`, which now raises "id properties not supported
for this type") and moved onto this dedicated RNA property wrapper; this
project targets 5.3+, so there's no fallback to the pre-5.2 shape. So
the same syntax reaches Geometry Nodes inputs too, no special-cased API:

```python
select(adapter, '#Chart mesh').attr(('modifiers', 'Scatter', 'Size'), 2.0)
```

- `adapter.gn_inputs(modifier) -> {name: value}` -- lists every input on
  a Geometry Nodes modifier's interface, for inspecting what's available
  before you `.attr()` into one of them by name.
- **Always use the tuple form, not the dot-joined string, once you're not
  sure a name is dot-free.** Node groups and modifiers get `.001`-style
  auto-suffixes exactly like objects do, and the string form's `.split('.')`
  can't tell "part of a name" from "the next path segment" apart --
  `'modifiers.Scatter.001.Size'` silently resolves to nothing, while
  `('modifiers', 'Scatter.001', 'Size')` is always correct, since nothing
  gets split.
- **The `[key...]` bracket-selector syntax can't express this at all** --
  it's a single unescaped CSS-style string, so a dotted or spaced name
  (GN inputs are often multi-word, like "Instance Count") can't be
  selected/filtered on that way. Use `.filter(lambda el: adapter.get_attr(el, (...)) > x)`
  instead of `[modifiers.Scatter.Instance Count>2]` (which doesn't parse).

### Material shader inputs

No new API here -- `get_attr`/`set_attr`'s existing generic path-walker
already reaches straight into a material's shader node tree, confirmed
against real bpy with zero changes needed:

```python
select(adapter, '#Ball').attr(
    ('active_material', 'node_tree', 'nodes', 'Principled BSDF', 'inputs', 'IOR', 'default_value'),
    lambda el, d, i: d['ior'])
```

`active_material` -> `node_tree` -> `nodes` -> the node's name ->
`inputs` -> the socket's name -> `default_value` -- plain attribute/
subscript access the whole way, the same walk that already worked for
`modifiers.Bevel.width` before any GN-specific handling existed. See
`examples/material_shader_params_blender.py` for a full data-driven
example (IOR, Roughness, Base Color, one material per object).

Two real gotchas, both confirmed, not assumed:

- **Node names auto-suffix exactly like objects and modifiers** -- a
  second `Principled BSDF` node in the same tree becomes `Principled
  BSDF.001`. The same tuple-vs-dotted-string rule applies: use a tuple
  segment for the node's name whenever it might not be unique, for the
  same reason `('modifiers', 'Scatter.001', 'Size')` exists.
- **Setting `default_value` on an already-linked socket succeeds
  silently and changes nothing visually.** If a texture (or any other
  node) feeds a socket, that link overrides its own `default_value`
  entirely -- `set_attr` doesn't know or warn, the value just sits there
  unused. If a `.attr()` write to a shader input doesn't seem to do
  anything, check `socket.is_linked` first.

Exact socket names (`'IOR'`, `'Base Color'`, `'Transmission Weight'`, ...)
are whatever your Blender version's Principled BSDF actually calls them
-- they do change between versions (confirmed: the `Specular` input
became `Specular IOR Level` around Blender 4.0). Inspect
`material.node_tree.nodes['Principled BSDF'].inputs` directly if
something doesn't resolve.

**A material you didn't build -- an asset, something with its real
shader buried a few node groups deep -- is a worse fit for path-walking**
than one whose structure you actually know: you'd be hardcoding a path
through node names you don't control and don't want to. Blender's own
driver system is the better tool there: wire a driver, once, from
whatever deeply-nested socket needs exposing to a plain custom object
property, and every future update only ever touches that property --
`.attr()` reaches it exactly like any other custom prop, no knowledge
of the material's structure required after the one-time setup.

```python
driver = bsdf.inputs['IOR'].driver_add('default_value').driver
driver.type = 'AVERAGE'   # a single-variable average = a clean passthrough
var = driver.variables.new()
var.name = 'ior_value'
var.type = 'SINGLE_PROP'
var.targets[0].id_type = 'OBJECT'
var.targets[0].id = obj
var.targets[0].data_path = '["ior_value"]'
```

...after which `select(adapter, '#Ball').attr('ior_value', lambda el, d, i: d['ior'])`
is the entire story, forever -- no path into the material anywhere in
that call. Use `driver.type = 'AVERAGE'`, not `'SCRIPTED'`: a
single-variable average is a clean passthrough, and unlike `'SCRIPTED'`
(an arbitrary Python expression string), it doesn't require Blender's
"Auto Run Python Scripts" preference to be enabled -- `'SCRIPTED'`
drivers are silently disabled without it.

**Confirmed, and easy to get wrong: changing the driving custom
property doesn't propagate to the driven value on its own, in headless
scripting.** The *first* change after a driver is created shows up with
just `bpy.context.view_layer.update()` -- every change after that
first one silently doesn't, `view_layer.update()` alone or not
(confirmed across several consecutive changes). `el.update_tag()`
immediately before `view_layer.update()`, on *every* change, is what
actually fixes it -- the same two-call pattern the Geometry Nodes
segment-count case needed, just easier to miss here since the first
change alone looking right could pass for "it works." See
`examples/material_shader_params_driven_blender.py` for the full
worked example (four spheres, one asset-style material each, IOR/
Roughness driven purely through custom properties).

### Cameras

Also no new API -- a camera is just an ordinary object. `select(adapter,
'camera')` finds it the same way `'mesh'` finds meshes; its transform
(`location`, `rotation_euler`) is an ordinary `.attr()` target. Camera-
specific properties (focal length, clipping, depth of field) live on
`.data`, one path-walk deeper, confirmed against real bpy with zero
adapter changes:

```python
select(adapter, 'camera').attr(('data', 'lens'), lambda el, d, i: d['focal_length'])
select(adapter, 'camera').attr(('data', 'dof', 'focus_distance'), lambda el, d, i: d['focus'])
```

If `select(adapter, 'camera')` comes back empty even though the camera
exists, it's almost certainly the scene-root-collection gotcha (see
Known limitations) -- link it into a real collection, not just
`bpy.context.scene.collection`.

### Compositor nodes

A third node-tree domain, after Geometry Nodes and materials, reachable
the same generic way -- confirmed against real bpy. **The exact API
here is version-sensitive and changed recently**: this Blender version
stores the compositor as a real node-group datablock on
`scene.compositing_node_group`, not the older `scene.node_tree`, and
`use_nodes = True` doesn't create that node group for you the way it
does for a material -- you create and assign it yourself:

```python
group = bpy.data.node_groups.new('Compositing', 'CompositorNodeTree')
scene.compositing_node_group = group
scene.use_nodes = True
```

...after which a node's inputs resolve exactly like a material's:

```python
adapter.set_attr(scene, ('compositing_node_group', 'nodes', 'Glare', 'inputs', 'Threshold', 'default_value'), 0.5)
```

Some node parameters are plain `bpy_struct` properties instead of
sockets (varies per node, same as everywhere else in this project) --
inspect the node directly (`node.bl_rna.properties`, `node.inputs`) if
a name doesn't resolve, same advice as the Modifiers and Material
sections above. `scene` here isn't something you reach through
`select()` -- there's normally exactly one, so just use
`bpy.context.scene` directly, the same way `select(adapter, el)`
already handles "I already have the element" for anything else.

### Per-vertex ("point") data

A different granularity than everything above: `get_attr`/`set_attr`
read/write one property on one object; these read/write one value *per
vertex*, for when your data has too many points to sensibly be one
object each (thousands of objects bogs down Blender's outliner/viewport
long before thousands of vertices in one mesh do).

- `adapter.point_count(el) -> int` -- vertex count, 0 if `el` isn't a mesh.
- `adapter.point_attr(el, name) -> [value, ...]` -- the whole per-vertex
  array for one named channel, in vertex-index order. `name='position'`
  is `.co`; anything else is a named entry in `mesh.attributes`
  (Blender's unified point/edge/face/corner attribute system). Reading a
  name that doesn't exist yet is a `KeyError`, same as a missing dict key.
- `adapter.set_point_attr(el, name, values)` -- bulk write; `len(values)`
  must equal `point_count(el)` exactly. **Deliberately never resizes the
  mesh to fit** -- a length mismatch is a clear `ValueError`, not an
  implicit rebuild. If the point count genuinely changed, rebuild the
  mesh yourself first (`mesh.clear_geometry()` + `mesh.from_pydata()`
  is the real-bpy way -- confirmed to work cleanly, but it does wipe any
  existing custom attributes, which then need recreating). Writing a new
  name creates the attribute, typed by inspecting your first value
  (float/int/bool/3-tuple/4-tuple -> FLOAT/INT/BOOLEAN/FLOAT_VECTOR/
  FLOAT_COLOR); writing an existing name keeps its established type.
- `points.point_data(adapter, el, frame, **channels)` -- the d3-flavored
  layer on top: each keyword is a channel name mapped to a
  `fn(frame) -> values` callable, computed and bulk-written in one call.
  Not flattened into the top-level package (same convention as `axis`/
  `array`) -- `from d3blender.points import point_data`.

**`point_data()` is deliberately not shaped like `Join`.** `Join` needs a
stamped identity (`d3_key`) because objects can be individually added or
removed and a rerun has to recognize "this object still represents the
same thing." Vertices don't have that kind of identity -- `point_data()`
binds by *index* (`data[i]` -> vertex `i`), not by key, and there's no
enter/update/exit. If you need per-entity continuity across a changing
dataset, that's what object-based `Selection`/`Join` is for; `point_data`
trades identity for the scale vertices give you over one object per point.

**No keyframing, no interpolation, no state kept between calls** -- every
`point_data()` call recomputes and overwrites each channel from scratch.
That's a real constraint, not a missing feature: per-vertex position
*can* be F-curve-keyframed like `obj.location` can, but the cost scales
with vertex count (measured: 2000 vertices creates 6000 F-curves for a
single keyframe pass) -- fine for a few hundred points, real file bloat
past that. Per-vertex custom attributes can't be keyframed through bpy's
RNA system at all (`keyframe_insert()` raises `could not make path`). So
"changing over time" here means recomputing per frame, one of two ways:

- **An explicit loop** -- `for frame in range(...): point_data(...)`.
  Deterministic and fully mock-testable, but be aware of what it
  actually does: it computes every frame's values instantly, one after
  another, and only the *last* one survives (nothing is stored) -- so
  this is for baking/exporting frame-by-frame, not for "run once and
  press Play," which does nothing afterward (confirmed: the mesh just
  sits frozen at the loop's final frame, however you scrub).
- **`blender_adapter.live_point_data(adapter, el, **channels)`** -- wires
  the same channel functions to `bpy.app.handlers.frame_change_pre`
  instead, so scrubbing or playing Blender's own timeline recomputes and
  rewrites the mesh live. Applies once immediately at the current frame,
  then again on every frame change; returns a `stop()` to remove the
  binding. Safe to call again for the same object while iterating on a
  script -- it replaces the previous handler rather than stacking a
  duplicate (confirmed: rebinding doesn't increase the handler count).
  Real-bpy only, since `bpy.app.handlers` doesn't exist without it -- see
  `examples/nested_point_deformation_blender.py`/
  `nested_uv_sphere_deformation_blender.py`, both updated to use this
  instead of a bake loop specifically so pressing Play actually animates
  them. Confirmed the handler fires correctly and cheaply on
  `scene.frame_set()`, repeatedly, headless; real interactive
  Play/scrubbing in a windowed session is a related but distinct claim,
  not separately verified (see CLAUDE.md's Testing status section).

If a channel needs continuity across calls either way -- easing between
explicit states, a lookup table -- give its function that state via a
closure; `point_data()` never manages it for you.

**Position is always local to the object, never world space** -- a
vertex's `.co` is relative to its own object's origin; Blender adds the
object's `.location`/rotation/scale on top when it works out where that
vertex ends up in the world. So an object's position (`Selection`/`Join`,
per-object) and its mesh's shape (`point_data`, per-vertex) are
independent and compose for free -- moving an object doesn't touch its
vertices, and reshaping its vertices doesn't touch its `.location`. If
you need a vertex's position expressed in *world* terms (a target
computed in world space that you need to convert to what to write into
`.co`), that conversion is on you -- subtract the object's own
`.location` yourself first; `point_attr`/`point_data` never do it for
you. See `examples/nested_point_deformation.py` for a worked example
contrasting two deformation styles (relative to a captured base shape,
vs. computed from scratch with no base shape at all) across several
objects, each with its own per-instance parameters.

**d3blender doesn't build primitive mesh geometry itself, on purpose --
same "object creation is left to the caller" boundary as everywhere
else here.** Blender's own `bpy.ops.mesh.primitive_uv_sphere_add()` (and
cube/cylinder/cone/torus) already produce correct topology (poles, quad
rings, real edges/faces); reinventing that in pure Python would be the
same "reinventing X badly" trap the hand-rolled CSS matcher was already
ripped out for. `point_attr`/`point_data` don't care how a mesh was
built, though -- they drive a real UV sphere's vertices exactly the same
way they'd drive a bare point cloud. See
`examples/nested_uv_sphere_deformation_blender.py` (real bpy only, no
mock sibling -- `bpy.ops` isn't something the mock has) for the same
two-sphere demo built on real primitives instead, including why a
*connected* mesh's "computed from scratch, no base shape" deformation
style needs to be anchored to each vertex's own rest position rather
than fully independent per vertex, to avoid tearing the surface --
d3blender doesn't help you build or maintain edges, so a deformation
formula that ignores the topology you started with will fight it.

`d3blender.mock.spawn_points(adapter, collection, name, vertices, **props)`
is the point-based sibling of `spawn()` -- gives the object a mesh sized
to `vertices` up front, instead of the default Blender primitive shape.

### `scale.py`
- `scale_linear(domain, range_)` -- `.invert(y)` also available
- `scale_band(domain_items, range_, padding=0.1)` -- `.bandwidth()`, `.step`
- `scale_ordinal(domain_items, range_)` -- cycles if there are more items than range values
- `scale_time(domain, range_)` -- `scale_linear` with a `datetime.datetime`/
  `datetime.date` domain instead of plain numbers; `.invert(y)` returns a
  `datetime`, a real inverse of what `scale()` accepts. Naive datetimes
  are treated as local time (Python's own `datetime.timestamp()`
  behavior) -- fine for "which day is this," not guaranteed correct
  across mixed timezones.
- `scale_sequential(domain, interpolator)` -- maps a continuous domain
  through `interpolator(t)` for `t` in `[0, 1]`, instead of onto a fixed
  range; `interpolator` is any `t -> value` callable. Clamps `t` to
  `[0, 1]` before calling `interpolator` -- unlike real d3, which only
  clamps if you opt in with `.clamp(true)` -- since an interpolator
  built for exactly `[0, 1]` will typically misbehave (values outside
  0-1) for out-of-domain input otherwise.
- `interpolate_rgb(start, end)` -- linear interpolation between two
  color tuples (3-channel RGB or 4-channel RGBA), for use as
  `scale_sequential()`'s interpolator -- the common "continuous color
  scale" case:
  ```python
  color = scale_sequential((0, max_revenue), interpolator=interpolate_rgb((0.9, 0.9, 0.9, 1), (0.9, 0.1, 0.1, 1)))
  bars.attr('fill', lambda el, d, i: color(d['revenue']))
  ```

### `shape.py` (mirrors pieces of d3-shape)
- `line(points, closed=False) -> [(p0, p1), ...]` -- one segment per
  consecutive pair of points, ready for `adapter.create_line_mesh(collection,
  name, segments)`. This is d3.line()'s actual job -- turning a
  data-derived array of points into a connected path -- not "generate a
  primitive shape" (which this project deliberately doesn't do, see
  "d3blender doesn't build primitive mesh geometry itself" above); the
  points already come from your own data or formula, this only decides
  which ones connect to which. `closed=True` also connects the last
  point back to the first (d3's `curveLinearClosed`), for an outline/
  polygon instead of an open path.

### `d3blender.array` (mirrors pieces of d3-array)
Not flattened into the top-level package -- `max`/`min`/`bin` collide with
Python builtins, so import it explicitly: `from d3blender import array`.
- `array.extent(items, value=None) -> (min, max)`, `array.max(...)`, `array.min(...)`
- `array.bin(items, value=None, thresholds=10) -> [Bin, ...]` -- buckets
  `items` into `thresholds` equal-width bins spanning the data's extent.
  Each `Bin` is a list of the items that fell in it, with `.x0`/`.x1`
  edges attached, so `len(some_bin)` is the frequency and
  `array.max(bins, value=len)` gives the tallest bin -- same idiom as
  d3's `d3.max(bins, d => d.length)`. Simplified vs. d3.bin(): fixed-width
  bins, not d3's "nice" auto-rounded edges -- fine for sizing bars, not
  for axis ticks that need to land on round numbers.

### `d3blender.axis`
The "ticks are just a set of lines" version of d3's `axisBottom()`/
`axisLeft()` -- no domain baseline, no tick-label text, just a short line
segment per tick value.
- `axis.ticks(domain, count=10)` -- `count` evenly spaced values across
  `domain` (same fixed-width simplification as `array.bin()`, not d3's
  "nice" rounded values)
- `axis.tick_lines(scale, values, place, tick_vector) -> [(p0, p1), ...]`
  -- one 3D line segment per tick value. `place(scale(v)) -> (x, y, z)`
  and `tick_vector` (a fixed `(dx, dy, dz)` offset) are supplied by the
  caller, since d3blender charts don't share one fixed 2D plane (compare
  `bar_chart.py`, which stands bars up along z, to `scatter_plot.py`,
  which lies flat at z=0)
- Feed the result straight to `adapter.create_line_mesh(collection, name,
  segments)` (below) to turn it into an object

### Adapters
- `d3blender.adapter.SceneAdapter` -- the engine; works against anything
  shaped like `bpy.data` (duck-typed, see below)
  - `.get_or_create_collection(name, parent=None)` -- the Blender
    equivalent of `d3.create('svg')`: get-or-create a named collection to
    serve as a join's root. Idempotent, so it's safe to call on every
    rerun. Works the same way on the mock and on `LiveBlenderAdapter`
    (which additionally links the collection into the scene -- an
    unlinked `bpy.data.collections.new()` result is an invisible orphan
    datablock).
  - `.create_line_mesh(collection, name, segments)` -- one mesh object
    containing one edge per `(p0, p1)` segment (e.g. axis ticks), rather
    than one object per segment. See `d3blender.axis` above.
  - `.gn_inputs(modifier)` -- `{name: value}` for a Geometry Nodes
    modifier's inputs. See "Modifiers and Geometry Nodes inputs" above.
- `d3blender.blender_adapter.get_adapter()` -- the one you actually call
  inside Blender; the only place in this package that imports `bpy`
  - `d3blender.blender_adapter.live_point_data(adapter, el, **channels)`
    -- wires `points.point_data()` to `bpy.app.handlers.frame_change_pre`
    for live scrub/Play-driven updates. See "Per-vertex data" above.
- `d3blender.mock` -- `MockObject` / `MockCollection` / `MockModifier` /
  `MockModifierCollection` / `MockMaterial` / `MockMaterialSlot` /
  `MockNodeGroup` / `MockNodeGroupInterface` / `MockNodeGroupInterfaceItem` /
  `MockMesh` / `MockAttributeCollection` / `MockPointAttribute` /
  `MockPointAttributeItem` / `MockVertex`, a fake scene shaped like
  `bpy.data` for testing without Blender installed; `new_scene(name)`
  builds an adapter with one collection, `spawn(adapter, collection,
  name, type_='MESH', **props)` creates and links an object into it, and
  `spawn_points(adapter, collection, name, vertices, **props)` is the
  point-based sibling -- the demo-scaffolding every example needs

## Using it inside Blender

`d3blender` is pure Python (its only dependency, `beautifulsoup4`, is
pure Python too), so it doesn't need a compiler or matching wheels for
Blender's bundled interpreter -- just get the `d3blender` package
directory onto Blender's Python path (drop it into
`<blender>/scripts/modules/`, or `pip install --target` into a folder you
add to `sys.path` in your addon).

```python
import bpy
from d3blender import select
from d3blender.blender_adapter import get_adapter

adapter = get_adapter()   # cheap; call fresh whenever the scene may have changed
select(adapter, 'mesh:selected').attr('hp', 100)
```

This is tested against real `bpy` (PyPI's headless module, see
`tests/blender/`), but not yet against the full Blender application --
if something doesn't match your Blender version, that's useful
information. Please open an issue with the version number and what
broke.

### Working with other Blender-scripting libraries

`d3blender` doesn't create objects or build node trees itself by design
(see "Things that are genuinely custom" -- object/geometry creation is
left to you). It composes fine with libraries that do:
[`databpy`](https://github.com/BradyAJohnston/databpy) for creating
objects/collections and storing per-point attributes, and
[`nodebpy`](https://github.com/BradyAJohnston/nodebpy) for building
Geometry Nodes trees from Python instead of the node editor. Neither
needs to know `d3blender` exists -- `d3blender` just selects/queries/
mutates whatever real `bpy` objects they produce, including their
Geometry Nodes modifier inputs (see "Modifiers and Geometry Nodes
inputs" above). `examples/geometry_nodes_countries.py` is a full,
three-library example: nodebpy builds a shared Geometry Nodes tree,
databpy creates one small object per country, d3blender selects the
populous countries and changes their Geometry Nodes inputs.

**Version caveat:** `nodebpy` versions its node-class definitions per
Blender release (e.g. `v520.8.0` targets Blender 5.2.x specifically) --
check its [releases page](https://github.com/BradyAJohnston/nodebpy/releases)
for a tag matching your actual Blender version before relying on it;
using a mismatched version risks a node's socket names/defaults having
quietly changed underneath you.

### Live vs. cached

`get_adapter()` snapshots `bpy.data.objects`/`.collections` at call time
and builds one small reverse index (which collection contains which
sub-collection) from that snapshot. It does **not** stay live if you
create or delete objects afterward -- call `get_adapter()` again. This is
a deliberate simplicity trade-off: Blender scenes are rarely more than a
few thousand objects, so rebuilding is cheap, and a cache that can go
stale is a worse bug than a cache that doesn't exist.

(`get_or_create_collection()` is the one exception -- it updates the
adapter's own `.collections` list and parent index directly, so it stays
correct without another `get_adapter()` call. That only covers changes
made *through* the adapter, though; collections or objects you create
via raw `bpy.ops`/`bpy.data` calls still need a fresh `get_adapter()`.)

## Known limitations

- A selector can't mix collection-axis and parent-axis combinators (see above).
- Numeric attribute comparisons and pseudo-classes only apply to the
  rightmost compound in a selector -- `#Weapons[level>2] > mesh` will
  parse but the `[level>2]` predicate is not evaluated against the
  ancestor. Put predicates on the thing you're actually selecting.
- `Selection.select()` (scoped queries) currently re-queries the whole
  scene and intersects with the descendant set, rather than building a
  doc scoped to just that subtree. Fine for typical scene sizes; would be
  worth revisiting for very large scenes.
- `array.bin()` uses fixed-width bins, not d3's "nice" auto-rounded edges
  -- fine for sizing bars, not for axis ticks that need round numbers.
- `d3blender.axis` covers tick marks (line segments) only -- no domain
  baseline and no tick-label text (`d3.axisBottom`'s numbers/category
  names rendered as text). Text/label geometry (`bpy.data.curves`-based
  font objects) is a bigger, separate design question -- deliberately
  out of scope for now.
- Geometry Nodes input lookup assumes the Blender 4.0+/5.x interface
  shape (`node_group.interface.items_tree`) -- no fallback to the
  pre-4.0 `node_group.inputs` API.
- The `[key...]` bracket-selector syntax can't reach a dotted or
  spaced nested name (a modifier/node-group name with a `.001` suffix, a
  multi-word Geometry Nodes input) -- it's a single unescaped string.
  Use `.filter(lambda el: adapter.get_attr(el, (...)) > x)` for those.
- `blender_adapter.py` is now tested against real `bpy` (PyPI's headless
  module, see `tests/blender/`), but not yet against the full Blender
  application or the `databpy`/`nodebpy`-dependent examples.
- An object linked *only* into the scene's root collection
  (`bpy.context.scene.collection`, not a collection you created) is
  invisible to `select()` -- that root collection isn't itself a member
  of `bpy.data.collections`, which is what `get_adapter()` builds
  `adapter.collections` from. Doesn't affect idiomatic usage, since
  `get_or_create_collection()` always produces a real tracked collection;
  see CLAUDE.md's Testing status section for the full explanation.
- `point_data()`/`set_point_attr()` never resize a mesh and never track
  per-vertex identity -- a changing point count is always your job to
  handle (rebuild the mesh explicitly), and there's no enter/update/exit
  at the vertex level the way `Join` has at the object level.
  `live_point_data()` (real bpy only) does wire up live scrub/Play-driven
  updates, though -- see the "Per-vertex data" section above.
- `Join.join()`'s shape-name shorthand covers the standard `bpy.ops.mesh`
  primitives only (`uv_sphere`, `ico_sphere`, `cube`, `cylinder`, `cone`,
  `plane`, `torus`, `circle`) -- nothing that needs a light/camera/GN
  setup/databpy or nodebpy object, and no auto-inferred target
  collection (see "Join" above for why). Pass your own `enter=...`
  callable for anything else, same as before this existed.

## Project layout

```
src/d3blender/
    __init__.py         public API
    adapter.py           SceneAdapter -- the engine, works against anything bpy-shaped
    blender_adapter.py    the only file that imports bpy
    scene_doc.py          builds the two synthetic BeautifulSoup docs
    query.py              selector compiler + soupsieve delegation
    selection.py           Selection / Join
    scale.py                scale_linear / scale_band / scale_ordinal / scale_time / scale_sequential
    shape.py                 line() -- connect points into a path (mirrors d3-shape)
    array.py                  bin / extent / max / min (mirrors d3-array)
    axis.py                    ticks / tick_lines (line-segment tick marks)
    points.py                   point_data() -- data bound to mesh vertices
    mock.py                    fake bpy-shaped scene for testing
examples/                runnable, mirror the README snippets
tests/                    pytest suite (uses mock.py, no Blender required)
tests/blender/             real-bpy suite (needs the blender-test extra; see its README.md)
```

## License

MIT -- see `LICENSE`.
