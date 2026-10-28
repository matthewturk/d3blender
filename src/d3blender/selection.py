"""
selection.py — the d3-shaped surface: `.each()`, `.attr()`, `.filter()`,
scoped `.select()`, and the enter/update/exit join. All structural
matching is delegated to query.py (soupsieve under the hood); this module
only adds the object-oriented ergonomics and the join/reconciliation
pattern, which has no existing-library equivalent.
"""

import inspect


def _arity(fn):
    """Parameter count of `fn` -- lets accessor/each/filter callables be
    written as `fn(el)`, `fn(el, i)`, or `fn(el, d, i)` and have the right
    one picked automatically (see _invoke). Real d3's own accessors are
    `(d, i) => ...`, receiving the bound datum directly, because a d3
    selection keeps data bound to each DOM node permanently once joined.
    d3blender mirrors that with a parallel Selection.datum list (see
    Join.join() below) instead of attaching data to the element itself --
    not every adapter's elements can hold arbitrary Python attributes
    (a real bpy ID can't). Falls back to 2 -- the pre-existing `(el, i)`
    shape -- for a callable inspect can't read (rare: some builtins),
    so nothing regresses for those.

    A callable taking `*args` (`lambda *a: ...`, `def f(el, *rest)`, a
    generic wrapper/decorator) counts as 3: it can accept the full
    `(el, d, i)`, so it gets it, rather than the arbitrary truncation a
    plain parameter count would give it (`lambda *a` used to count as 1
    and receive only `el`)."""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return 2
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in params):
        return 3
    return len(params)


def _invoke(fn, el, d, i):
    """Call `fn` with however many positional args its own arity calls
    for -- `fn(el)`, `fn(el, i)`, or `fn(el, d, i)`. The one place all
    of Selection's callable-accepting methods (attr, each, keyframe,
    filter) dispatch through, so all three call shapes work consistently
    everywhere a callable is accepted."""
    n = _arity(fn)
    if n >= 3:
        return fn(el, d, i)
    if n == 2:
        return fn(el, i)
    return fn(el)


