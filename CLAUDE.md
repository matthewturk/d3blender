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
`.keyframe()`). `adapter.py` is the only thing that knows how to read a
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
real Blender plus both packages installed, same category as
`scatter_plot_3d_blender.py`. It's written against verified, current,
real APIs, not guessed ones, but that's still not the same claim as
"run and confirmed working."

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
- `blender_adapter.py` has **not** been run against a real Blender
  install by anyone yet. It's written against documented, stable bpy API
  (`bpy.data.objects/collections`, `.type`, `.parent`,
  `.users_collection`, `Collection.objects/.children`, `ID.keys()/.get()`),
  but "written correctly from documentation" and "verified against a live
  install" are different claims. If you're asked to fix a bug in real
  Blender usage, that's the first place to look, and it's expected that
  something may not match.
- Don't report "this works in Blender" unless you've actually run it in
  Blender. The mock is deliberately strict about attribute access (it
  raises `AttributeError` for unknown attrs, same as real bpy IDs do) so
  tests exercise the real code paths, not a lenient stand-in -- but it's
  still a mock.

## Commands

```bash
pip install -e ".[dev]"        # or: uv venv && uv pip install -e ".[dev]"
pytest                          # full suite, ~53 tests
python examples/bar_chart.py    # and the other 6 in examples/ (two need Blender)
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
