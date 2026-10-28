# CLAUDE.md

Context for an AI assistant picking up this repo. Read this before making
changes -- several design decisions look arbitrary until you know why.

## What this is

`d3blender`: a d3.js-flavored selector / join-reconciliation / animation
layer over Blender's scene graph. A Python library, not a UI, not an
addon with panels -- you write plain Python against `bpy` and get
`select(adapter, '.enemy[hp>0]')`-style queries and d3's
`selection.data(array).join()` reconciliation pattern.

Read `README.md` first -- it has the selector grammar, API reference, and
known limitations. This file is about *why* things are built the way they
are, for whoever (human or AI) touches the code next.

## The one thing to internalize before touching anything

**Blender has two independent hierarchies, and CSS only has one.**

- Collection containment (`.users_collection`, `Collection.children`)
- Transform parenting (`obj.parent` -- rigs, instancing)

Every design decision in `query.py` and `scene_doc.py` exists because of
this. There are two combinator axes (` `/`>` for collection, `~`/`~>` for
parenting), two synthetic documents get built per query, and a selector
is rejected if it mixes both axes. Don't try to "simplify" this into one
tree -- the two hierarchies are genuinely semantically different and
conflating them silently produces wrong answers, not just ugly code.

## Architecture, in one paragraph

`query.py` compiles a selector string into `(axis, css_string,
predicates)`. `scene_doc.py` serializes the *current* scene into a small
BeautifulSoup document for whichever axis was requested (real objects/
collections become synthetic tags: type→tag name, `.class`→`class` attr,
`#id`→`id` attr, custom props→attrs). `css_string` gets handed straight
to `soup.scene.select(...)`, which is soupsieve doing real CSS matching --
that's the entire structural engine, and it isn't ours. `predicates` are
the things CSS can't express (numeric comparison, custom pseudo-classes)
and get applied as a plain Python filter on the results afterward.
`selection.py` wraps results in `Selection`/`Join` for the d3-shaped verbs
(`.attr()`, `.each()`, `.filter()`, `.select()`, `.data().join()`,
`.keyframe()`, `.transition()`). `fetch.py` loads CSV/TSV/JSON into
plain row dicts (d3-fetch). `adapter.py` is the only thing that knows how to read a
scene (duck-typed against real `bpy` shapes); `blender_adapter.py` is the
only file that imports `bpy`.

**If you're about to write matching logic (type/class/id/attribute
matching, tree traversal for combinators), stop -- that almost certainly
belongs in soupsieve via a selector string, not in new Python.** This
codebase used to have a hand-rolled ~250-line parser/matcher; it was
deleted in favor of delegating to soupsieve once we realized it was
reinventing CSS badly. Don't bring that pattern back.

## `select()` also takes an element directly

Mirroring `d3.select(node)`, `select(adapter, target)` accepts a non-string
`target` (an element, or an iterable of elements) and just wraps it in a
`Selection` -- no CSS. This exists because re-selecting an already-known
element via `select(adapter, f'#{el.name}')` is a real trap: Blender
auto-suffixes duplicate names with a dot (`"Cube.001"`), and CSS reads
that dot as a class selector, so it throws. Examples that need to
`.keyframe()` one known element (`update_pattern.py`,
`staggered_animation.py`, `scatter_plot_3d.py`) use `select(adapter, el)`
for exactly this reason -- don't revert them to the `#name` form.

`d3blender.mock` also has `new_scene()` / `spawn()` now, to stop every
example from hand-rolling the same object-creation-and-linking function.
These are demo scaffolding only, not selector-engine code -- there's no
real-Blender equivalent, since object creation there goes through
`bpy.ops`/`bpy.data.objects.new()`.

## `array.py` and `get_or_create_collection()` -- how far d3 parity goes

These exist to make d3.js-style "bin the data, size a bar per bucket"
code (the classic Observable histogram notebook) portable to
`d3blender`, without pulling in things a 3D scene doesn't have an
opinion about yet:

- `array.py` mirrors `d3.bin()`/`d3.max()`/`d3.min()`/`d3.extent()` --
  pure data transforms, no `bpy` involved, so they're cheap and safe to
  add. `bin()` deliberately uses fixed-width bins instead of d3's "nice"
  auto-rounded edges -- good enough for sizing bars, not for axis ticks
  that need to land on round numbers. Not flattened into the top-level
  package like `scale.py` is: `max`/`min`/`bin` shadow builtins, so it's
  `from d3blender import array; array.max(...)`.
- `SceneAdapter.get_or_create_collection(name, parent=None)` is the
  Blender-flavored `d3.create('svg')` -- a join's root container.
  Base `SceneAdapter` does bookkeeping generically (updates
  `.collections`/`._collection_parent` directly, so it doesn't need
  another `get_adapter()` call afterward); `LiveBlenderAdapter` overrides
  it fully (same pattern as `remove()`) because a real
  `bpy.data.collections.new()` result also needs linking into the scene
  -- otherwise it's an orphan datablock, invisible in the outliner.
- **`parent` scopes the lookup; `parent=None` deliberately doesn't.**
  Found when the library was first adopted in a real script (a halo-
  merger-tree importer building `Root/Halos` + `Root/Trails` per run):
  the original lookup searched *every* collection by name even with a
  `parent`, so a second root's `"Halos"` silently returned the first
  root's. With `parent`, it now only searches `parent`'s direct
  children (`_find_child_collection`). `parent=None` keeps the old
  global lookup -- changing it to top-level-only would silently start
  creating duplicates in existing scripts that relied on it finding a
  nested collection, which is worse than the inconsistency.
- **Real collection names are global, hence the `d3_name` stamp.** A new
  child whose name is taken elsewhere comes back as `"Halos.001"`
  (confirmed against real bpy) -- unavoidable. Without a stamp, the
  rerun's scoped lookup for `"Halos"` would miss it and create
  `"Halos.002"` every run. Created collections get
  `COLLECTION_NAME_PROP = 'd3_name'` = the requested name, matched after
  the exact name. Same "stamp identity, don't parse names" reasoning as
  `Join`'s `d3_key` and the tuple-path rule -- don't replace this with a
  regex that strips `.NNN` suffixes. Known gap: a child created *without*
  the stamp (by hand, or by pre-stamp code) under an auto-suffixed name
  isn't recognized; one extra stamped collection gets created once, then
  reruns are stable.
