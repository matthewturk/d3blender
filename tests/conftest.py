import pytest

from d3blender.mock import MockObject, MockCollection, MockModifier
from d3blender.adapter import SceneAdapter


@pytest.fixture
def scene():
    """
    Weapons (collection)
      Sword       .enemy  [hp=30]  (BEVEL modifier)
      Shield      .enemy  [hp=40]
    Characters (collection)
      Rig (ARMATURE)
        - Hand (child, parent=Rig)
            - Sword_Held (child of Hand)  [hp=100]
        - Head (child, parent=Rig)  hidden
    Props (collection, nested inside Characters)
      Barrel  [hp=20]
    """
    weapons = MockCollection('Weapons')
    characters = MockCollection('Characters')
    props = MockCollection('Props')
    characters.children.append(props)

    sword = MockObject('Sword', 'MESH', d3_class='enemy', hp=30)
    shield = MockObject('Shield', 'MESH', d3_class='enemy', hp=40)
    sword.modifiers.append(MockModifier('BEVEL'))
    weapons.objects += [sword, shield]

    rig = MockObject('Rig', 'ARMATURE')
    hand = MockObject('Hand', 'EMPTY', parent=rig)
    sword_held = MockObject('Sword_Held', 'MESH', parent=hand, hp=100)
    head = MockObject('Head', 'EMPTY', parent=rig)
    head.hidden = True
    characters.objects += [rig, hand, sword_held, head]

    barrel = MockObject('Barrel', 'MESH', hp=20)
    props.objects.append(barrel)

    for obj, coll in [(sword, weapons), (shield, weapons), (rig, characters),
                      (hand, characters), (sword_held, characters),
                      (head, characters), (barrel, props)]:
        obj.users_collection = (coll,)

    adapter = SceneAdapter(
        objects=[sword, shield, rig, hand, sword_held, head, barrel],
        collections=[weapons, characters, props],
    )
    return adapter