class Selection:
    def __init__(self, adapter, elements, datum=None, parent=None):
        """`datum` is the bound-data counterpart to `.elements` -- one
        entry per element, in the same order, or `None` for each element
        if this selection has no bound data (e.g. a plain `select()`
        query, not the result of `.data().join()`). Real d3 attaches
        `__data__` to the node itself and never needs a parallel list;
        d3blender can't do that generically (see _arity's docstring), so
        it tracks the same information alongside `.elements` instead.

        `parent` is the collection these elements were selected *from*,
        when that's known -- set by `select_all(collection)`, the
        equivalent of d3's `parent.selectAll(...)` keeping its parent
        node. `.join()` uses it as the default home for entered
        elements (see Join.join). `None` for every other selection.

        `entered` / `updated` are only set on a `.join()` result: the
        sub-selections of elements that were just created vs. already
        existed (both bound to their data). `None` elsewhere."""
        self.adapter = adapter
        self.elements = list(elements)
        self.datum = list(datum) if datum is not None else [None] * len(self.elements)
        self.parent = parent
        self.entered = None
        self.updated = None

    def __len__(self):
        return len(self.elements)

    def __iter__(self):
        return iter(self.elements)

    def __repr__(self):
        return f'Selection({len(self.elements)} elements)'

    # -- d3-style verbs -------------------------------------------------

    def each(self, fn):
        for i, (el, d) in enumerate(zip(self.elements, self.datum)):
            _invoke(fn, el, d, i)
        return self

    def attr(self, key, value=None):
        if value is None:
            return self.adapter.get_attr(self.elements[0], key) if self.elements else None
        for i, (el, d) in enumerate(zip(self.elements, self.datum)):
            v = _invoke(value, el, d, i) if callable(value) else value
            self.adapter.set_attr(el, key, v)
        return self

    def classed(self, names, value=None):
        """d3's `selection.classed(names[, value])` -- toggles one or
        more classes in the space-separated `d3_class` custom property
        that already powers `.foo`-style selectors (see `classes_of()`),
        rather than replacing the whole string -- other classes already
        on an element are preserved. `names` can be space-separated,
        exactly like d3's own multi-class form (`.classed('enemy boss',
        True)` adds both).

        Getter (`value` is `None`): whether the *first* element has
        *all* of `names` -- same "first element" convention as
        `.attr()`'s getter, `False` for an empty selection.

        Setter: `value` is a plain bool, applied to every element, or a
        callable (`(el)`/`(el, i)`/`(el, d, i)`, same dispatch as
        everywhere else) returning one per element. `True` adds the
        class(es), `False` removes them."""
        names = names.split()
        if value is None:
            if not self.elements:
                return False
            current = self.adapter.classes_of(self.elements[0])
            return all(n in current for n in names)
        for i, (el, d) in enumerate(zip(self.elements, self.datum)):
            want = _invoke(value, el, d, i) if callable(value) else value
            classes = self.adapter.classes_of(el)
            if want:
                classes.update(names)
            else:
                classes.difference_update(names)
            self.adapter.set_attr(el, 'd3_class', ' '.join(sorted(classes)))
        return self

    def keyframe(self, frame, **attrs):
        """d3's .transition().attr(...) equivalent -- except Blender
        already has a real tweening engine (F-curves), so this just sets
        values and drops a keyframe at `frame` rather than faking
        interpolation itself. Chain calls at different frames:

            sel.keyframe(1, location=start).keyframe(30, location=end)

        `frame` can be a plain number (every element keyframed at the
        same frame) or a callable with the same `(el)`/`(el, i)`/
        `(el, d, i)` dispatch as the attr values, evaluated once per
        element -- so each element can land on its own frame, e.g. one
        derived from its bound datum:

            sel.keyframe(lambda el, d, i: d['frame'], location=lambda el, d, i: d['pos'])
        """
        for i, (el, d) in enumerate(zip(self.elements, self.datum)):
            f = _invoke(frame, el, d, i) if callable(frame) else frame
            for key, value in attrs.items():
                v = _invoke(value, el, d, i) if callable(value) else value
                self.adapter.set_attr(el, key, v)
                self.adapter.keyframe_insert(el, key, f)
        return self

    def transition(self, duration=24, delay=0, start=None):
        """d3's `selection.transition()`, built on `.keyframe()`: returns
        a Transition whose `.attr(key, value)` keyframes each element's
        *current* value at `start + delay` and the new value at
        `start + delay + duration` (frames). Blender's F-curves do the
        in-between, as everywhere else here -- there's no tweening or
        easing in Python.

        `start` defaults to the scene's current frame. `duration`,
        `delay` and `start` can each be a number or a per-element
        callable (`(el)`/`(el, i)`/`(el, d, i)`), so a staggered entrance
        is just `delay=lambda el, i: i * 3`:

            bars.transition(20, delay=lambda el, i: i * 3).attr('scale', lambda el, d, i: ...)
        """
        return Transition(self, duration, delay, start)

    def filter(self, predicate):
        kept, kept_data = [], []
        if callable(predicate):
            for i, (el, d) in enumerate(zip(self.elements, self.datum)):
                if _invoke(predicate, el, d, i):
                    kept.append(el)
                    kept_data.append(d)
        else:
            from . import query
            matched_ids = {id(e) for e in query.select(self.adapter, predicate).elements}
            for el, d in zip(self.elements, self.datum):
                if id(el) in matched_ids:
                    kept.append(el)
                    kept_data.append(d)
        return Selection(self.adapter, kept, datum=kept_data, parent=self.parent)

    def select(self, selector_str, axis='collection'):
        """Scoped descendant query: search within the current selection's
        subtree rather than the whole scene. `axis='collection'` walks
        containment (folders); `axis='parent'` walks transform parenting
        (rigs, instancing). Delegates the actual matching to query.select,
        then intersects with the descendant set computed here.

        Deliberately returns an *unbound* Selection (datum all `None`),
        not this selection's own bound data carried down to whatever
        descendants it finds -- unlike .filter() (a subset of the same
        elements, so each survivor's datum obviously carries over), a
        descendant here isn't the same thing .data() was ever bound to,
        and there's no 1:1 parent-datum-to-child mapping to fall back on
        (one parent can have many matching descendants). Rebind with a
        fresh `.data()` if you need one."""
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
        self.key_fn = _key_function(key_fn)

    def join(self, enter, update=None, exit=None, **create_kwargs):
        """`enter` is normally a callable `d -> element`. It can also be
        a shape name (a string, e.g. `'uv_sphere'`) -- d3's own
        `selection.join("circle")` shorthand, which desugars to
        `enter => enter.append("circle")` since the DOM has one
        universal "create an element of this type" primitive. Blender's
        object creation isn't remotely that uniform (a sphere and a
        camera and an empty are built through entirely different APIs),
        so this doesn't invent a generic creator -- it dispatches to
        `self.adapter.creator(enter, **create_kwargs)`, a small, adapter-
        owned registry of the handful of cases that genuinely are
        unambiguous (see LiveBlenderAdapter.creator -- real bpy's own
        primitive-mesh operators, real bpy only, no mock equivalent,
        same split as everywhere else creation-related in this library).
        `create_kwargs` only makes sense alongside the string form --
        passing it with a callable `enter` is almost certainly a
        mistake, so it's a hard error, not silently ignored.

        **The selection's parent collection is the default home for new
        elements**, like d3's `parent.selectAll(...).data(...).join(...)`
        appending to `parent`. When the selection came from
        `select_all(collection)`:
          - the string form uses that collection unless `collection=` is
            passed explicitly;
          - an element a callable `enter` returns that isn't linked into
            any collection yet (e.g. a bare `bpy.data.objects.new()`) is
            linked into it. One that already is linked somewhere is left
            exactly where `enter` put it.
        Without a known parent, behaviour is unchanged: `collection=` is
        required for the string form, and `enter`'s result is untouched.

        Returns the merged enter + update selection, in data order, bound
        to the data -- so chained `.attr()`/`.keyframe()`/`.transition()`
        apply to every element the data describes, new or not (d3 v5+'s
        `join()` merge). `.entered` and `.updated` on the result hold the
        two halves separately, e.g. to animate only new elements in."""
        parent = self.selection.parent
        if isinstance(enter, str):
            if 'collection' not in create_kwargs and parent is not None:
                create_kwargs['collection'] = parent
            enter = self.adapter.creator(enter, **create_kwargs)
        elif create_kwargs:
            raise TypeError(
                f"join() got creator kwargs ({sorted(create_kwargs)}) but 'enter' "
                "is a callable, not a shape name string -- those only apply "
                "to the enter='shape_name' form"
            )

        existing = {}
        for el in self.selection.elements:
            k = self.adapter.get_attr(el, self.KEY_PROP)
            if k is not None:
                existing[k] = el

        result, result_data = [], []
        entered, entered_data, updated, updated_data = [], [], [], []
        used_keys = set()
        for i, d in enumerate(self.items):
            k = self.key_fn(i, d)
            used_keys.add(k)
            el = existing.get(k)
            if el is None:
                el = enter(d)
                if parent is not None and not getattr(el, 'users_collection', None):
                    self.adapter.link(el, parent)
                self.adapter.set_attr(el, self.KEY_PROP, k)
                entered.append(el)
                entered_data.append(d)
            else:
                if update is not None:
                    update(el, d)
                updated.append(el)
                updated_data.append(d)
            result.append(el)
            result_data.append(d)  # this element's bound datum -- see Selection.datum

        for k, el in existing.items():
            if k not in used_keys:
                if exit is not None:
                    exit(el)
                else:
                    self.adapter.remove(el)

        merged = Selection(self.adapter, result, datum=result_data, parent=parent)
        merged.entered = Selection(self.adapter, entered, datum=entered_data, parent=parent)
        merged.updated = Selection(self.adapter, updated, datum=updated_data, parent=parent)
        return merged


