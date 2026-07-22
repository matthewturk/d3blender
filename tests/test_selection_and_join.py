from d3blender import select
from d3blender.mock import MockObject


def names(sel):
    return sorted(el.name for el in sel)


def test_scoped_select_collection_axis(scene):
    weapons_sel = select(scene, '#Weapons')
    assert names(weapons_sel.select('.enemy')) == ['Shield', 'Sword']


def test_scoped_select_parent_axis(scene):
    rig_sel = select(scene, '#Rig')
    assert names(rig_sel.select('mesh', axis='parent')) == ['Sword_Held']


def test_attr_mutation_persists(scene):
    select(scene, '.enemy').attr('hp', lambda el, i: scene.get_attr(el, 'hp') + 5)
    sword = select(scene, '#Sword').elements[0]
    shield = select(scene, '#Shield').elements[0]
    assert sword.get('hp') == 35
    assert shield.get('hp') == 45


def test_join_enter_update_exit_is_rerun_safe(scene):
    props = next(c for c in scene.collections if c.name == 'Props')

    def make_crate(d):
        o = MockObject(f"Crate.{d['id']}", 'MESH')
        props.objects.append(o)
        o.users_collection = (props,)
        scene.objects.append(o)
        return o

    events = []

    def update_crate(el, d):
        events.append(('update', el.name, d['x']))

    def remove_crate(el):
        events.append(('exit', el.name))
        scene.remove(el)

    def crates():
        return select(scene, '#Props mesh').filter(lambda el: el.name.startswith('Crate'))

    first = [{'id': 0, 'x': 0}, {'id': 1, 'x': 2}, {'id': 2, 'x': 4}]
    crates().data(first, key=lambda i, d: f"crate-{d['id']}").join(
        enter=make_crate, update=update_crate, exit=remove_crate)
    assert names(crates()) == ['Crate.0', 'Crate.1', 'Crate.2']

    second = [{'id': 0, 'x': 10}, {'id': 2, 'x': 40}]  # id 1 dropped
    crates().data(second, key=lambda i, d: f"crate-{d['id']}").join(
        enter=make_crate, update=update_crate, exit=remove_crate)

    assert names(crates()) == ['Crate.0', 'Crate.2']
    assert ('exit', 'Crate.1') in events
    assert ('update', 'Crate.0', 10) in events
    assert ('update', 'Crate.2', 40) in events
    # Crate.1 was removed, not re-entered or updated:
    assert not any(name == 'Crate.1' and kind == 'update' for kind, name, *_ in events)
