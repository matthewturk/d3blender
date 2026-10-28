"""
query.py — public `select()`. Given a string, compiles a selector down to:

  (axis, css_selector_string, predicates)

`css_selector_string` is handed straight to soupsieve (via BeautifulSoup's
`.select()`), which does all the real work: type/.class/#id/[attr=value]
matching and the ' '/'>' combinators, against whichever axis-doc
(collection containment or transform parenting) applies. `predicates` are
the handful of things CSS genuinely can't express -- numeric attribute
comparisons and domain pseudo-classes like :has-modifier(...) -- applied
as a plain Python filter over the matched elements afterward.

Limitation, stated up front rather than hidden: a single selector must stay
on one axis. "Rig ~ Weapons > mesh" mixes both and is rejected -- write it
as two queries and intersect/chain them.

`select()` also accepts a non-string target -- a single element or an
iterable of elements -- and just wraps it in a `Selection`, no CSS
involved. See its docstring.
"""

import re

from .scene_doc import build_collection_doc, build_parent_doc
from .selection import Selection

_NUMERIC_ATTR_RE = re.compile(r'\[\s*([\w.\-]+)\s*(>=|<=|!=|>|<)\s*([^\]]*)\]')
_PSEUDO_RE = re.compile(r':([A-Za-z_][\w-]*)(?:\(([^)]*)\))?')
_COMBINATOR_RE = re.compile(r'\s*(~>|>|~)\s*|\s+')

_AXIS_COMBINATORS = {' ': 'collection', '>': 'collection', '~': 'parent', '~>': 'parent'}
_CSS_COMBINATOR = {' ': ' ', '>': '>', '~': ' ', '~>': '>'}


def _mask_protected_regions(s):
    out = list(s)
    depth = 0
    for i, c in enumerate(s):
        if c in '[(':
            depth += 1
            continue
        if c in '])':
            depth -= 1
            continue
        if depth > 0:
            out[i] = '\x00'
    return ''.join(out)


def _split_top_level(s, sep_char):
    masked = _mask_protected_regions(s)
    parts, start = [], 0
    for i, c in enumerate(masked):
        if c == sep_char:
            parts.append(s[start:i])
            start = i + 1
    parts.append(s[start:])
    return [p.strip() for p in parts if p.strip()]


def _split_compounds(group_str):
    masked = _mask_protected_regions(group_str)
    compounds, combs, prev_end = [], [], 0
    for m in _COMBINATOR_RE.finditer(masked):
        text = group_str[prev_end:m.start()]
        if text.strip():
            compounds.append(text.strip())
        combs.append(m.group(1) if m.group(1) is not None else ' ')
        prev_end = m.end()
    tail = group_str[prev_end:].strip()
    if tail:
        compounds.append(tail)
    return compounds, combs


def _strip_predicates(compound_text):
    predicates = []

    def _attr_sub(m):
        predicates.append(('attr', m.group(1), m.group(2), m.group(3).strip()))
        return ''

    text = _NUMERIC_ATTR_RE.sub(_attr_sub, compound_text)

    def _pseudo_sub(m):
        predicates.append(('pseudo', m.group(1), m.group(2)))
        return ''

    text = _PSEUDO_RE.sub(_pseudo_sub, text)
    return text.strip(), predicates


def _compounds_to_css(compounds, combs):
    css = compounds[0]
    for comb, compound in zip(combs, compounds[1:]):
        css += (' > ' if _CSS_COMBINATOR[comb] == '>' else ' ') + compound
    return css


def compile_query(selector_str):
    """-> (axis, css_selector_string, predicates)"""
    groups = _split_top_level(selector_str, ',')
    axes_seen = set()
    predicates = []
    css_groups = []
    for group in groups:
        compounds, combs = _split_compounds(group)
        for c in combs:
            axes_seen.add(_AXIS_COMBINATORS[c])
        last_css, group_predicates = _strip_predicates(compounds[-1])
        compounds = compounds[:-1] + [last_css if last_css else '*']
        predicates.extend(group_predicates)
        css_groups.append(_compounds_to_css(compounds, combs))
    if len(axes_seen) > 1:
        raise ValueError(
            "selector mixes collection-axis (' ', '>') and parent-axis "
            "('~', '~>') combinators -- split into two queries instead")
    axis = axes_seen.pop() if axes_seen else 'collection'
    return axis, ', '.join(css_groups), predicates


def _coerce_compare(op, actual, expected_str):
    if actual is None:
        return False
    try:
        a, e = float(actual), float(expected_str)
    except (TypeError, ValueError):
        a, e = str(actual), str(expected_str)
    return {'>': a > e, '<': a < e, '>=': a >= e, '<=': a <= e, '!=': a != e}[op]


