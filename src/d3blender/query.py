"""
query.py — public `select()`. Compiles a selector string down to:

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


def select(adapter, selector_str):
    axis, css, predicates = compile_query(selector_str)
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
