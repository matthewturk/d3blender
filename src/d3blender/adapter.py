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

# Mesh point-domain (per-vertex) attribute shapes -- verified against real
# bpy 5.2 (see tests/blender/test_point_attrs.py): a POINT-domain attribute's
# value lives under a type-dependent field name, same "duck-typed shape
# lookup" pattern as the GN input value holder above (_gn_input_get).
# Position itself is deliberately NOT routed through this table -- it's
# handled separately via mesh.vertices[i].co, the always-present, always-
# stable API, rather than relying on the newer unified-attributes view of
# position (confirmed equivalent, but younger and less universally assumed).
_POINT_ATTR_SHAPE = {
    'FLOAT': (1, 'value'),
    'INT': (1, 'value'),
    'BOOLEAN': (1, 'value'),
    'FLOAT_VECTOR': (3, 'vector'),
    'FLOAT_COLOR': (4, 'color'),
}


def _infer_point_attr_type(value):
    """Pick a mesh.attributes.new(type=...) value from a sample Python
    value, for set_point_attr()'s create-on-first-write path. bool before
    int matters -- bool is an int subclass in Python."""
    if isinstance(value, bool):
        return 'BOOLEAN'
    if isinstance(value, int):
        return 'INT'
    if isinstance(value, float):
        return 'FLOAT'
    if isinstance(value, (tuple, list)):
        if len(value) == 3:
            return 'FLOAT_VECTOR'
        if len(value) == 4:
            return 'FLOAT_COLOR'
    raise TypeError(
        f"can't infer a point-attribute type for {value!r} -- expected a "
        "float, int, bool, or a 3- or 4-tuple (vector/color)")


def _check_point_count(adapter, el, name, n, values):
    """Shared by SceneAdapter.set_point_attr and LiveBlenderAdapter's bulk
    override -- set_point_attr never resizes a mesh to fit (see CLAUDE.md),
    so a length mismatch is always a clear error, not an implicit rebuild,
    on both code paths identically."""
    if len(values) != n:
        raise ValueError(
            f"set_point_attr({name!r}): got {len(values)} values for "
            f"{n} points on {adapter.name_of(el)!r} -- set_point_attr "
            "never resizes the mesh; rebuild it explicitly first if "
            "the point count actually changed"
        )


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


def _gn_input_identifier(modifier, name):
    """If `modifier` is a Geometry Nodes modifier exposing a node-group
    interface (Blender 4.0+/5.x shape: `node_group.interface.items_tree`),
    resolve a human-readable input socket name ("Size") to the underlying
    ID-property key ("Input_2") that actually stores the value. None if
    there's no match -- duck-typed, so this works the same against the
    mock and real bpy, no bpy import needed."""
    node_group = getattr(modifier, 'node_group', None)
    interface = getattr(node_group, 'interface', None)
    items = getattr(interface, 'items_tree', None)
    if items is None:
        return None
    for item in items:
        if getattr(item, 'in_out', None) == 'INPUT' and getattr(item, 'name', None) == name:
            return getattr(item, 'identifier', None)
    return None


def _gn_input_get(modifier, identifier):
    """Read a Geometry Nodes input given its identifier (e.g. "Socket_0"
    -- as of Blender 5.2 the identifiers themselves changed shape too,
    no longer "Input_N"). GN modifier inputs stopped being plain ID
    properties (`modifier[identifier]`, which now raises "id properties
    not supported for this type") and moved onto a dedicated property
    group: `modifier.properties.inputs[identifier]` is an `IDPropertyGroup`
    holding the actual value under `["value"]` -- verified against real
    bpy 5.2.0 (see tests/blender/) for float/int/bool/string/object/vector
    sockets alike, all `IDPropertyGroup`. The `hasattr(holder, 'value')`
    branch is a defensive duck-typed fallback for a plain-RNA-property
    wrapper shape, not one observed in practice -- kept in case some
    socket type or future version exposes one; don't read it as evidence
    such a shape currently exists. This project targets 5.3+, so there's
    deliberately no fallback to the pre-5.2 direct-subscript shape (same
    policy as _gn_input_identifier's node_group.interface lookup)."""
    holder = modifier.properties.inputs[identifier]
    return holder.value if hasattr(holder, 'value') else holder['value']