- **An untracked `parent` must not go into `_collection_parent`.**
  `parent=bpy.context.scene.collection` (the natural way to say "a root
  in this scene") used to record the scene root -- which isn't in
  `bpy.data.collections` -- as the new collection's parent, so
  `top_level_collections()` dropped it and nothing tracked could reach
  it: the whole subtree was invisible to `select()` (confirmed against
  real bpy). `_record_collection_parent` now applies the same rule a
  fresh `get_adapter()`'s `_build_collection_parent_index` does: only
  tracked collections count as parents.

**Axis ticks now exist, scoped down to lines only.** `axis.py` mirrors
d3's `axisBottom()`/`axisLeft()` with no domain baseline and no
tick-label text -- `axis.ticks(domain, count)` picks values (same
fixed-width simplification as `array.bin()`), `axis.tick_lines(scale,
values, place, tick_vector)` turns them into `(p0, p1)` segments, and
`SceneAdapter.create_line_mesh(collection, name, segments)` builds one
mesh object with one edge per segment (not one object per tick -- see
`get_or_create_collection()`'s precedent: a line segment is as
unambiguous a "thing" as a collection, unlike picking a primitive shape
for a data point). `place`/`tick_vector` are deliberately the caller's
job, not `axis.py`'s -- d3blender charts don't share one fixed 2D plane
(`bar_chart.py` stands bars up along z at y=0; `scatter_plot.py` lies
flat at z=0), so `axis.py` can't assume which spatial axis is "the" x or
y the way an SVG axis can.

**Still explicitly out of scope: tick-label text.** Rendering the actual
numbers/category names as geometry (`bpy.data.curves`-based font
objects) is a bigger, separate design question than the line segments
above -- don't add it as a side effect of some other task.

## Materials are queryable, split the same way modifiers already were

`obj.active_material` (the common single-material case) is exposed as a
synthetic `material` tag attribute in `scene_doc.py`'s `_new_tag()` --
`adapter.material_of(el)` reads it, mirroring `type_of`/`name_of`. That
alone makes `[material=Enemy_Red]` and `[material]` (exists) work through
soupsieve with **zero new parsing code**, same "let soupsieve do it"
principle as everything else in `query.py`.

`active_material` only sees one material, though, and a real object can
have several (`obj.material_slots`, each possibly empty). For "does this
object have material X *anywhere*," `:has-material(Name)` was added to
`SceneAdapter.pseudos`, checking membership across every slot -- the
exact same shape as the pre-existing `:has-modifier(TYPE)`. Follow that
split for future queryable-but-not-a-custom-prop Blender concepts: a
synthetic attribute for the "one canonical value" case, a `:has-*()`
pseudo for the "any of several" case.

`mock.py` mirrors bpy's real shape here too: `MockMaterialSlot.material`
can be `None` (an empty slot), and `active_material` is a genuinely
separate mock attribute, not derived from `material_slots` -- don't
"simplify" that by computing one from the other, since real bpy doesn't.

## `get_attr`/`set_attr` take a string OR a tuple path -- and reach into Geometry Nodes

`get_attr`/`set_attr` (and therefore `Selection.attr`) walk nested paths
generically (`getattr` → `.get()` → subscript at each segment), so
`'modifiers.Bevel.width'` already worked for the *read* side before this
existed -- `set_attr` didn't have the same path-walk at all, just a flat
`setattr`/subscript on `el` directly. Both now share the same walker.

**String vs. tuple is the same escape hatch as `select(adapter, el)` vs.
`select(adapter, f'#{el.name}')`.** A dot-joined string is convenient but
ambiguous the instant any name in the chain contains a literal `.` --
Blender auto-suffixes duplicate modifiers and node groups with `.001`
exactly like it does object names, so `'modifiers.Scatter.001.Size'`
silently mis-splits into 4 segments instead of 3 and resolves to nothing.
A tuple of segments (`('modifiers', 'Scatter.001', 'Size')`) never
splits, so it's always correct. Don't "fix" the string form with escaping
syntax -- that's exactly the hand-rolled-parser trap this codebase
already ripped out once (see the top of this file). The tuple form is
the answer, not a smarter splitter.

**Geometry Nodes inputs are the one thing plain attribute-walking
genuinely can't reach on its own**, because the human-readable name
("Size") isn't a real attribute or dict key on the modifier -- it only
exists in the node group's interface, which maps it to the actual
ID-property key (`"Input_2"`) that stores the value. `_gn_input_identifier()`
in `adapter.py` does that lookup, duck-typed against
`modifier.node_group.interface.items_tree` (the Blender 4.0+/5.x shape --
this project targets 5.3+, so there's deliberately no fallback to the
older `node_group.inputs` API). It's wired into `_resolve_one()` for
reads and `set_attr()`'s final-segment logic for writes, as one more
fallback after plain attribute/dict/subscript access fails -- so the
exact same path syntax reaches ordinary modifier properties and GN
inputs alike, no separate API. `adapter.gn_inputs(modifier)` lists
`{name: value}` for a modifier's inputs, for inspection.

**The identifier ("Input_2") isn't itself where the value lives, though
-- that storage shape changed in Blender 5.2.** Through 5.1, GN modifier
inputs were plain ID properties (`modifier["Input_2"] = value`); as of
5.2 that raises `TypeError: bpy_struct[key] = val: id properties not
supported for this type`, because the value moved onto a dedicated RNA
property group instead: `modifier.properties.inputs["Input_2"]` is a
wrapper exposing the real value through `.value` (`["value"]` one level
deeper for the vector-shaped sockets that report as a nested
`IDPropertyGroup` instead -- not yet modeled in `mock.py`, since nothing
exercises it). `_gn_input_get()`/`_gn_input_set()` in `adapter.py` are
that read/write pair, duck-typed the same way as `_gn_input_identifier`
(`hasattr(holder, 'value')`, no bpy import) -- this project targets
5.3+, so there's deliberately no fallback to the pre-5.2 direct-subscript
shape, same policy as `_gn_input_identifier` having no fallback to the
older `node_group.inputs` API. `mock.py`'s `MockModifier.properties.inputs`
(a dict of `MockGNInputValue`, which just holds `.value`) mirrors this
shape so tests exercise the real code path instead of the old
`modifier[identifier]` shortcut.

**Re-confirmed on Blender 5.4.0 Alpha (the full application, not the
wheel):** `modifier.properties.inputs[identifier]` is still an
`IDPropertyGroup` -- keys `value`/`type`/`attribute_name` for a field-
capable socket like float, just `value`/`type` for object/material
sockets (checked directly on both 5.4 and the 5.2 wheel; identical) -- and the path-walker's get/set round-trips through
`["value"]` for float, int, bool, vector, object and material sockets --
`tests/blender/test_modifiers_and_gn.py`'s per-socket-type test, run
in-app via `tests/blender/run_in_blender_app.py`. No code change was
needed; `_gn_input_get`/`_gn_input_set` already did the right thing.

`mock.py`'s `MockObject.modifiers` had to stop being a bare list and
become `MockModifierCollection` (name-addressable, like real bpy's
modifiers collection) for name-based path resolution to find a modifier
by name at all -- this was a latent gap, not something GN introduced.
`MockNodeGroup`/`MockNodeGroupInterface`/`MockNodeGroupInterfaceItem`
mirror the `items_tree` shape closely enough to test the lookup without
touching bpy.

**The `[key...]` bracket-selector syntax still can't express any of
this** for dotted-or-spaced names -- it's a single unescaped CSS string,
and GN inputs are frequently multi-word ("Instance Count"). That's a
selector-syntax limitation, not a path-walker one; `.filter(lambda el:
adapter.get_attr(el, (...)) > x)` is the answer there, and it isn't
worth solving by inventing string escaping.

## `point_attr`/`set_point_attr`/`points.point_data()` -- a different granularity, deliberately not Join-shaped

`get_attr`/`set_attr` read/write one property on one object. These read/
write one value *per vertex* on one object's mesh -- for data with too
many points to sensibly be one object each (see "Things that are
genuinely custom" below on why `Join` doesn't stretch to cover this).

**Position is `.vertices[i].co`, not `mesh.attributes['position']`,
on purpose.** Verified against real bpy 5.2: modern Blender's unified
attribute system genuinely does expose position as just another
POINT-domain entry (`mesh.attributes['position']`, `FLOAT_VECTOR`,
readable/writable through the exact same `foreach_get`/`foreach_set`
path as any custom attribute) -- one underlying mechanism, no special
case needed for correctness. `point_attr`/`set_point_attr` still special-
case `name == 'position'` to go through `.vertices`/`.co` directly
anyway, because that's the older, always-present, always-stable API;
the attributes-system view of position is confirmed equivalent but
younger, and there's no reason to depend on the newer one when the
established one already does the job.

**Custom point attributes are type-shaped, same duck-typing pattern as
the GN input fix above.** A POINT-domain attribute's value lives under
a field name that depends on `data_type` -- `FLOAT`/`INT`/`BOOLEAN` ->
`.value`, `FLOAT_VECTOR` -> `.vector`, `FLOAT_COLOR` -> `.color`
(verified against real bpy; table lives in `adapter.py`'s
`_POINT_ATTR_SHAPE`). `set_point_attr` infers which type to create from
the Python shape of your first value (`_infer_point_attr_type`) --
bool before int matters there, since `bool` is an `int` subclass.
`mesh.attributes[name]` returning a *different* (but same-name) Python
wrapper object on every access is a real, confirmed bpy quirk -- don't
cache an attribute reference across calls, re-fetch by name.

**`LiveBlenderAdapter` overrides both methods for bulk `foreach_get`/
`foreach_set` access, and this one is a real performance override, not
just the class-boilerplate kind the other overrides in
`blender_adapter.py` are.** `SceneAdapter`'s base version is a plain
per-item Python loop -- correct, mock-testable, and *measured* about
100x slower than `foreach_get`/`foreach_set` at a few thousand points
(python-loop 0.0117s vs. foreach_set 0.0001s for n=5000, see
`tests/blender/test_point_attrs.py`). That gap matters here more than
anywhere else in this file: the entire reason to reach for vertices
over objects is scale, so shipping only the naive loop would quietly
defeat the feature's own purpose. `_check_point_count()` (the never-
resize length check) is factored out in `adapter.py` so both versions
raise the identical error, since the two paths must never silently
diverge in behavior, only in speed.

**`set_point_attr`/`point_data()` never resize a mesh to fit new data,
by design, not as a v1 gap to fill in later.** A length mismatch is
always a `ValueError`. `mesh.clear_geometry()` + `mesh.from_pydata()`
is a real, clean way to resize a mesh (confirmed against real bpy) if
you ever want that -- it just also wipes every custom point attribute,
which then need recreating -- but `point_data`/`set_point_attr`
deliberately don't do this automatically. Resizing was considered and
explicitly rejected for the motivating use cases (a deforming sphere,
attributes changing over time -- both fixed vertex count, only values
change), not merely deferred for lack of time.

**`points.point_data()` is deliberately not `Join` with vertices instead
of objects.** `Join` needs a stamped identity (`d3_key`) because objects
can be individually added/removed and a rerun needs to recognize "this
object still represents the same thing." Vertices have no such identity
to begin with -- there's no cheap way to say "this vertex is still the
same conceptual point" across a topology change without real geometry
surgery (`bmesh`), which this deliberately doesn't take on. So
`point_data()` binds by *index* (`data[i]` -> vertex `i`), full stop --
no key function, no enter/update/exit. If per-entity continuity across
a changing dataset matters, that's what object-based `Selection`/`Join`
is for; `point_data` trades identity for the scale vertices give you
over one object per point.

**No keyframing inside `point_data()`, and that's a hard technical wall,
not a style choice.** Verified against real bpy: `mesh.vertices[i].co`
*can* be keyframed like `obj.location` can (confirmed real interpolation
across frames) -- but it costs 3 F-curves per vertex, and at 2000
vertices that's 6000 F-curves for a *single* keyframe pass (~0.23s
measured, and that cost repeats every frame you bake). Named point
attributes can't be keyframed through bpy's RNA system *at all*
(`item.keyframe_insert('value', ...)` raises `could not make path`,
confirmed). So "changing over time" for point data can only mean
recompute-and-overwrite, never baked animation data -- confirmed cheap
and clean at real scale (2000 vertices × 240 frames, pure recompute, no
keyframes: 0.33s total, and `mesh.animation_data` stays `None`
throughout). `point_data(adapter, el, frame, **channels)` reflects this
directly: each channel is a plain `fn(frame) -> values` called fresh
every time, no interpolation or state of its own -- if a channel needs
continuity across calls (easing between explicit states, a lookup
table), that lives in the closure you pass in, not in `point_data`
itself.