def _predicates_ok(adapter, el, predicates):
    for kind, *rest in predicates:
        if kind == 'attr':
            key, op, val = rest
            if not _coerce_compare(op, adapter.get_attr(el, key), val):
                return False
        else:
            name, arg = rest
            pred = adapter.pseudos.get(name)
            if pred is None:
                raise ValueError(f'unknown pseudo-selector :{name}')
            if not pred(el, arg):
                return False
    return True


_NO_TARGET = object()
_default = None


def set_default_adapter(adapter):
    """Make `adapter` what `select()`/`select_all()`/`collection()` use
    when none is passed. Accepts an adapter, a zero-argument factory
    returning one, or `None` to restore the normal behaviour (a fresh
    live adapter per call, inside Blender). Returns the previous setting,
    so tests can restore it. Mostly for the mock and for tests: inside
    Blender the default is already right."""
    global _default
    previous, _default = _default, adapter
    return previous


def default_adapter():
    """The adapter used when a call doesn't pass one: whatever
    set_default_adapter() installed, otherwise a **fresh**
    `blender_adapter.get_adapter()` snapshot. Fresh on every call, on
    purpose: an adapter is a snapshot of bpy.data (see README "Live vs.
    cached"), so caching one here would bring back the stale-index bugs
    get_adapter()'s docstring warns about."""
    if _default is not None:
        return _default() if callable(_default) else _default
    try:
        from .blender_adapter import get_adapter
        return get_adapter()
    except ModuleNotFoundError as exc:
        if exc.name != 'bpy':
            raise
        raise RuntimeError(
            "no adapter given and bpy isn't importable (not running inside "
            "Blender) -- pass one explicitly, e.g. select(adapter, target), or "
            "call d3blender.set_default_adapter(adapter) first"
        ) from None


def _is_collection(x):
    return hasattr(x, 'objects') and hasattr(x, 'children')


def select(*args, adapter=None, target=_NO_TARGET):
    """`select(target)` or `select(adapter, target)` -- both work.

    `target` is either a selector string, or -- mirroring d3's
    `d3.select(node)` -- an element (or iterable of elements) to wrap
    directly, bypassing CSS entirely. Use the latter to re-wrap an element
    you already have (e.g. to `.keyframe()` it) instead of round-tripping
    it through `#name`: Blender's own auto-suffixed names ("Cube.001")
    aren't valid CSS id-selector text, since CSS reads the dot as a class.

    With no adapter (one positional argument, or `adapter=None`), a fresh
    one comes from default_adapter() -- inside Blender, a new
    `get_adapter()` snapshot per call. The selection keeps that adapter
    for everything chained off it."""
    if len(args) > 2:
        raise TypeError(f'select() takes at most 2 positional arguments ({len(args)} given)')
    if len(args) == 2:
        adapter, target = args
    elif len(args) == 1:
        if target is _NO_TARGET:
            target = args[0]
        else:
            adapter = args[0]
    if target is _NO_TARGET:
        raise TypeError("select() missing the 'target' argument")
    if adapter is None:
        adapter = default_adapter()

    if not isinstance(target, str):
        elements = list(target) if hasattr(target, '__iter__') else [target]
        return Selection(adapter, elements)

    axis, css, predicates = compile_query(target)
    soup, ref_map = build_collection_doc(adapter) if axis == 'collection' else build_parent_doc(adapter)
    seen, elements = set(), []
    for tag in soup.scene.select(css):
        el = ref_map[tag['data-ref']]
        if id(el) in seen:
            continue
        if _predicates_ok(adapter, el, predicates):
            seen.add(id(el))
            elements.append(el)
    return Selection(adapter, elements)


def select_all(target, selector=None, adapter=None):
    """d3's `parent.selectAll(...)`: the usual way to start a join.

    - `target` a **collection**: its own objects (direct members, not
      nested collections'), with the collection remembered as the
      selection's `parent` -- so `.data(...).join('cube')` creates new
      elements in it and a rerun finds and updates them in place:

          bars = select_all(chart).data(rows, key='label').join('cube')

    - `target` a selector string or element(s): same as `select()`, no
      parent.

    `selector` optionally narrows the result (a selector string or a
    predicate, as in `.filter()`), e.g. `select_all(chart, '.bar')` when
    one collection holds several independently joined groups -- without
    it, a join would treat the other group's keyed objects as its own
    exits. Tag a group with `.classed('bar', True)` after its join.

    `adapter` defaults as in select()."""
    if adapter is None:
        adapter = default_adapter()
    if _is_collection(target):
        sel = Selection(adapter, adapter.collection_objects(target), parent=target)
    else:
        sel = select(adapter, target)
    return sel.filter(selector) if selector is not None else sel


def collection(name, parent=None, adapter=None):
    """Get-or-create a collection -- `adapter.get_or_create_collection()`
    without having to hold an adapter. See that method for how `parent`
    scopes the lookup."""
    if adapter is None:
        adapter = default_adapter()
    return adapter.get_or_create_collection(name, parent=parent)