def _gn_input_set(modifier, identifier, value):
    """Write side of _gn_input_get -- same `["value"]` (or `.value`)
    access, since `modifier[identifier] = value` now raises "id
    properties not supported for this type" on Blender 5.2+."""
    holder = modifier.properties.inputs[identifier]
    if hasattr(holder, 'value'):
        holder.value = value
    else:
        holder['value'] = value


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
        pass
    identifier = _gn_input_identifier(cur, part)
    if identifier is not None:
        try:
            return _gn_input_get(cur, identifier)
        except Exception:
            return None
    return None


class _MeshObject:
    """Minimal duck-typed mesh object -- just enough shape (name/type/
    parent/custom-props) for the selector engine and Selection to treat
    it like any other object. Holds the raw (vertices, edges) as
    `.mesh_data`, since there's no real geometry to inspect otherwise.
    This is create_line_mesh()'s default construction; LiveBlenderAdapter
    overrides it with a real bpy.data.meshes.new()+from_pydata()."""

    def __init__(self, name, vertices, edges):
        self.name = name
        self.type = 'MESH'
        self.parent = None
        self.mesh_data = (vertices, edges)
        self._props = {}

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __setitem__(self, key, value):
        self._props[key] = value

    def __repr__(self):
        return f'<Object {self.name}>'


