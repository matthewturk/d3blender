"""
selection.py — the d3-shaped surface: `.each()`, `.attr()`, `.filter()`,
scoped `.select()`, and the enter/update/exit join. All structural
matching is delegated to query.py (soupsieve under the hood); this module
only adds the object-oriented ergonomics and the join/reconciliation
pattern, which has no existing-library equivalent.
"""


class Selection:
    def __init__(self, adapter, elements):
        self.adapter = adapter
        self.elements = list(elements)

    def __len__(self):
        return len(self.elements)

    def __iter__(self):
        return iter(self.elements)

    def __repr__(self):
        return f'Selection({len(self.elements)} elements)'

    # -- d3-style verbs -------------------------------------------------

    def each(self, fn):
        for i, el in enumerate(self.elements):
            fn(el, i)
        return self

    def attr(self, key, value=None):
        if value is None:
            return self.adapter.get_attr(self.elements[0], key) if self.elements else None
        for i, el in enumerate(self.elements):
            v = value(el, i) if callable(value) else value
            self.adapter.set_attr(el, key, v)
        return self

    def keyframe(self, frame, **attrs):
        """d3's .transition().attr(...) equivalent -- except Blender
        already has a real tweening engine (F-curves), so this just sets
        values and drops a keyframe at `frame` rather than faking
        interpolation itself. Chain calls at different frames:

            sel.keyframe(1, location=start).keyframe(30, location=end)
        """
        for i, el in enumerate(self.elements):
            for key, value in attrs.items():
                v = value(el, i) if callable(value) else value
                self.adapter.set_attr(el, key, v)
                self.adapter.keyframe_insert(el, key, frame)
        return self

    def filter(self, predicate):
        if callable(predicate):
            kept = [el for el in self.elements if predicate(el)]
        else:
            from . import query
            matched_ids = {id(e) for e in query.select(self.adapter, predicate).elements}
            kept = [el for el in self.elements if id(el) in matched_ids]
        return Selection(self.adapter, kept)

    def select(self, selector_str, axis='collection'):
        """Scoped descendant query: search within the current selection's
        subtree rather than the whole scene. `axis='collection'` walks
        containment (folders); `axis='parent'` walks transform parenting
        (rigs, instancing). Delegates the actual matching to query.select,
        then intersects with the descendant set computed here."""
        universe, seen = [], set()
        if axis == 'collection':
            frontier = list(self.elements)
            while frontier:
                nxt = []
                for el in frontier:
                    for child in self.adapter.collection_children_forward(el):
                        if id(child) not in seen:
                            seen.add(id(child))
                            universe.append(child)
                            nxt.append(child)
                frontier = nxt
        elif axis == 'parent':
            idx = self.adapter.build_parent_children_index()
            frontier = list(self.elements)
            while frontier:
                nxt = []
                for el in frontier:
                    for child in idx.get(id(el), []):
                        if id(child) not in seen:
                            seen.add(id(child))
                            universe.append(child)
                            nxt.append(child)
                frontier = nxt
        else:
            raise ValueError(f"axis must be 'collection' or 'parent', got {axis!r}")

        from . import query
        matched_ids = {id(e) for e in query.select(self.adapter, selector_str).elements}
        kept = [el for el in universe if id(el) in matched_ids]
        return Selection(self.adapter, kept)

    def remove(self):
        for el in self.elements:
            self.adapter.remove(el)
        return Selection(self.adapter, [])

    # -- the join pattern -------------------------------------------------

    def data(self, items, key=None):
        return Join(self.adapter, self, items, key)


class Join:
    """Reconciles the current selection against a data array by identity,
    à la d3's selection.data().join(). Identity is stamped as a custom
    property ('d3_key' by default) on entered elements so reruns are
    idempotent: change the array, rerun the script, get exactly the
    elements the array now describes -- no orphans, no dupes. This part
    has no existing-library equivalent -- it's genuinely Blender-specific
    reconciliation logic, not CSS matching."""

    KEY_PROP = 'd3_key'

    def __init__(self, adapter, selection, items, key_fn):
        self.adapter = adapter
        self.selection = selection
        self.items = list(items)
        self.key_fn = key_fn or (lambda i, d: str(i))

    def join(self, enter, update=None, exit=None):
        existing = {}
        for el in self.selection.elements:
            k = self.adapter.get_attr(el, self.KEY_PROP)
            if k is not None:
                existing[k] = el

        result = []
        used_keys = set()
        for i, d in enumerate(self.items):
            k = self.key_fn(i, d)
            used_keys.add(k)
            el = existing.get(k)
            if el is None:
                el = enter(d)
                self.adapter.set_attr(el, self.KEY_PROP, k)
            elif update is not None:
                update(el, d)
            result.append(el)

        for k, el in existing.items():
            if k not in used_keys:
                if exit is not None:
                    exit(el)
                else:
                    self.adapter.remove(el)

        return Selection(self.adapter, result)
