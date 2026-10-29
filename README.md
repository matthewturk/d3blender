# d3blender

**EXPERIMENTAL!!!!!**  This was largely vibe-coded, and probably doesn't work
that amazingly well, but it meets some specific needs I had.

A d3.js-flavored selector, join/reconciliation, and animation layer over
Blender's scene graph. Written in Python, for Python.

```python
import d3blender as d3

rows = d3.csv('sales.csv')                       # typed: numbers, bools, dates, None
chart = d3.collection('Chart')                   # get-or-create
y = d3.scale_linear().domain((0, d3.array.max(rows, lambda d: d['revenue']))).nice().range((0, 4))

bars = (d3.select_all(chart)                     # the collection's objects, chart as parent
        .data(rows, key='month')                 # identity = the month column
        .join('cube')                            # new rows -> new cubes in chart; gone rows -> removed
        .attr('location', lambda el, d, i: (i * 1.5, 0, y(d['revenue']) / 2))
        .attr('scale', lambda el, d, i: (0.6, 0.6, y(d['revenue']))))

bars.entered.transition(20, delay=lambda el, i: i * 3).attr('location', lambda el, d, i: (i * 1.5, 0, y(d['revenue'])))
d3.select('.enemy[hp>0]').attr('hp', lambda el: el['hp'] - 10)
```

Rerun the script after editing the CSV or a setting and the same objects
update in place. Inside Blender no adapter argument is needed; outside it
(tests, the mock) you pass one: `select(adapter, '...')`.

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
import d3blender as d3          # inside Blender

height = d3.scale_linear().domain((0, 100)).range((0.2, 4.0))

d3.select('mesh.bar').attr('scale', lambda el: (1, 1, height(el.get('value', 0))))
```

The same thing with an explicit adapter, which is what the mock, tests,
and code written before the adapter became optional use:

```python
from d3blender import select, scale_linear
from d3blender.blender_adapter import get_adapter

adapter = get_adapter()
height = scale_linear(domain=(0, 100), range_=(0.2, 4.0))
select(adapter, 'mesh.bar').attr('scale', lambda el: (1, 1, height(el.get('value', 0))))
```

**Ready-to-run scripts:** `examples/script_runner/` holds three Script
Runner scripts (bar chart, scatter plot, CSV to points) with sample
CSVs -- see "Script Runner examples" below.

## API

### `select(target)` / `select(adapter, target)` -> `Selection`
Top-level query against the whole scene. The adapter is optional: with
one argument (or `adapter=None`), `select()` builds a **fresh**
`get_adapter()` snapshot for that call, so it always sees the current
scene (see "Live vs. cached"). Pass one explicitly to pin it (and
outside Blender you must, or call `d3blender.set_default_adapter(adapter)`
once -- that also takes a zero-argument factory). `target` is usually a selector
string, but -- mirroring d3's `d3.select(node)` -- it can also be an
element, or an iterable of elements, to wrap directly with no CSS
involved. Reach for that form to re-wrap an element you already have
(e.g. to `.keyframe()` it on a rerun): Blender's own auto-suffixed names
like `"Cube.001"` aren't valid `#name` selector text, since CSS reads the
`.` as a class.

### `select_all(target, selector=None, adapter=None) -> Selection`
d3's `parent.selectAll(...)`, and the usual way to start a join. With a
**collection**, it selects that collection's own objects and remembers
the collection as the selection's `parent`, which `.join()` then uses as
the home for new elements (below). With a selector string or elements, it
behaves like `select()`. `selector` narrows the result (a selector
string or predicate, as in `.filter()`): use it when one collection
holds several separately joined groups, e.g. `select_all(chart, '.bar')`
together with `.classed('bar', True)` after that group's join --
otherwise a join would count the other group's keyed objects as its own
and remove them.

### `collection(name, parent=None, adapter=None)`
`adapter.get_or_create_collection()` without holding an adapter (see
Adapters for how `parent` scopes the lookup).

### `Selection`