def _segments_to_vertices_edges(segments):
    vertices, edges = [], []
    for p0, p1 in segments:
        i = len(vertices)
        vertices.append(tuple(p0))
        vertices.append(tuple(p1))
        edges.append((i, i + 1))
    return vertices, edges


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
            'has-material': lambda el, arg: arg in [
                slot.material.name for slot in getattr(el, 'material_slots', []) if slot.material
            ],
        }

    # -- identity / attributes ------------------------------------------

    def type_of(self, el):
        kind = getattr(el, 'type', None)
        return kind.lower() if kind is not None else 'collection'

    def name_of(self, el):
        return getattr(el, 'name', None)

    def material_of(self, el):
        """The object's active material name, if any -- exposed to the
        selector engine as a synthetic 'material' attribute (see
        scene_doc.py), so `[material=Enemy_Red]`/`[material]` just work
        via existing CSS attribute matching. Only sees the *active*
        material; an object with several material slots but a different
        (or no) active one needs `:has-material(Name)` instead."""
        mat = getattr(el, 'active_material', None)
        return getattr(mat, 'name', None) if mat is not None else None

    def classes_of(self, el):
        raw = _resolve_one(el, 'd3_class') or ''
        return set(raw.split())

    def get_attr(self, el, path):
        """`path` is either a dot-joined string ("modifiers.Bevel.width"
        -- convenient, but ambiguous if any name in the chain contains a
        literal '.', e.g. an auto-uniquified "Scatter.001" modifier) or a
        tuple of segments ("modifiers", "Scatter.001", "width") -- always
        unambiguous, since no splitting happens. Reach for the tuple form
        whenever a name might contain a dot."""
        parts = path.split('.') if isinstance(path, str) else list(path)
        cur = el
        for part in parts:
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

    def set_attr(self, el, path, value):
        """Same string-vs-tuple contract as get_attr(). Walks to the
        second-to-last segment, then sets the last one -- through a
        Geometry Nodes input's name if that's what it resolves to
        (see _gn_input_identifier/_gn_input_set), otherwise a plain
        setattr/subscript exactly like before path support existed."""
        parts = path.split('.') if isinstance(path, str) else list(path)
        *init, last = parts
        cur = el
        for part in init:
            cur = _resolve_one(cur, part)
        identifier = _gn_input_identifier(cur, last)
        if identifier is not None:
            _gn_input_set(cur, identifier, value)
            return
        try:
            setattr(cur, last, value)
        except Exception:
            cur[last] = value

    def gn_inputs(self, modifier):
        """{name: current_value} for every input socket on a Geometry
        Nodes modifier's node-group interface -- for inspecting what's
        available before .attr()-ing into one of them by name."""
        node_group = getattr(modifier, 'node_group', None)
        interface = getattr(node_group, 'interface', None)
        items = getattr(interface, 'items_tree', None) or []
        result = {}
        for item in items:
            if getattr(item, 'in_out', None) != 'INPUT':
                continue
            name = getattr(item, 'name', None)
            identifier = getattr(item, 'identifier', None)
            if name is None or identifier is None:
                continue
            try:
                result[name] = _gn_input_get(modifier, identifier)
            except Exception:
                result[name] = None
        return result

    # -- per-vertex ("point") data ---------------------------------------
    #
    # A different granularity than get_attr/set_attr above: those read/write
    # one property on one object; these read/write one value *per vertex*,
    # for the case where the data you're visualizing has too many points to
    # sensibly be one object each (see CLAUDE.md). Generic, duck-typed
    # per-item loop here so it's correct against both the mock and real bpy
    # with no bpy import; LiveBlenderAdapter overrides both with a bulk
    # foreach_get/foreach_set version, since that loop is ~100x slower than
    # bulk access on real meshes at any real point count (measured against
    # tests/blender/) -- the whole reason to reach for vertices over objects
    # is scale, so the naive version would quietly defeat its own purpose
    # there. Correctness lives here either way; LiveBlenderAdapter's override
    # is purely a performance override, never a behavior difference.

    def point_count(self, el):
        """Number of vertices on `el`'s mesh -- 0 if `el` isn't a mesh
        object at all."""
        vertices = getattr(getattr(el, 'data', None), 'vertices', None)
        return len(vertices) if vertices is not None else 0

    def point_attr(self, el, name):
        """The whole per-vertex array for point-domain attribute `name`,
        one entry per vertex, in vertex-index order. `name='position'` is
        `.co`; anything else is a named entry in `mesh.attributes` (create
        it first via set_point_attr -- reading an attribute that doesn't
        exist is a KeyError, same as reading a dict key that isn't there)."""
        mesh = el.data
        if name == 'position':
            return [tuple(v.co) for v in mesh.vertices]
        attr = mesh.attributes[name]
        arity, field = _POINT_ATTR_SHAPE[attr.data_type]
        if arity == 1:
            return [getattr(item, field) for item in attr.data]
        return [tuple(getattr(item, field)) for item in attr.data]

    def set_point_attr(self, el, name, values):
        """Write a whole per-vertex array in one call -- `values` must have
        exactly as many entries as `el` has vertices. Deliberately never
        resizes the mesh to fit: a length mismatch is a clear error, not an
        implicit rebuild (see CLAUDE.md) -- rebuild the mesh yourself first
        if the point count genuinely changed. Creates the attribute (typed
        by inference from `values[0]`, see _infer_point_attr_type) the
        first time you write a new name; after that, the existing type
        sticks, same as a modifier property would."""
        mesh = el.data
        values = list(values)
        _check_point_count(self, el, name, self.point_count(el), values)
        if name == 'position':
            for vertex, co in zip(mesh.vertices, values):
                vertex.co = co
            mesh.update()
            return
        if name in mesh.attributes:
            attr = mesh.attributes[name]
        else:
            attr = mesh.attributes.new(
                name=name, type=_infer_point_attr_type(values[0]), domain='POINT')
        arity, field = _POINT_ATTR_SHAPE[attr.data_type]
        for item, value in zip(attr.data, values):
            setattr(item, field, value)
        mesh.update()

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

    def creator(self, name, collection, **create_kwargs):
        """Resolve a shape name (e.g. `'uv_sphere'`) to an `enter`
        callable for `Join.join()`'s string shorthand -- see its
        docstring. The base/mock adapter can't fulfill this at all:
        there's no bpy.ops equivalent here to dispatch to, and this
        deliberately doesn't grow a hand-rolled geometry generator to
        fake one (see CLAUDE.md's "no primitive-mesh functions"
        discussion -- reinventing what Blender's own primitive
        operators already do well is exactly the trap this library has
        avoided elsewhere). `LiveBlenderAdapter.creator()` is the real
        implementation; against the mock, build your own starting shape
        with `mock.spawn()`/`spawn_points()` and pass a plain callable
        `enter` instead."""
        raise NotImplementedError(
            f"creator({name!r}) needs a real Blender adapter (LiveBlenderAdapter) -- "
            "the mock has no bpy.ops equivalent for building primitive geometry. "
            "Use mock.spawn()/spawn_points() with your own vertex data and pass a "
            "plain callable as join()'s enter= instead."
        )

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

    def create_line_mesh(self, collection, name, segments):
        """Create a single mesh object containing one edge per (p0, p1)
        pair in `segments` (e.g. one edge per axis tick mark from
        d3blender.axis.tick_lines()), linked into `collection` -- much
        cheaper than one object per segment. Base implementation builds a
        minimal duck-typed mesh object; LiveBlenderAdapter overrides
        construction with a real bpy mesh."""
        vertices, edges = _segments_to_vertices_edges(segments)
        obj = _MeshObject(name, vertices, edges)
        obj.users_collection = (collection,)
        collection.objects.append(obj)
        self.objects.append(obj)
        return obj

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