def _key_function(key):
    """Normalize `.data(items, key=...)` to the internal `(i, d) -> key`.

    - `None`: the item's index (as a string), unchanged.
    - a string: that field of each item -- `key='label'` is `d['label']`.
    - a 1-parameter callable: `fn(d)`, d3's usual `d => d.id` shape.
    - a 2-parameter callable: `fn(i, d)` -- this library's original
      form, kept for existing callers. Note the order is (i, d), the
      reverse of d3's own (d, i)."""
    if key is None:
        return lambda i, d: str(i)
    if isinstance(key, str):
        field = key
        return lambda i, d: d[field]
    if _arity(key) == 1:
        return lambda i, d: key(d)
    return key


def _per_element(value, el, d, i):
    return _invoke(value, el, d, i) if callable(value) else value


class Transition:
    """What `Selection.transition()` returns. `.attr(key, value)` writes
    two keyframes per element -- the current value at its start frame,
    the new value at its end frame -- and returns the transition, so
    several attrs chain into one timed change. See
    Selection.transition() for the timing arguments.

    `.duration(n)` / `.delay(n)` re-time any `.attr()` calls that follow
    (numbers or per-element callables, same as the constructor), and
    `.transition(duration, delay=0)` starts a *following* transition at
    each element's end frame, like d3's chained transitions.
    `.selection()` returns the underlying Selection.

    If an element has no current value for `key` yet (a custom property
    that doesn't exist), there's nothing to animate *from*, so only the
    end keyframe is written. No easing here, by design: set the F-curve
    interpolation in Blender (or Preferences > Animation > Default
    Interpolation) instead."""

    def __init__(self, selection, duration=24, delay=0, start=None):
        self._selection = selection
        self._duration = duration
        self._delay = delay
        self._start = start

    def _frames(self, el, d, i):
        start = self._start
        if start is None:
            start = self._selection.adapter.current_frame()
        else:
            start = _per_element(start, el, d, i)
        f0 = start + _per_element(self._delay, el, d, i)
        return f0, f0 + _per_element(self._duration, el, d, i)

    def attr(self, key, value):
        sel = self._selection
        adapter = sel.adapter
        for i, (el, d) in enumerate(zip(sel.elements, sel.datum)):
            f0, f1 = self._frames(el, d, i)
            if adapter.get_attr(el, key) is not None:
                adapter.keyframe_insert(el, key, f0)
            adapter.set_attr(el, key, _per_element(value, el, d, i))
            adapter.keyframe_insert(el, key, f1)
        return self

    def duration(self, *value):
        if not value:
            return self._duration
        self._duration = value[0]
        return self

    def delay(self, *value):
        if not value:
            return self._delay
        self._delay = value[0]
        return self

    def transition(self, duration=24, delay=0):
        previous = self

        def start(el, d, i):
            return previous._frames(el, d, i)[1]

        return Transition(self._selection, duration, delay, start)

    def selection(self):
        return self._selection