**Live-scrub wiring exists: `blender_adapter.live_point_data(adapter, el,
**channels)`.** Originally scoped out pending someone actually trying
the explicit-loop driver against real scrubbing first (see the demos in
`examples/`) -- that happened, and an explicit bake loop turned out to
be a real surprise: it computes all frames instantly at script-run time
and only the *last* one survives (no keyframes are ever written), so
pressing Play afterward does nothing at all -- confirmed by scrubbing
after running the loop and finding the mesh frozen. `live_point_data()`
wraps `points.point_data()` in a `bpy.app.handlers.frame_change_pre`
registration instead: applies once immediately (so the first view
already reflects the formula, not the raw rest shape -- the handler
only fires on an actual frame *change*), then again on every frame
change. It lives in `blender_adapter.py` alone (needs `bpy.app`), and
`points.point_data()` itself is untouched -- `live_point_data()` is a
thin wrapper around it, not a fork.

The one piece of real complexity flagged before building this was
handler *lifecycle*, not the mechanism -- `bpy.app.handlers.frame_change_pre`
is a plain global list that outlives a single script run, so a naive
"register a handler" helper would pile up a duplicate (holding an
increasingly stale closure) every time you rerun your setup script,
exactly the rerun-unsafety this library is otherwise careful about (see
`Join`'s `d3_key` stamping). `live_point_data()` handles it by tagging
each handler with the target object's name and scanning-and-replacing
on re-registration, so calling it again for the same object swaps the
whole channel set rather than stacking a second handler -- confirmed:
re-binding the same object leaves the handler count unchanged, not
incremented. `stop()` (the return value) removes the binding; call it
before deleting an object you've live-bound, so its handler doesn't
outlive it holding a now-invalid reference. `tests/blender/conftest.py`'s
autouse fixture also clears `bpy.app.handlers.frame_change_pre` as a
backstop, since `read_factory_settings()` (which resets `bpy.data`
between tests) doesn't touch `bpy.app.handlers` at all -- a test that
raised before its own `finally: stop()` would otherwise leave a stale
handler to blow up a *later* test's `frame_set()`, not its own.

**What's verified vs. not, precisely:** confirmed against real bpy that
`scene.frame_set()` reliably triggers the handler, headless, correctly,
repeatedly. **Not** separately verified: real interactive Play/scrubbing
in an actual windowed Blender session firing the handler the same way --
that's a related but distinct claim from "`frame_set()` triggers it,"
and headless `bpy` has no window to check it against (same category as
every other "verified headless, not the full application" caveat in
this file).

**Mesh test-data shape:** `mock.py`'s `MockMesh`/`MockAttributeCollection`/
`MockPointAttribute`/`MockPointAttributeItem`/`MockVertex` mirror the
real shapes above closely enough to exercise the same adapter code
against both -- same "mock mirrors verified real shape" pattern as
`MockGNInputValue`. `MockObject.data` (a `MockMesh` or `None`) is new;
`mock.spawn_points()` is the point-based sibling of `spawn()`.

## `examples/geometry_nodes_countries.py` -- real third-party libraries, verify before trusting

This example treats `databpy` (object/collection creation, attribute
storage) and `nodebpy` (building Geometry Nodes trees from Python) as
peer, top-level libraries d3blender composes with -- neither is a
dependency of d3blender itself, and d3blender doesn't wrap either of
them; it just selects/mutates whatever real `bpy` objects they produce
(same "object creation is left to the caller" boundary as `mock.spawn()`
and the collection/tick-mesh exceptions to it, see above).

If you're asked to extend this example or add another one like it:
**don't trust remembered API shapes for these two libraries -- verify
against their actual source first.** Both are real (same author, Brady
Johnston), both are under active, versioned development, and a
doc-summary tool got one thing outright wrong during research for this
file (`BlenderObject.obj` doesn't exist; the real attribute is
`.object`) -- caught only by cloning the repos and reading source
directly instead of trusting a fetched summary. `nodebpy` specifically
versions its node-class definitions **per Blender release** (its latest
tag at the time this was written, `v520.8.0`, targets Blender 5.2.x
specifically, with no 5.3-targeted release yet) -- a node's socket names
or defaults can change between Blender versions, so pin/verify the
`nodebpy` version against whatever Blender version is actually running
before assuming a node signature still matches what's used here.

This example has no pytest coverage and can't get any -- it needs a
real Blender application plus both packages installed, unlike
`scatter_plot_3d_blender.py`/`bar_chart_blender.py` (plain `bpy`, no
add-on packages), which the headless `bpy` module can and does exercise
(see Testing status below). This one's written against verified,
current, real APIs, not guessed ones, but that's still not the same
claim as "run and confirmed working."

## Things that are genuinely custom (no library does this)

- The axis/combinator split and the numeric-attribute/pseudo-class
  stripping in `query.py` -- CSS has no numeric comparison operators and
  no way to know about Blender-specific predicates like
  `:has-modifier(BEVEL)`.
- The join/reconciliation pattern in `selection.py` -- rerun-safe scene
  construction via a stamped `d3_key` custom property. This is the actual
  value-add of the library; treat it carefully.
- `.keyframe()` -- deliberately does *not* try to fake tweening. It sets
  values and calls the real `keyframe_insert`; Blender's F-curves do
  interpolation. Don't add an interpolation/easing layer here -- if
  someone wants easing, that's an F-curve interpolation mode on the
  Blender side, not something to build in Python.
  **Custom properties need the ID-property data path.** Real
  `obj.keyframe_insert('hp')` raises `TypeError: ... property "hp" not
  found` for a custom prop, on both the 5.2 wheel and Blender 5.4;
  `'["hp"]'` works. So `SceneAdapter.keyframe_insert` retries with
  `_id_prop_path(key)` on that `TypeError`, but only when `el.get(key)`
  has the key (duck-typed, no bpy import, inherited by
  `LiveBlenderAdapter`). Everything else re-raises bpy's own error.
  `MockObject.keyframe_insert` is now just as strict (it raises for a
  bare custom-prop name and accepts `'["key"]'`), so the mock suite goes
  through the same retry. It used to read `getattr(self, data_path)` and
  simply couldn't keyframe a custom prop at all. Still not handled:
  nested/tuple paths (`'modifiers.Bevel.width'`) aren't translated into
  RNA data paths (`'modifiers["Bevel"].width'`), so `.keyframe()` on
  those fails in real bpy. Translating would mean resolving each segment
  the way the path-walker does, including GN input names that have no
  RNA path at all; that's a separate design question, so it wasn't done
  as a drive-by.

## `Selection.datum` -- closing the `(el, i)` vs. real d3's `(d, i)` gap

Real d3 accessor functions (`.attr("cx", d => ...)`) receive the bound
datum directly, because a d3 selection attaches `__data__` to each DOM
node permanently once joined -- rebinding replaces it, but it's never
just lost. `d3blender`'s `Selection` used to only track `.elements`,
so every accessor was `(el, i)`, and getting at the datum meant closing
over the original data array and re-indexing by `i` by hand (see the
git history of `examples/nested_uv_sphere_deformation_chained_blender.py`
for exactly what that looked like before this existed) -- a real gap,
not a style choice, since not every adapter's elements can hold
arbitrary Python attributes the way a DOM node can (a real bpy ID
mostly can't), so d3blender can't just attach data to the element
itself the way d3 does.

**The fix: `Selection.datum`, a list parallel to `.elements`.**
`Join.join()` populates it (each entered/updated element's own item
from `items`, in the same order `.elements` is built in -- rerunning
`.data(newItems).join(...)` rebinds it to the new items, never stale
ones). `.filter()` propagates it correctly for survivors, since
filtering only ever whittles down the *same* elements (a trivial 1:1
mapping). `.select()` (scoped descendant queries) is the one exception,
and deliberately so: it returns *unbound* data (`.datum` full of
`None`), because there's no 1:1 parent-datum-to-child mapping to fall
back on -- one element can have many matching descendants, and picking
one interpretation over another would be guessing. Don't try to invent
one if asked to "fix" that; it was considered and rejected, not missed.
A plain `select()` query (never joined at all) is unbound the same way.

**Every callable-accepting method (`.attr()`, `.each()`, `.keyframe()`,
`.filter()`) dispatches through one shared helper, `_invoke()`, based on
`_arity()` (parameter count via `inspect.signature`).** `fn(el)`,
`fn(el, i)`, and `fn(el, d, i)` are all valid, chosen automatically --
this is what makes the change non-breaking: every script written before
`Selection.datum` existed, using `(el, i)`, keeps working exactly as
before, since `_arity` still routes it to the 2-arg call. Don't
"simplify" this into always passing `(el, d, i)` -- that would force
every existing script and test using the 2-arg shape to be rewritten,
for no behavioral gain, and directly contradicts why this was built
incrementally in the first place (see the conversation that led here:
the ask was explicitly "update a *few* of the scripts," not migrate
everything). A `*args` callable (`lambda *a`, `def f(el, *rest)`, a
generic decorator/wrapper) counts as arity 3 and gets the full
`(el, d, i)`. It used to be counted by plain parameter number, so
`lambda *a` got only `fn(el)`. This is a real (small) behaviour change
for `*args` callables only: `def f(el, *rest)` used to receive
`(el, i)` and now receives `(el, d, i)`. Callables without `*args` are
unaffected.
`**kwargs` and keyword-only parameters still count toward the plain
total (pre-existing behaviour, left alone).

`.keyframe()`'s `frame` argument goes through the same `_invoke()`
dispatch when it's callable (evaluated once per element, before that
element's attrs), so data whose rows each carry their own time can
keyframe every element at its own frame in one call. Added after the
first real adoption had to fall back to raw `obj.keyframe_insert()`
loops for exactly that. A plain number still means "every element at
this frame," unchanged.

`points.py`/`point_attr`/`point_data`/`live_point_data` are explicitly
**not** part of this -- those stay whole-array-only, no per-vertex
callable dispatch, by deliberate choice (see their own section above).
This datum-binding change is scoped entirely to `Selection`/`Join`
(object-level), not vertex-level data.

## `Join.join()`'s shape-name shorthand -- real d3's `join("circle")`, and where it genuinely can't match

Real d3's `selection.join("circle")` is sugar for `join(enter =>
enter.append("circle"))` -- trivial to implement generically, because
the DOM has exactly one universal "create an element of this type"
primitive (`document.createElement`) that works for any tag name.
Blender's object creation has no such uniformity: a sphere, a cube, a
camera, and a databpy-created object are all built through entirely
different APIs, with different parameters and different result shapes.
So `Join.join()`'s string form (`enter` as a shape name) doesn't invent
a generic creator -- it dispatches to `self.adapter.creator(name,
collection, **create_kwargs)`, and the *adapter* owns what's actually
possible: `SceneAdapter.creator()` (the base/mock) always raises
clearly, since there's no `bpy.ops` equivalent to fall back on and this
deliberately doesn't grow a hand-rolled geometry generator to fake one
(see the geometry_nodes_countries.py section above and the earlier "no
primitive-mesh functions" discussion -- same reasoning, same
boundary). `LiveBlenderAdapter.creator()` is the real implementation, a
small dispatch table (`_PRIMITIVE_OPS` in `blender_adapter.py`) mapping
a handful of names to the corresponding real `bpy.ops.mesh.primitive_*_add`
call plus the "read `bpy.context.active_object`, unlink from wherever it
landed, link into `collection`" boilerplate every example's own
`spawn_X()` helper was duplicating identically.

**`collection` is a required argument, not defaulted to Blender's
ambient `bpy.context.collection`, and that was a deliberate call, not
an oversight.** Real d3 doesn't need an explicit parent because DOM
structure supplies it implicitly (the new element is appended as a
child of the selection's own parent node). d3blender has no equivalent
"current parent" concept. The tempting shortcut -- default to whatever
`bpy.context.collection` currently is, mirroring how the operators
themselves behave when called with no explicit collection -- was
checked and rejected: that ambient default is Blender's own Scene
Collection unless a script has specifically pointed the active layer
collection elsewhere first, and this project already knows (see
"Testing status" above) that an object linked only into the scene root
is invisible to `select()`. A convenience whose default silently
produces invisible objects would be strictly worse than the boilerplate
it replaces, so it still never defaults to the ambient collection.
**Update:** d3blender now *does* have a "current parent" concept --
`select_all(collection)` records the collection as `Selection.parent`
(see the ergonomics section below) -- and `join('shape')` defaults
`collection` to that. That's the d3 behaviour the paragraph above says
was missing, and it doesn't reopen the ambient-default trap: the parent
is a collection the caller explicitly selected from, not whatever
happens to be active. With no parent, `collection=` is still required.

**Shape parameters only exist as creation-time arguments, verified, not
assumed.** Checked directly against real bpy: a UV sphere created with
`segments=8` has no `segments` attribute on the object or the mesh, and
setting `obj['segments'] = 32` afterward (a custom property, the only
other avenue) changes nothing about the actual vertex count. There is
no live property to reshape after the fact -- this is a real wall in
bpy's own object model, not a d3blender gap to close later. That's why
`create_kwargs` (radius, segments, ring_count, ...) live on the `.join()`
call itself, evaluated per-datum if given as `fn(d) -> value`, rather
than being something you'd expect to set via `.attr()` afterward the
way you would `cx`/`r` on a d3 circle. Genuinely mutable properties
(name, location, scale, custom props) are unaffected by any of this and
stay ordinary `.attr()` calls post-join, same as always --
`.attr('scale', lambda el, d, i: (d['radius'],) * 3)` is the correct,
cheap, real way to vary a created primitive's *apparent* size per
datum without needing a per-datum creation kwarg at all.

`_PRIMITIVE_OPS` is deliberately just the standard `bpy.ops.mesh`
primitives Blender itself ships as one-call operators -- adding an
entry should always mean "another real `bpy.ops.mesh.primitive_*_add`
exists," never "and here's our own vertex math for a shape Blender
doesn't have a built-in operator for." That second thing is exactly the
"no primitive-mesh functions" boundary this project has already drawn
once; don't cross it here either.

## `Selection.classed()` and material shader inputs -- one real addition, one already-there capability

Two different questions, evaluated together, with two different
answers -- worth keeping straight since they look similar (both are
"what about d3's other selection methods") but landed differently.

**`.classed()` is a real, small, new method.** d3's `d3_class` custom
property (space-separated, read by `classes_of()`) already powers
`.foo`-style selectors -- it existed before this, from day one of the
selector grammar. What didn't exist was an ergonomic way to *toggle*
one class without hand-splitting the string, mutating a set, and
rejoining it yourself every time. `Selection.classed(names, value=None)`
closes that gap: same getter/setter shape as `.attr()`, same
`(el)`/`(el, i)`/`(el, d, i)` dispatch via `_invoke()`, space-separated
multi-class support matching real d3's own `.classed('foo bar', true)`.
No new adapter capability was needed -- it's built entirely on
`classes_of()` and `set_attr('d3_class', ...)`, both pre-existing.

**Material shader inputs needed zero new code at all, confirmed
directly.** `get_attr`/`set_attr`'s existing generic path-walker
already reaches into a material's node tree --
`('active_material', 'node_tree', 'nodes', 'Principled BSDF', 'inputs',
'IOR', 'default_value')` read and wrote correctly against real bpy with
no changes to `adapter.py` at all. This is the same story as
`modifiers.Bevel.width` working before any GN-specific handling
existed -- plain attribute/subscript access already gets you most of
the way into any bpy object graph; special-casing (like `_gn_input_get`)
is only needed where the human-readable name and the actual storage key
genuinely diverge, which isn't true here. So there's no `adapter.shader_input()`
or similar to build -- the actual gap was that this pattern wasn't
written down anywhere, the same kind of "capability exists, isn't
discoverable" gap that prompted documenting Geometry Nodes access
explicitly.

Two things confirmed while verifying this, both now in the README, both
worth remembering if asked to extend this further:

- **Node names auto-suffix exactly like objects/modifiers/GN node
  groups** (`Principled BSDF` -> `Principled BSDF.001` for a second
  one, confirmed) -- the identical tuple-vs-dotted-string reasoning
  applies, nothing new to design here, just another instance of an
  already-documented rule.
- **`default_value` on an already-linked socket sets successfully and
  silently does nothing** -- confirmed: the value stores, `is_linked`
  stays `True`, and the link keeps controlling the actual shading. This
  is bpy's own behavior, not something `set_attr` could detect or warn
  about generically without adding real complexity for a narrow case;
  documented as a gotcha rather than "fixed."
- **Socket names are version-sensitive** -- confirmed via the fresh
  Principled BSDF's actual input list on this Blender version; don't
  assume a socket name from memory (`Specular` became `Specular IOR
  Level` around Blender 4.0, per Blender's own release notes) -- read
  `material.node_tree.nodes[name].inputs` directly if extending an
  example or writing new code against a shader input.

`examples/material_shader_params_blender.py` is the worked example --
one material per object (materials are shared datablocks by default;
changing one shared material's input would change every object using
it, so the example creates a fresh material per sphere deliberately,
not as an oversight to fix later).

## Driving a material you didn't build: drivers, not path-walking -- and a real, non-obvious gotcha

Path-walking (above) is the right tool for a material whose structure
you actually know. It's the wrong tool for a complicated asset material
-- you'd be hardcoding a path through node names you don't control,
several groups deep, exactly the kind of fragile coupling this project
avoids elsewhere. Blender's own driver system is the better answer, and
it composes with d3blender for free: wire a driver, once, from
whatever deeply-nested socket needs exposing to a plain custom object
property (`socket.driver_add('default_value')`, a `SINGLE_PROP`
variable targeting `object["prop_name"]`), and every future update only
ever touches that property -- `.attr('prop_name', ...)` reaches it
exactly like any other custom prop, no new d3blender code, no
adapter change, nothing. See
`examples/material_shader_params_driven_blender.py`.

**Two things confirmed while building that example, one of them a real
trap that took two rounds of testing to pin down precisely:**

- **`driver.type = 'AVERAGE'`, not `'SCRIPTED'`.** A single-variable
  average is a clean passthrough for the "one property drives one
  input" case this needs, and unlike `'SCRIPTED'` (an arbitrary Python
  expression string), it doesn't depend on Blender's "Auto Run Python
  Scripts" preference being enabled -- a `'SCRIPTED'` driver is
  silently disabled without it. Don't reach for `'SCRIPTED'` here by
  habit; `'AVERAGE'` is the deliberate, more portable choice.
- **Changing the driving custom property does not propagate to the
  driven value on its own in headless scripting -- and the failure mode
  is sneaky.** First pass: added `bpy.context.view_layer.update()`
  after the change, tested once, saw the correct value, assumed it was
  fixed (same pattern that worked for the GN modifier segment-count
  case). Second pass, testing *multiple consecutive* changes to the
  same property: only the *first* change after the driver's creation
  actually showed up: `view_layer.update()` alone did nothing for the
  second, third, or any later change. The fix, confirmed across four
  consecutive changes: `el.update_tag()` immediately before
  `view_layer.update()`, called again on *every* change, not just once.
  This is the exact same two-call pattern the GN case needed
  (`update_tag()` + `view_layer.update()`) -- the reason it's flagged
  as its own gotcha here, not just "see the GN section," is that the
  failure is specifically the kind that hides on a single-check test:
  the first change looking right is not evidence the mechanism is
  correct, only that it happened to also be the one case that doesn't
  need the fix. If asked to verify a similar update-propagation claim
  in the future, check at least two consecutive changes, not one.

**Separately confirmed while investigating this: unlike per-vertex
attributes, a shader node's `default_value` genuinely can be keyframed**
(`socket.keyframe_insert('default_value', frame=N)`), with correct
F-curve interpolation on `scene.frame_set()` -- no `update_tag()`
needed for this path specifically, *as long as the material is actually
assigned to an object linked into the scene* (an orphan/unused material
isn't part of the depsgraph and its animation won't evaluate). So
`Selection.keyframe()` already works for material inputs today, no
changes needed -- baked, scrubbable animation of a shader parameter and
a live driver from a custom property are both real, both already
available, and which one to reach for depends on whether you want
"recorded keyframes" or "always follows this other value."

## Cameras and compositor nodes -- a third and fourth confirmation of the same pattern

Grew out of comparing d3's real module list (d3-selection, d3-scale,
d3-shape, d3-hierarchy, d3-force, d3-geo, d3-transition -- checked
against current tutorials/the official getting-started page and the D3
Graph Gallery, not just memory) against what's here. Two more places
turned out to already work with zero new code, the same story as
Geometry Nodes inputs and material shader inputs before them:

- **Cameras** are ordinary objects -- `select(adapter, 'camera')`
  already works, `.attr()` already reaches `.location`, and camera-
  specific settings (`lens`, `clip_end`, `dof.focus_distance`) are one
  path-walk deeper on `.data`, confirmed. The first attempt at
  verifying this returned an empty selection -- not a camera-specific
  bug, just the already-documented scene-root-collection gotcha
  (linked the test camera into `bpy.context.scene.collection` instead
  of a real tracked collection); relinking it into one fixed it
  immediately. Worth remembering as a reminder that an unexpected empty
  `select()` result anywhere should make you check that gotcha first,
  not assume a new bug.
- **Compositor nodes** are a third node-tree domain, reachable the
  same generic way -- but getting there took three failed attempts
  using remembered API shapes that turned out to be stale, which is
  worth recording precisely since it's a clean illustration of why this
  project insists on checking bpy directly instead of trusting memory
  for anything version-sensitive:
  1. `scene.node_tree` -- doesn't exist in this version. The compositor
     moved to a real node-group datablock, `scene.compositing_node_group`,
     the same modernization materials and GN already went through.
  2. `scene.use_nodes = True` does **not** auto-create that node group
     the way it does a material's default Principled BSDF setup -- you
     create the `CompositorNodeTree` and assign it yourself.
  3. `CompositorNodeGlare.threshold` -- not a real property in this
     version either. What used to be (in older Blender) a plain
     `bpy_struct` float is now `inputs['Threshold'].default_value`, a
     socket, matching the same generalization materials underwent.
  Once the *current* shape was used, `get_attr`/`set_attr` reached it
  immediately, no adapter changes.
  4. **And again in 5.4** (checked on 5.4.0 Alpha): compositing became
     a list of effects, `scene.compositor_effects` (`new(name)`/`remove`/
     `clear`/`.active`). Each `SceneCompositorEffect` has its own
     `node_group`, `enable_for_render`/`enable_for_preview`/`is_active`/
     `properties`. `scene.compositing_node_group` and `scene.use_nodes`
     still exist but emit `DeprecationWarning` (removal expected in 6.0);
     `compositing_node_group` is a shim for the active effect's group.
     Still no adapter change: `('compositor_effects', 'FX', 'node_group',
     'nodes', 'Glare', ...)` resolves because the effect-name segment
     falls through to the collection's `.get('FX')` (plain `getattr`
     misses it, confirmed). The tests and README use `compositor_effects`
     where the scene has it and the 5.2 properties otherwise. 5.3 hasn't
     been checked. One trap from writing the version gate:
     `hasattr(bpy.types.Scene, 'compositor_effects')` is `False` even on
     5.4, because RNA properties aren't class attributes. That silently
     skipped the 5.4-only test in the first in-app run. Check the
     instance, or `bpy.types.Scene.bl_rna.properties`. `scene` isn't reached through
  `select()` -- there's normally exactly one current scene, so
  `bpy.context.scene` handed directly to `get_attr`/`set_attr` (the
  same "I already have the element" pattern `select(adapter, el)`
  exists for) is the right shape, not a new selector concept.

Both are documented in README (a "Cameras" and a "Compositor nodes"
section, mirroring "Material shader inputs") and covered by real-bpy
tests (`tests/blender/test_camera_and_compositor.py`) that pin down the
*current* API shape as a regression check -- if Blender changes this
again, the test breaking is the signal, not a stale assumption
quietly staying wrong.

## `scale_time`/`scale_sequential`/`interpolate_rgb`, and `shape.line()`

Grew out of the same d3-module comparison. Small, deliberately scoped
additions, all pure Python (no bpy), same "tiny, mirrors the d3
concept, nothing more" philosophy as the existing scales/`axis.py`.

- **`scale_time`** is `scale_linear` with a date-aware domain
  conversion (`_timestamp()`) bolted on -- naive datetimes are treated
  as local time (matching Python's own `datetime.timestamp()`
  behavior), which is a real, stated simplification, not a bug: correct
  for "which day is this" charting, not guaranteed correct mixing
  timezones. `.invert()` returns an actual `datetime`, not a raw
  number, so it's a genuine inverse of what the forward scale accepts
  -- don't "simplify" that back to a number under the assumption
  nothing depends on it round-tripping cleanly.
- **`scale_sequential` clamps by default; real d3's doesn't unless you
  call `.clamp(true)`.** Deliberate deviation, not an oversight: an
  interpolator built for exactly `t` in `[0, 1]` (which `interpolate_rgb`
  is, and which is the overwhelmingly common case -- a color gradient)
  will produce out-of-range channel values for unclamped out-of-domain
  input, which is a worse default than d3's own for this project's
  actual use case. If a future need for unclamped extrapolation shows
  up, add a `clamp=True` parameter rather than flipping the default.
- **`interpolate_rgb` lives in `scale.py`, not its own module.** Real
  d3 splits this into a separate `d3-interpolate` package because it
  has dozens of interpolators (color spaces, strings, arrays, objects,
  numbers). This project has exactly one, and `scale_sequential` is its
  only real consumer -- a whole new module for one four-line function
  would be over-structuring; add a `d3blender/interpolate.py` if a
  second genuinely distinct interpolator shows up later, not before.
- **`shape.line()` is scoped to exactly what `create_line_mesh()` needs
  -- one function, not a `d3-shape` port.** `d3.line()`'s actual job
  isn't "generate a primitive" (the boundary this project has already
  drawn twice, for mesh primitives and for reimplementing GN node
  construction) -- it's connecting a data-derived array of points into
  a path, which is a fundamentally different thing: the points already
  came from the caller's own data or formula. `closed=True` mirrors
  d3's `curveLinearClosed`. Deliberately not implemented here: `d3.area()`
  (a filled ribbon between two point arrays, which would need real face
  generation, not just edges -- a materially bigger lift than
  connecting points) and any curve interpolation beyond straight
  segments (d3's `curveBasis`/`curveCardinal`/etc. -- smooth curve
  fitting is its own real piece of math, not a small addition to
  `line()`). Add those as their own functions if genuinely needed, not
  as options bolted onto `line()`.

## The ergonomics pass: adapter-less select, select_all, scale chaining, csv, transitions

A user-requested pass to make scripts read like d3. **Hard constraint:
existing callers must keep working unchanged.** Three real ones exist in
`~/.config/blender/blender-config/scripts/startup` (the halo importer,
`country_wireframes._reconcile_geo_markers`, `gpx_import._reconcile`),
all shaped `select(get_adapter(), list(coll.objects)).data(items,
key=lambda i, d: ...).join(enter, exit=...)` then `.elements`/`.datum`,
plus `scale_linear(domain, range_)`. `tests/test_ergonomics.py::
test_existing_callers_call_shape_still_works` pins that shape, and the
gpx/country helpers themselves were called headlessly in Blender 5.4
with synthetic items after this change (same objects on rerun, removals
correct). Don't break that test to make something prettier.

- **`select(target)` without an adapter** gets `default_adapter()`: a
  *fresh* `get_adapter()` per call (or whatever `set_default_adapter()`
  installed -- an adapter or a factory; that's how the mock suite tests
  this path). Fresh on purpose, per the "get_adapter() snapshots" rule;
  caching one would bring the stale-index bug back. The selection keeps
  its adapter for the whole chain. `select()`'s signature became
  `select(*args, adapter=None, target=...)` so both the one- and
  two-positional forms and the old `select(adapter=..., target=...)`
  keyword form all work. `query.py` imports `blender_adapter` lazily
  inside `default_adapter()`, so `blender_adapter.py` is still the only
  file that imports `bpy`, and the package still imports without it.
  Outside Blender with no default set, the error says to pass an adapter.
- **`select(collection)` was deliberately NOT changed** to mean "its
  objects". It already means "wrap this collection as the element"
  (d3.select(node)), and changing it would silently change existing
  code. `select_all(collection)` is the new spelling, mirroring d3's
  `parent.selectAll()`: its direct objects, with `Selection.parent` set.
  `filter()` keeps the parent; scoped `.select()` doesn't.
- **`join()` uses the parent** as the default `collection=` for the
  shape-name form, and links a callable `enter`'s result into it **only
  if the element isn't in any collection yet**. Existing callers' enter
  functions link objects themselves and their selections have no parent,
  so nothing changes for them. An element `enter` placed elsewhere is
  never moved.
- **Several joined groups in one collection need `select_all(coll,
  '.group')`**, the analogue of d3's `selectAll('rect.bar')`. Without
  the narrowing selector, group A's join sees group B's `d3_key`-stamped
  objects and removes them as exits. Unkeyed objects (an axis mesh, hand-
  added objects) are never touched by a join, which was already true.
- **`.data(key=...)`** also takes a field name or a 1-arg `fn(d)`. The
  2-arg form stays `fn(i, d)`, index first (the reverse of d3); it can't
  be flipped without breaking every existing caller.
- **Join result:** it was already the merged enter+update selection in
  data order, so chaining after `.join()` already hit both (verified,
  now documented and tested). New: `.entered` / `.updated` sub-
  selections on the result.
- **Pushed back on `join(enter=fn(selection), update=fn(selection))`**
  (d3 v7 sub-selection callables). `enter` is already a per-datum
  `fn(d)`, and a selection-taking `fn(sel)` has the same arity, so the
  two can't be told apart; adding it would need a flag or a different
  method, which buys little over `.entered`/`.updated`. Not built.
- **Transitions** (`Selection.transition()` -> `Transition`) are built
  on `adapter.keyframe_insert()`: current value at `start+delay`, target
  at `start+delay+duration`, `start` default `adapter.current_frame()`
  (new adapter method: a settable attribute on the mock, the scene frame
  live). Chained `.transition()` starts at each element's previous end.
  No easing layer, consistent with the `.keyframe()` rule above: that's
  F-curve interpolation in Blender. If there's no current value (a custom
  prop that doesn't exist yet), only the end key is written.
- **Scales became small classes** with `__call__`, keeping every old
  construction signature and attribute: `scale_band(...).step` is still
  a number (d3 makes it a method), `scale_ordinal` with an explicit
  domain still maps unknowns to `range_[0]`, `scale_band` still raises
  `KeyError` for unknowns, `scale_sequential` still clamps by default.
  New: chaining getters/setters, `nice()`/`ticks()` (d3-array's
  1/2/5 x 10^k algorithm, `scale.ticks()` is the module function),
  `clamp()`, `copy()`, tuple ranges interpolated per component, and the
  implicit ordinal domain when no domain is given. `scale_time` has no
  `ticks()`/`nice()`: d3's calendar ticks are a different algorithm and
  numeric ticks on timestamps would be wrong-looking, so it's absent
  rather than misleading. `axis.ticks()` (fixed-width) was left as is;
  `scale.ticks()` is the nice one.
- **`fetch.py`** (`csv`/`tsv`/`dsv`/`json`/`auto_type`): typed by
  default because d3 code almost always passes `d3.autoType`. Ints vs.
  floats are kept apart (d3 has one number type); dates become
  `datetime.date`/`datetime`. Stdlib only, no bpy, so `//` paths are the
  caller's job. Not in `__all__` so a star-import can't shadow the
  stdlib `csv`/`json` modules.
- **`examples/script_runner/`** follows the Script Runner extension's
  contract (`PARAMS` + `execute(context, params)`, `_`-prefixed files
  skipped, `.py` only). Each script duplicates two tiny helpers (CSV-path
  and collection fallback) instead of sharing a `_common.py`: the runner
  doesn't put the folder on `sys.path`, and self-contained files are
  easier to copy. `csv_to_points.py` resizes the mesh itself when the
  row count changes (`clear_geometry()` + `from_pydata()`), which keeps
  d3blender's own never-resize rule intact. `tests/blender/
  test_script_runner_examples.py` runs all three through `execute()`
  with reruns and setting changes, on the wheel and in-app on 5.4.

## Known gotchas (see README for the full list)

- **Bare word = type, `#name` = a specific instance.** `Weapons > mesh`
  parses fine and matches nothing, because `Weapons` is read as a type
  name. This has bitten every draft of the test suite and examples at
  least once. If a query mysteriously returns `[]`, check this first.
- Numeric/pseudo predicates only apply to the *rightmost* compound in a
  selector, not to ancestors in a combinator chain. This is a stated v1
  scope limitation, not a bug -- don't "fix" it without discussing,
  since it'd require restructuring how predicates attach to the compiled
  query.
- `Selection.select()` (scoped queries) re-runs the full-scene query and
  intersects with a precomputed descendant set, rather than building a
  doc scoped to just that subtree. Correct, but not the most efficient
  approach for very large scenes -- fine for now.

## Testing status -- read before claiming something works

- Everything in `src/d3blender/` except `blender_adapter.py` is tested
  and passing against `d3blender.mock` (a fake scene shaped like
  `bpy.data`, no Blender required). `pytest` runs in well under a second.
- `blender_adapter.py` **is now also tested against real `bpy`**, in
  `tests/blender/` -- see that directory's README.md for setup (short
  version: PyPI's headless `bpy` module, a separate Python 3.13 venv,
  `pytest tests/blender`). A plain `pytest`/`pytest tests/` from the main
  dev venv skips this directory cleanly (`pytest.importorskip` in its
  conftest.py) rather than failing, so it's opt-in, not a tax on the fast
  path. This closed the gap that let the Blender 5.2+ Geometry Nodes
  storage-shape break (see the section above) ship unnoticed -- the mock
  had no way to know the real shape had changed.
