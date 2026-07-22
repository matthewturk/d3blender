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
- `.each(fn)` -- calls `fn(el, i)` for every element, returns `self`
- `.attr(key, value=None)` -- getter if `value` is `None` (reads the first
  element), setter otherwise; `value` can be a plain value or `fn(el, i)`
- `.keyframe(frame, **attrs)` -- sets each attr and drops a real Blender
  keyframe at `frame`. Blender's own F-curves do the interpolation, so
  this is the whole "transition" story: `sel.keyframe(1, location=a).keyframe(30, location=b)`
- `.filter(predicate)` -- `predicate` can be a selector string or `fn(el) -> bool`
- `.select(selector_str, axis='collection'|'parent')` -- scoped descendant
  query within the current selection's subtree
- `.remove()` -- removes every element in the selection
- `.data(items, key=None) -> Join`

### `Join`
- `.join(enter, update=None, exit=None) -> Selection` -- reconciles by
  identity (a stamped `d3_key` custom property). `enter(d)` must return
  the created element; `update(el, d)` and `exit(el)` are optional (a
  missing `exit` just calls `adapter.remove(el)`).

### `scale.py`
- `scale_linear(domain, range_)` -- `.invert(y)` also available
- `scale_band(domain_items, range_, padding=0.1)` -- `.bandwidth()`, `.step`
- `scale_ordinal(domain_items, range_)` -- cycles if there are more items than range values

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
- `d3blender.blender_adapter.get_adapter()` -- the one you actually call
  inside Blender; the only place in this package that imports `bpy`
- `d3blender.mock` -- `MockObject` / `MockCollection` / `MockModifier` /
  `MockMaterial` / `MockMaterialSlot`, a fake scene shaped like `bpy.data`
  for testing without Blender installed; `new_scene(name)` builds an
  adapter with one collection, and
  `spawn(adapter, collection, name, type_='MESH', **props)` creates and
  links an object into it -- the demo-scaffolding every example needs

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

**This has not yet been exercised against a live Blender install** --
`blender_adapter.py` is written against the documented, stable parts of
`bpy`'s API, but if something doesn't match your Blender version, that's
useful information. Please open an issue with the version number and
what broke.

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
- The `blender_adapter.py` real-Blender glue is unverified against a live
  Blender install (see above).

## Project layout

```
src/d3blender/
    __init__.py         public API
    adapter.py           SceneAdapter -- the engine, works against anything bpy-shaped
    blender_adapter.py    the only file that imports bpy
    scene_doc.py          builds the two synthetic BeautifulSoup docs
    query.py              selector compiler + soupsieve delegation
    selection.py           Selection / Join
    scale.py                scale_linear / scale_band / scale_ordinal
    array.py                 bin / extent / max / min (mirrors d3-array)
    axis.py                   ticks / tick_lines (line-segment tick marks)
    mock.py                    fake bpy-shaped scene for testing
examples/                runnable, mirror the README snippets
tests/                    pytest suite (uses mock.py, no Blender required)
```

## License

MIT -- see `LICENSE`.
