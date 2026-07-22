"""
adapter.py — the only file that touches Blender-shaped data. Written
against duck-typed objects mirroring bpy's real API surface (`.type`,
`.name`, `.parent`, `.users_collection`, `.get()`, `.keys()`, `.objects`,
`.children`) so the same class works against a mock scene or real
bpy.data.

Two axes, matching Blender's two real hierarchies:
  - COLLECTION axis: containment (`.users_collection`, `.children`)
  - PARENT axis: transform parenting (`.parent`) -- objects only
"""

_MISSING = object()


class _Collection:
    """Minimal duck-typed collection -- name/objects/children plus the
    generic custom-prop get()/__setitem__ shape everything else in this
    package expects. This is get_or_create_collection()'s default
    construction, deliberately self-contained (not d3blender.mock's
    MockCollection) so adapter.py doesn't depend on the mock/test module.
    LiveBlenderAdapter overrides construction with a real
    bpy.data.collections.new(), which also needs linking into the scene
    to actually be visible."""

    def __init__(self, name):
        self.name = name
        self.objects = []
        self.children = []
        self._props = {}

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __setitem__(self, key, value):
        self._props[key] = value

    def __repr__(self):
        return f'<Collection {self.name}>'


def _resolve_one(cur, part):
    if cur is None:
        return None
    val = getattr(cur, part, _MISSING)
    if val is not _MISSING:
        return val
    getter = getattr(cur, 'get', None)
    if callable(getter):
        try:
            got = getter(part)
            if got is not None:
                return got
        except Exception:
            pass
    try:
        return cur[part]
    except Exception:
        return None


class SceneAdapter:
    def __init__(self, objects, collections):
        self.objects = list(objects)
        self.collections = list(collections)
        self._collection_parent = self._build_collection_parent_index()
        self.pseudos = {
            'selected': lambda el, arg: bool(getattr(el, 'selected', False)),
            'visible': lambda el, arg: not bool(getattr(el, 'hidden', False)),
            'hidden': lambda el, arg: bool(getattr(el, 'hidden', False)),
            'has-modifier': lambda el, arg: arg in [m.type for m in getattr(el, 'modifiers', [])],
        }

    # -- identity / attributes ------------------------------------------

    def type_of(self, el):
        kind = getattr(el, 'type', None)
        return kind.lower() if kind is not None else 'collection'

    def name_of(self, el):
        return getattr(el, 'name', None)

    def classes_of(self, el):
        raw = _resolve_one(el, 'd3_class') or ''
        return set(raw.split())

    def get_attr(self, el, path):
        cur = el
        for part in path.split('.'):
            cur = _resolve_one(cur, part)
        return cur

    def simple_attrs(self, el):
        """Scalar custom properties, exposed as plain CSS attribute text
        (e.g. [hp=30]) -- soupsieve handles equality/existence natively;
        query.py only needs to add numeric comparison on top."""
        props = getattr(el, '_props', None)
        if props is not None:
            return dict(props)
        keys_fn = getattr(el, 'keys', None)
        if callable(keys_fn):
            try:
                return {k: el[k] for k in keys_fn()}
            except Exception:
                return {}
        return {}

    def set_attr(self, el, key, value):
        try:
            setattr(el, key, value)
        except Exception:
            el[key] = value

    def keyframe_insert(self, el, data_path, frame):
        el.keyframe_insert(data_path=data_path, frame=frame)

    def remove(self, el):
        # Real adapter: bpy.data.objects.remove(el, do_unlink=True), which
        # automatically unlinks from every collection. This mock keeps
        # collection membership as separate lists, so it has to do that
        # unlinking by hand.
        if el in self.objects:
            self.objects.remove(el)
        if el in self.collections:
            self.collections.remove(el)
        for c in self.collections:
            if el in getattr(c, 'objects', []):
                c.objects.remove(el)
            if el in getattr(c, 'children', []):
                c.children.remove(el)

    def parent_of(self, el):
        return getattr(el, 'parent', None)

    # -- collection axis, forward traversal (native to Blender) --------

    def top_level_collections(self):
        return [c for c in self.collections if id(c) not in self._collection_parent]

    def sub_collections(self, coll):
        return list(getattr(coll, 'children', []))

    def collection_objects(self, coll):
        return list(getattr(coll, 'objects', []))

    def objects_without_collection(self):
        return [o for o in self.objects if not getattr(o, 'users_collection', None)]

    def get_or_create_collection(self, name, parent=None):
        """Get-or-create a collection by name -- the Blender equivalent of
        d3.create('svg'): a container to serve as a join's root. Pass
        `parent` (another collection already known to this adapter) to
        nest the new collection instead of adding it at the top level."""
        for c in self.collections:
            if self.name_of(c) == name:
                return c
        coll = _Collection(name)
        self.collections.append(coll)
        if parent is not None:
            parent.children.append(coll)
            self._collection_parent.setdefault(id(coll), []).append(parent)
        return coll

    def collection_children_forward(self, el):
        if hasattr(el, 'objects') and hasattr(el, 'children'):
            return list(el.objects) + list(el.children)
        return []

    # -- parent axis, forward traversal (needs one small reverse index) -

    def build_parent_children_index(self):
        idx = {}
        for o in self.objects:
            p = getattr(o, 'parent', None)
            if p is not None:
                idx.setdefault(id(p), []).append(o)
        return idx

    # -- internal ---------------------------------------------------------

    def _build_collection_parent_index(self):
        idx = {}
        for c in self.collections:
            for child in getattr(c, 'children', []):
                idx.setdefault(id(child), []).append(c)
        return idx