Every callable a `Selection` method accepts -- `.attr()`'s `value`,
`.each()`'s `fn`, `.keyframe()`'s attr values, `.filter()`'s
`predicate` -- can be written as `fn(el)`, `fn(el, i)`, or
`fn(el, d, i)`, and the right one is picked automatically by the
callable's own arity (a `*args` callable, like a generic wrapper, gets
all three). `d` is this element's own bound datum -- the same
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
  this is the whole "transition" story: `sel.keyframe(1, location=a).keyframe(30, location=b)`.
  `frame` can also be a callable (same `fn(el)`/`fn(el, i)`/`fn(el, d, i)`
  shapes, evaluated once per element) so each element lands on its own
  frame -- e.g. `sel.keyframe(lambda el, d, i: d['frame'], location=lambda el, d, i: d['pos'])`
  for data whose rows each carry their own time. Custom properties work
  too (`sel.keyframe(10, hp=5)`): bpy's own `keyframe_insert('hp')`
  rejects a custom prop by bare name, so the adapter retries it as the
  ID-property path `'["hp"]'` (confirmed on 5.2 and 5.4). Nested paths
  (`'modifiers.Bevel.width'`, tuples) aren't translated into RNA data
  paths, so keyframe those on the owning struct yourself
- `.transition(duration=24, delay=0, start=None)` -> `Transition` --
  d3's transitions on top of `.keyframe()`. Each `.attr(key, value)` on
  the transition keyframes the element's *current* value at
  `start + delay` and the new value at `start + delay + duration` (in
  frames; `start` defaults to the scene's current frame). Any of the
  three can be a per-element callable, so staggering is
  `delay=lambda el, i: i * 3`. `.attr()` calls chain into one change;
  `.duration(n)`/`.delay(n)` re-time the `.attr()` calls after them;
  `.transition(...)` on a transition starts the next one where each
  element's previous one ended; `.selection()` gets back the Selection.
  An attr with no current value (a custom prop that doesn't exist yet)
  only gets the end keyframe. There's no easing in Python -- set the
  F-curve interpolation in Blender (or the default in Preferences >
  Animation)
- `.filter(predicate)` -- a selector string, or a callable as above;
  survivors keep their own bound datum (`kept.datum` lines up with
  `kept.elements`)
- `.select(selector_str, axis='collection'|'parent')` -- scoped descendant
  query within the current selection's subtree. Returns an *unbound*
  Selection -- there's no 1:1 parent-datum-to-child mapping to fall back
  on (one element can have many matching descendants), so this doesn't
  try to guess one; rebind with a fresh `.data()` if you need one
- `.remove()` -- removes every element in the selection
- `.data(items, key=None) -> Join` -- `key` identifies an item across
  reruns: a field name (`key='id'` is `d['id']`), a one-argument
  callable `fn(d)`, or the original two-argument `fn(i, d)` (note: index
  first, the reverse of d3's `(d, i)`). Default: the item's index
- `.parent` -- the collection a `select_all(collection)` selection came
  from (else `None`); `.entered` / `.updated` -- on a `.join()` result,
  the newly created vs. already existing elements, each bound to its
  data (else `None`)

### `Join`
- `.join(enter, update=None, exit=None) -> Selection` -- reconciles by
  identity (a stamped `d3_key` custom property). `enter(d)` must return
  the created element; `update(el, d)` and `exit(el)` are optional (a
  missing `exit` just calls `adapter.remove(el)`). The returned
  `Selection` is the **merged** enter + update selection in data order,
  so `.attr()`/`.keyframe()`/`.transition()` chained after `.join()`
  apply to every element the data describes; `.entered`/`.updated` hold
  the two halves. Its `.datum` is each element's own item from `items`,
  in the same order -- rerunning `.data(newItems).join(...)` rebinds it
  to the new items, not stale ones.
- When the selection came from `select_all(collection)`, that collection
  is the default home for new elements, like d3 appending to the parent:
  the shape-name form below uses it unless `collection=` is given, and
  an element a callable `enter` returns that isn't in any collection yet
  (say, a bare `bpy.data.objects.new()`) is linked into it. An element
  `enter` already linked somewhere is left alone. With no parent, nothing
  changes from before.
- `enter`/`update`/`exit` are per-element callables. d3 v7's
  `join(enter => enter.append(...), update => ...)` (callables that
  receive whole sub-selections) isn't supported: it can't be told apart
  from the per-element `enter(d)` form by its signature. Use `.entered`/
  `.updated` on the result for the same effect.
- `enter` can also be a shape name string (e.g. `.join('uv_sphere',
  collection=chart)`) -- real d3's own `selection.join("circle")`
  shorthand, dispatched through `adapter.creator(name, collection,
  **create_kwargs)`. `collection` comes from the selection's parent
  (`select_all(chart)...join('uv_sphere')`) or must be passed; it never
  defaults to Blender's ambient "active collection", which risks landing
  objects somewhere invisible to `select()` -- see Known limitations; other kwargs are creation-time
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
through `modifier.properties.inputs[key]["value"]` -- as of Blender 5.2,
GN modifier inputs stopped being plain ID properties
(`modifier[key] = value`, which now raises "id properties not supported
for this type") and moved onto this dedicated RNA property wrapper; this
project targets 5.3+, so there's no fallback to the pre-5.2 shape.
Confirmed unchanged on **Blender 5.4.0 Alpha** (the full application,
via `tests/blender/run_in_blender_app.py`): path-walker get/set
round-trips for float, int, bool, vector, object and material sockets.
So the same syntax reaches Geometry Nodes inputs too, no special-cased API:

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
here is version-sensitive and has changed twice**, so check which shape
your Blender has:

- **Blender 5.4** (checked on 5.4.0 Alpha): compositing is a list of
  *effects*, `scene.compositor_effects` (`new(name)`/`remove`/`clear`,
  plus `.active`). Each `SceneCompositorEffect` has its own `node_group`
  (assign a `CompositorNodeTree`), `enable_for_render`,
  `enable_for_preview`, `is_active` and `properties`.
  `scene.compositing_node_group` and `scene.use_nodes` still exist but
  are deprecated (removal expected in 6.0); `compositing_node_group` is
  now a shim for the active effect's group.
- **Blender 5.2** (the PyPI wheel): no `compositor_effects`. The
  compositor is a node-group datablock on `scene.compositing_node_group`
  (not the older `scene.node_tree`), and `use_nodes = True` doesn't
  create that group for you the way it does for a material.
- 5.3 hasn't been checked. Test for the property on the instance
  (`hasattr(scene, 'compositor_effects')`), or on the type via
  `'compositor_effects' in bpy.types.Scene.bl_rna.properties`. A
  class-level `hasattr(bpy.types.Scene, ...)` is always `False`, because
  RNA properties aren't class attributes.

```python
group = bpy.data.node_groups.new('Compositing', 'CompositorNodeTree')
if hasattr(scene, 'compositor_effects'):          # 5.4
    scene.compositor_effects.new('FX').node_group = group
    prefix = ('compositor_effects', 'FX', 'node_group')
else:                                             # 5.2
    scene.compositing_node_group = group
    scene.use_nodes = True
    prefix = ('compositing_node_group',)
```

...after which a node's inputs resolve exactly like a material's. On 5.4
the effect-name segment (`'FX'`) resolves through the effects
collection's `.get(name)`, the path-walker's existing fallback; no
special handling was needed:

```python
adapter.set_attr(scene, prefix + ('nodes', 'Glare', 'inputs', 'Threshold', 'default_value'), 0.5)
adapter.set_attr(scene, ('compositor_effects', 'FX', 'enable_for_render'), False)  # 5.4 only
```

Use the tuple form here, as everywhere: an effect or node name
containing a `.` would mis-split in the dotted-string form.

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

Every scale works both ways -- the original call form and d3's chaining
(setters return the scale; with no argument they're getters):

```python
x = scale_linear((0, 24), (0.2, 4.0))
x = scale_linear().domain((0, 24)).range((0.2, 4.0))     # same scale
y = scale_linear().domain((0.3, 97)).nice().range((0, 4)) # domain becomes (0, 100)
y.ticks(5)       # [0, 20, 40, 60, 80, 100] -- d3's round 1/2/5 x 10^k steps
y.invert(2.0)    # 50.0
y.clamp()        # out-of-domain input pins to the range ends; .clamp(False) undoes
y.copy()         # an independent copy
```

- `scale_linear(domain, range_)` -- `.domain()`, `.range()`, `.nice(count=10)`,
  `.ticks(count=10)`, `.clamp()`, `.invert(y)`, `.copy()`. The range can
  be numbers or equal-length tuples (positions, RGBA colors), interpolated
  per component.
- `scale_band(domain_items, range_, padding=0.1)` -- `.domain()`,
  `.range()`, `.padding()`, `.bandwidth()`; `.step` stays a plain number
  (not d3's `step()` method), because existing code reads it that way.
  `padding` is one fraction split evenly around each band (no separate
  inner/outer padding or align). An unknown item raises `KeyError`.
- `scale_ordinal(domain_items, range_)` -- cycles if there are more
  items than range values. `.domain()`, `.range()`, `.unknown(value)`.
  With an explicit domain, unknown items map to `range_[0]` (the original
  behaviour) unless `.unknown()` is set. With **no** domain
  (`scale_ordinal().range(palette)`), the domain is implicit as in d3:
  each new item is added on first use, so colors are handed out in order
  of appearance.
- `scale_time(domain, range_)` -- `scale_linear` with a `datetime.datetime`/
  `datetime.date` domain instead of plain numbers; chains like
  `scale_linear`, and `.invert(y)` returns a `datetime`, a real inverse of
  what `scale()` accepts. No `.ticks()`/`.nice()` (d3's calendar-aware
  time ticks are a different algorithm). Naive datetimes are treated as
  local time (Python's own `datetime.timestamp()` behavior) -- fine for
  "which day is this," not guaranteed correct across mixed timezones.
- `scale_sequential(domain, interpolator)` -- maps a continuous domain
  through `interpolator(t)` for `t` in `[0, 1]`, instead of onto a fixed
  range; `interpolator` is any `t -> value` callable. Also
  `scale_sequential(interpolator)` (domain `[0, 1]`) and
  `scale_sequential().domain(...).interpolator(...)`. Clamps `t` to
  `[0, 1]` by default -- unlike real d3, which only clamps if you opt in
  with `.clamp(true)` -- since an interpolator built for exactly
  `[0, 1]` will typically misbehave (values outside 0-1) for
  out-of-domain input otherwise. `.clamp(False)` opts out. `.nice()` and
  `.ticks()` work as for `scale_linear`.
- `ticks(start, stop, count=10)` -- d3.ticks as a plain function.
- `interpolate_rgb(start, end)` -- linear interpolation between two
  color tuples (3-channel RGB or 4-channel RGBA), for use as
  `scale_sequential()`'s interpolator -- the common "continuous color
  scale" case:
  ```python
  color = scale_sequential((0, max_revenue), interpolator=interpolate_rgb((0.9, 0.9, 0.9, 1), (0.9, 0.1, 0.1, 1)))
  bars.attr('fill', lambda el, d, i: color(d['revenue']))
  ```

### Loading data: `csv()`, `tsv()`, `json()` (mirrors d3-fetch + d3.autoType)

```python
import d3blender as d3
rows = d3.csv('sales.csv')     # list of dicts; rows.columns is the header order
```

Values are auto-typed by default, like `d3.csv(url, d3.autoType)`:
empty -> `None`, `true`/`false` -> `bool`, whole numbers -> `int`, other
numbers -> `float`, `NaN` -> `float('nan')`, `YYYY-MM-DD` ->
`datetime.date`, ISO date-times -> `datetime.datetime` (timezone-aware if
the string has an offset or `Z`); everything else stays a string. Pass
`typed=False` for raw strings, or `row=fn` (d3's row function:
`fn(d)`, `fn(d, i)` or `fn(d, i, columns)`; return `None` to drop the
row). Leading zeros are dropped by typing (`'007'` -> 7), as in d3, so
read identifier columns with `typed=False` or a row function. A UTF-8
byte-order mark is stripped. `tsv()` is the tab-separated variant,
`dsv(path, delimiter)` the general one, and `json(path)` just parses a
file. Local paths only and synchronous; a Blender-relative path
(`//data.csv`) needs `bpy.path.abspath()` first. Stdlib only. These
aren't in `__all__`, so a star-import doesn't shadow the stdlib `csv`/
`json` modules; use them as `d3.csv(...)`. `auto_type(row)` and
`auto_type_value(s)` are exposed too.

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
    - `parent=None` looks `name` up across **every** collection (the
      original behaviour, kept for backward compatibility) and creates a
      top-level one if nothing matches.
    - With `parent`, the lookup is scoped to **`parent`'s own direct
      children**, so two roots can each get their own `"Halos"`:

      ```python
      root = adapter.get_or_create_collection('Run2', parent=bpy.context.scene.collection)
      halos = adapter.get_or_create_collection('Halos', parent=root)
      ```

      Real Blender collection names are global, so if `"Halos"` already
      exists elsewhere the new child comes back as `"Halos.001"` --
      expected. Every collection this method creates is stamped with a
      `d3_name` custom property holding the requested name (the same idea
      as `Join`'s `d3_key`), and the parent-scoped lookup matches on that
      stamp as well as the exact name, so a rerun finds `"Halos.001"`
      again instead of creating `"Halos.002"`. The stamp is also a normal
      selector attribute: `collection[d3_name=Halos]`. A child created
      *without* the stamp (by hand, or before this existed) is only found
      by its exact name.
    - `parent` doesn't have to be a collection the adapter tracks --
      `bpy.context.scene.collection` (the scene root, which isn't in
      `bpy.data.collections`) works, and the result stays visible to
      `select()` exactly like a `parent=None` collection would.
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
import d3blender as d3
d3.select('mesh:selected').attr('hp', 100)    # a fresh adapter per call

# or, explicitly:
from d3blender.blender_adapter import get_adapter
adapter = get_adapter()   # cheap; call fresh whenever the scene may have changed
d3.select(adapter, 'mesh:selected').attr('hp', 100)
```

This is tested against real `bpy` (PyPI's headless 5.2 module, see
`tests/blender/`) and, headless, inside the Blender 5.4 application. If
something doesn't match your Blender version, that's useful information.
Please open an issue with the version number and what broke.

### Script Runner examples

`examples/script_runner/` is a folder of ready-to-run scripts for the
Script Runner extension (`PARAMS` dict + `execute(context, params)`).
Add the folder under **Preferences > Add-ons > Script Runner** as a
*Scripts* folder; d3blender must be importable in Blender. Neither
project imports the other.

| script | what it builds | rerun behaviour |
|---|---|---|
| `bar_chart_csv.py` | one cube per row, band x scale, nice()d linear height, color by value; optional staggered grow-in animation | joined by the category column: bars update in place, new rows add bars, missing rows remove them |
| `scatter_csv.py` | one ico-sphere per row, x/y/z scaled into a cube, size and categorical color columns | joined by an id column (or row number): spheres move/resize/recolor in place |
| `csv_to_points.py` | one mesh, one vertex per row; every other numeric column becomes a point attribute; optional Geometry Nodes "Mesh to Points" display whose Radius is set through the path-walker | same object found again; values rewritten in bulk; mesh rebuilt only if the row count changed; attributes for dropped columns removed |

Each takes a CSV file (empty = the bundled sample: `sales.csv`,
`stars.csv`, `spiral_points.csv`) and a target collection (empty = one
named after the chart, created under the scene). Colors use each
object's Color property, read by a shared "d3 Object Color" material
(Object Info node), so they render too. They're tested by
`tests/blender/test_script_runner_examples.py`, which calls `execute()`
with a params dict exactly as Script Runner does, including reruns.

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

The adapter-less forms (`select('...')`, `select_all(coll)`,
`collection(name)`) follow the same rule: each call takes a new
snapshot, and the returned selection keeps the adapter it was built
with for everything chained off it. So a long chain sees the scene as of
its first call (plus the objects it creates itself); start a new
`select()` after changing the scene some other way.

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
- `blender_adapter.py` is tested against real `bpy` (PyPI's headless
  5.2 module, see `tests/blender/`), and the same suite has been run
  inside the full Blender 5.4.0 Alpha application
  (`tests/blender/run_in_blender_app.py`) -- headless/`--background`
  only, not an interactive session. The `databpy`/`nodebpy`-dependent
  examples still aren't covered.
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
    selection.py           Selection / Join / Transition
    fetch.py               csv / tsv / json / auto_type (mirrors d3-fetch + d3-dsv)
    scale.py                scale_linear / scale_band / scale_ordinal / scale_time / scale_sequential
    shape.py                 line() -- connect points into a path (mirrors d3-shape)
    array.py                  bin / extent / max / min (mirrors d3-array)
    axis.py                    ticks / tick_lines (line-segment tick marks)
    points.py                   point_data() -- data bound to mesh vertices
    mock.py                    fake bpy-shaped scene for testing
examples/                runnable, mirror the README snippets
examples/script_runner/   Script Runner scripts + sample CSVs (see "Script Runner examples")
tests/                    pytest suite (uses mock.py, no Blender required)
tests/blender/             real-bpy suite (needs the blender-test extra; see its README.md)
```

## License

MIT -- see `LICENSE`.