- `examples/bar_chart_blender.py` and `examples/scatter_plot_3d_blender.py`
  have both now actually been run (not just written) against the headless
  `bpy` module, via `.venv-blender/bin/python examples/whichever.py`, and
  their output matches their mock-based counterparts exactly (`.venv-blender`
  is `tests/blender/`'s venv -- see that directory's README.md -- reused
  here since it already has a real `bpy` importable). Still **not**
  covered by anything runnable here: `examples/geometry_nodes_countries.py`,
  which additionally needs `databpy`/`nodebpy` installed -- neither is a
  dependency of `d3blender` itself (see that example's own section below),
  and the headless `bpy` module isn't a substitute for the full Blender
  application those two libraries assume.
- The PyPI wheel stops at 5.2.0, so newer versions are checked by
  running the same suite inside an installed Blender binary:
  `blender --background --factory-startup --python
  tests/blender/run_in_blender_app.py -- -q`. It forces this checkout's
  `src/` to be the d3blender under test (a user's Blender startup scripts
  may otherwise import another copy, e.g. an editable install from a
  different project's venv) and prints the path it used. Last run: Blender
  5.4.0 Alpha, 57/57 passed in ~35 s, no warnings (the 5.2 wheel: 56
  passed, 1 skipped, ~4 s).
- **The `clean_scene` reset is `read_homefile(use_empty=True,
  use_factory_startup=True)`, not `read_factory_settings(use_empty=True)`.**
  In the full app the latter also resets preferences, which re-registers
  every add-on/extension and re-runs user startup hooks: ~3.2 s per call
  on Blender 5.4, twice per test. That made the in-app run take ~5 minutes,
  ~50x the wheel. `read_homefile` gives an identical empty `bpy.data`
  (checked field by field on 5.2 and 5.4) at ~0.28 s in-app. Don't switch
  back to save a line. The trade-off is that prefs aren't reset between
  tests, which is why the in-app command keeps `--factory-startup`.
- `pyproject.toml` sets `--import-mode=importlib` because `tests/` and
  `tests/blender/` share test-file basenames on purpose (mock vs.
  real-bpy versions of the same feature). With the default import mode,
  a whole-repo `.venv-blender/bin/pytest` died with "import file
  mismatch". Now it runs both suites (~215 tests). Don't "fix" this by
  renaming files or adding `__init__.py` packages instead.
- One real limitation `tests/blender/` surfaced that the mock couldn't:
  **`bpy.context.scene.collection` (the scene's root "Scene Collection")
  is not itself a member of `bpy.data.collections`**, and `get_adapter()`
  builds `adapter.collections` from exactly that list. An object linked
  *only* into the scene root (not into any collection you created) is
  therefore invisible to any selector query -- `select()`'s collection-axis
  doc has no way to reach it, though `get_attr`/`set_attr` on a
  directly-held reference still work fine. Idiomatic d3blender code never
  hits this: `get_or_create_collection()` is the documented way to make a
  join's root container, and its output always lands in
  `bpy.data.collections`. Flagging this as a known gap, not fixing it as
  a side effect of adding tests -- expanding what counts as a "collection"
  changes `scene_doc.py` semantics and deserves its own discussion, not a
  drive-by change.
- Don't report "this works in Blender" unless you've actually run it in
  Blender (the real application, not just the headless `bpy` module) --
  they're the same API surface for everything `d3blender` touches, but
  they're still not identical claims. The mock is deliberately strict
  about attribute access (it raises `AttributeError` for unknown attrs,
  same as real bpy IDs do) so tests exercise the real code paths, not a
  lenient stand-in -- but it's still a mock, one layer further removed
  than either.

## Commands

```bash
pip install -e ".[dev]"        # or: uv venv && uv pip install -e ".[dev]"
pytest                          # full mock suite, ~160 tests, skips tests/blender/
python examples/bar_chart.py    # and the other 14 in examples/ (nine need Blender)

# real-bpy suite (separate venv, see tests/blender/README.md):
uv venv --python 3.13 .venv-blender
uv pip install --python .venv-blender/bin/python -e ".[dev,blender-test]"
.venv-blender/bin/pytest tests/blender     # ~56 tests (+1 skipped on the 5.2 wheel)
.venv-blender/bin/pytest                  # both suites at once (importlib import mode)

# same suite inside a real Blender binary (needs .venv-blender for pytest):
/path/to/blender --background --factory-startup --python tests/blender/run_in_blender_app.py -- -q
```

## If asked to extend this

- New selector features: check whether soupsieve/CSS already expresses it
  before writing a parser extension. It usually does.
- New adapter methods: add to `adapter.py` (bpy-shaped, testable via
  mock) first; only touch `blender_adapter.py` if the behavior genuinely
  differs for a live scene (like `remove()` does, since real
  `bpy.data.objects.remove()` already unlinks from collections and the
  mock has to do that by hand).
- Keep `blender_adapter.py` the only file importing `bpy`. That's what
  makes the rest of the package testable without Blender installed --
  don't erode it for convenience.
