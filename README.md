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
:pseudo(arg)    a predicate with an argument (:has-modifier(BEVEL))
a, b            union, same as CSS
```

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

### `select(adapter, selector_str) -> Selection`
Top-level query against the whole scene.

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

### Adapters
- `d3blender.adapter.SceneAdapter` -- the engine; works against anything
  shaped like `bpy.data` (duck-typed, see below)
- `d3blender.blender_adapter.get_adapter()` -- the one you actually call
  inside Blender; the only place in this package that imports `bpy`
- `d3blender.mock` -- `MockObject` / `MockCollection` / `MockModifier`,
  a fake scene shaped like `bpy.data` for testing without Blender installed

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
    mock.py                  fake bpy-shaped scene for testing
examples/                runnable, mirror the README snippets
tests/                    pytest suite (uses mock.py, no Blender required)
```

## License

MIT -- see `LICENSE`.
