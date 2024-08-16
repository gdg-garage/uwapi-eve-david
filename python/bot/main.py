import json
import os
import random
import signal
import sys
from collections import defaultdict
from enum import Enum
from xml.dom.minidom import Entity

import uw
from uw import Prototype

class CombatMode(Enum):
    ATTACK = "attack"
    DEFEND = "defend"
    AUTOMATIC = "automatic"

class Bot:
    def __init__(self):
        self.cwd = os.getcwd()

        self.game = uw.Game()
        self.step = 0
        self.main_building = None
        self.resources_map = None
        self.prototypes = None
        self.resources = None

        self.construction_prototype_name_map = {}
        self.unit_prototype_name_map = {}
        self.resource_prototype_name_map = {}
        self.construction_prototype_id_map = {}
        self.unit_prototype_id_map = {}
        self.resource_prototype_id_map = {}

        self.construction_prototypes = None # deprecated
        self.unit_prototypes = None # deprecated
        self.entities = None
        self.last_commands = {}
        self.config = {}

        # register update callback
        self.game.add_update_callback(self.update_callback_closure())

    def get_unit_name(self, unit) -> str:
        u = self.game.prototypes.unit(unit.Proto.proto)
        if u is None:
            return ""
        return u.get("name", "")

    def find_main_base(self):
        if self.main_building:
            return
        for e in self.game.world.entities().values():
            if not (e.own() and hasattr(e, "Unit")):
                continue
            if self.get_unit_name(e) == "nucleus":
                self.main_building = e

    def init_prototypes(self):
        if self.prototypes:
            return
        self.prototypes = []
        self.construction_prototype_name_map = {}
        self.unit_prototype_name_map = {}
        for p in self.game.prototypes.all():
            if self.game.prototypes.type(p) == Prototype.Construction:
                self.construction_prototype_name_map[self.game.prototypes.name(p)] = p
                self.construction_prototype_id_map[p] = self.game.prototypes.name(p)
            if self.game.prototypes.type(p) == Prototype.Unit:
                self.unit_prototype_name_map[self.game.prototypes.name(p)] = p,
                self.unit_prototype_id_map[p] = self.game.prototypes.name(p)
            if self.game.prototypes.type(p) == Prototype.Resource:
                self.resource_prototype_name_map[self.game.prototypes.name(p)] = p,
                self.resource_prototype_id_map[p] = self.game.prototypes.name(p)

        for p in self.game.prototypes.all():
            self.prototypes.append({
                "id": p,
                "name": self.game.prototypes.name(p),
                "type": self.game.prototypes.type(p),
            })
        self.construction_prototypes = list(filter(lambda x: x["type"] == Prototype.Construction, self.prototypes))
        self.unit_prototypes = list(filter(lambda x: x["type"] == Prototype.Unit, self.prototypes))

    def get_closest_ores(self):
        self.resources_map = defaultdict(list)
        for e in self.game.world.entities().values():
            if not (hasattr(e, "Unit")) and not e.own():
                continue
            unit_name = self.get_unit_name(e)
            if "deposit" not in unit_name:
                continue
            name = unit_name.replace(" deposit", "")
            self.resources_map[name].append(e)

        if not self.main_building:
            return
        for r in self.resources_map:
            self.resources_map[r].sort(key=lambda x: self.game.map.distance_estimate(
                self.main_building.Position.position, x.Position.position
            ))

    def start(self):
        self.game.log_info("starting")
        self.game.set_player_name("eve-david")
        pid = os.getpid()
        self.load_config()

        if not self.game.try_reconnect():
            self.game.set_start_gui(True)
            lobby = os.environ.get("UNNATURAL_CONNECT_LOBBY", "")
            # addr = os.environ.get("UNNATURAL_CONNECT_ADDR", "192.168.2.102")
            # port = os.environ.get("UNNATURAL_CONNECT_PORT", 45528)
            addr = os.environ.get("UNNATURAL_CONNECT_ADDR", "")
            port = os.environ.get("UNNATURAL_CONNECT_PORT", "")
            if lobby != "":
                self.game.connect_lobby_id(lobby)
            elif addr != "" and port != "":
                self.game.connect_direct(addr, port)
            else:
                self.game.connect_new_server(extra_params="-m planets/triangularprism.uw")

        os.kill(pid, signal.SIGTERM)
        self.game.log_info("done")

    def get_resources(self):
        if self.resources:
            return
        self.resources = defaultdict(int)
        for e in self.game.world.entities().values():
            if not e.own():
                continue
            if e.Proto.proto in self.resource_prototype_id_map:
                self.resources[self.resource_prototype_id_map[e.Proto.proto]] += e.Amount.amount

    def find_own_combat_units(self) -> list:
        return [
            e
            for e in self.game.world.entities().values()
            if e.own()
               and e.has("Unit")
               and self.game.prototypes.unit(e.Proto.proto)
               and self.get_unit_name(e) != "nucleus"
               and self.game.prototypes.unit(e.Proto.proto).get("dps", 0) > 0
        ]

    def combat(self):
        if self.config["combat_mode"] == str(CombatMode.ATTACK.value):
            self.attack_nearest_enemies()
        elif self.config["combat_mode"] == str(CombatMode.DEFEND.value):
            self.go_to_nucleus()
        else:
            own_units = self.find_own_combat_units()
            if not own_units:
                return
            if len(own_units) >= 10:
                self.attack_nearest_enemies()
            else:
                self.go_to_nucleus()

    def attack_nearest_enemies(self):
        own_units = self.find_own_combat_units()
        if not own_units:
            return
        enemy_units = [
            e
            for e in self.game.world.entities().values()
            if e.policy() == uw.Policy.Enemy and e.has("Unit")
        ]
        if not enemy_units:
            return
        for u in own_units:
            _id = u.Id
            pos = u.Position.position
            if (_id in self.last_commands and self.last_commands[_id] == CombatMode.DEFEND) or len(self.game.commands.orders(_id)) == 0:
                enemy = sorted(
                    enemy_units,
                    key=lambda x: self.game.map.distance_estimate(
                        pos, x.Position.position
                    ),
                )[0]
                self.game.commands.order(
                    _id, self.game.commands.fight_to_entity(enemy.Id)
                )
                print("Unit "+self.get_unit_name(u)+" is attacking")
                self.last_commands[_id] = CombatMode.ATTACK

    def go_to_nucleus(self):
        own_units = self.find_own_combat_units()
        if not own_units:
            return
        for u in own_units:
            _id = u.Id
            if (_id in self.last_commands and self.last_commands[_id] == CombatMode.ATTACK) or len(self.game.commands.orders(_id)) == 0:
                self.game.commands.order(
                    _id, self.game.commands.run_to_entity(self.main_building.Id)
                )
                print("Unit " + self.get_unit_name(u) + " is defending")
                self.last_commands[_id] = CombatMode.DEFEND

    def assign_recipe(self, recipe_name: str):
        for e in self.game.world.entities().values():
            if not (e.own() and hasattr(e, "Unit")):
                continue
            recipes = self.game.prototypes.unit(e.Proto.proto)
            if not recipes:
                continue
            recipes = recipes["recipes"]
            for recipe in recipes:
                if self.game.prototypes.name(recipe) == recipe_name:
                    self.game.commands.command_set_recipe(e.Id, recipe)
                    break

    def find_own_constructions(self) -> list: # list of entities
        construction_entities = []
        for e in self.game.world.entities().values():
            if not e.own():
                continue
            if e.Proto.proto in self.construction_prototype_id_map:
                construction_entities.append(e)
        return construction_entities

    def find_own_units(self) -> list: # list of entities
        unit_entities = []
        for e in self.game.world.entities().values():
            if not e.own():
                continue
            if e.Proto.proto in self.unit_prototype_id_map:
                unit_entities.append(e)
        return unit_entities


    def find_own_units_with_name(self, building_name: str) -> list[Entity]:
        return list(filter(lambda x: self.unit_prototype_id_map[x.Proto.proto] == building_name, self.find_own_units()))

    def find_own_units_and_constructions_of_name(self, name: str):
        constructions = self.find_own_constructions()
        units = self.find_own_units()
        filtered_c = list(filter(lambda x: self.construction_prototype_id_map[x.Proto.proto] == name, constructions))
        filtered_u = list(filter(lambda x: self.unit_prototype_id_map[x.Proto.proto] == name, units))
        return filtered_c + filtered_u

    def find_placement_and_build_construction(self, construction_name: str, position: int) -> bool:
        if self.anything_in_construction():
            return False
        for c in self.construction_prototypes:
            if c["name"] == construction_name:
                # if self.game.map.test_construction_placement(c["id"], position):
                self.game.commands.command_place_construction(
                    c["id"],
                    self.game.map.find_construction_placement(self.construction_prototype_name_map["experimental assembler"], position))
                # self.game.commands.command_place_construction(
                #     c["id"],
                #     self.game.map.find_construction_placement(c["id"], position))
                return True
        return False

    def build_construction(self, construction_name: str, position: int) -> bool:
        if self.anything_in_construction():
            return False

        for c in self.construction_prototypes:
            if c["name"] == construction_name:
                if self.game.map.test_construction_placement(c["id"], position):
                    self.game.commands.command_place_construction(
                        c["id"],position)
                    return True
        return False

    def maybe_build_concrete_plant(self, position: int) -> bool:
        building_name = "concrete plant"
        plants = self.find_own_units_and_constructions_of_name(building_name)
        if len(plants) >= self.config["building_limits"][building_name]:
            return False
        return self.find_placement_and_build_construction(building_name, position)

    def neighbouring_deposit(self, resource: str, position: int):
        for res in self.resources_map.get(resource, []):
            if position == res.Position.position:
                return res
            for neighbor in self.game.map.neighbors_of_position(position):
                if res.Position.position == neighbor:
                    # print(json.dumps(res.__dict__))
                    return res

    def find_drills_with_resource_type(self, resource_type: str) -> list[Entity]:
        drills = self.find_own_units_and_constructions_of_name("drill")
        return list(filter(lambda x: self.neighbouring_deposit(resource_type, x.Position.position), drills))

    def find_pumps_with_resource_type(self, resource_type: str) -> list[Entity]:
        pumps = self.find_own_units_and_constructions_of_name("pump")
        return list(filter(lambda x: self.neighbouring_deposit(resource_type, x.Position.position), pumps))


    def maybe_build_drill(self, resource_type: str):
        drills = self.find_drills_with_resource_type(resource_type)
        if len(drills) >= self.config["drill_limits"][resource_type]:
            return False

        # TODO Check if we have iron insufficiency
        if self.resources_map is None:
            return
        closest_deposits : list = self.resources_map.get(resource_type, [])
        # TODO check if enough reinforced concrete

        for d in closest_deposits:
            print("trying to build " + resource_type + " drill", d)
            if self.build_construction("drill", d.Position.position):
                print("success")
                break
            print("not success")

    def maybe_set_recipe(self, building_name: str, recipe_name: str):
        # buildings = self.find_own_units_with_name(building_name)
        # for b in buildings:
        pass


    def maybe_build(self, building_name: str, position: int = -1):
        if position == -1:
            return False
        buildings = self.find_own_units_and_constructions_of_name(building_name)
        if len(buildings) >= self.config["building_limits"].get(building_name, 0):
            return False
        return self.find_placement_and_build_construction(building_name, position)

    def maybe_build_pump(self, resource_type: str):
        # Conditions - There are already metal drills and concrete plants
        pumps = self.find_pumps_with_resource_type(resource_type)
        if len(pumps) >= self.config["pump_limits"].get(resource_type, 0):
            return False

        closest_deposits: list = self.resources_map.get(resource_type, [])
        for d in closest_deposits:
            if self.build_construction("pump", d.Position.position):
                return True
        return False

    def maybe_build_oil_pump(self):
        self.find_own_units_with_name("drill")
        # TODO filter only metal drills
        self.get_resources()
        return self.maybe_build_pump("oil")

    def maybe_build_laboratory(self):
        self.get_resources()
        return self.maybe_build(
            "laboratory",
            self.neighboring_position_to_building("drill", "crystals", True))

    def maybe_build_arsenal(self):
        self.get_resources()
        return self.maybe_build(
            "arsenal",
            self.neighboring_position_to_building("drill", "metal"))

    def maybe_build_smelter(self):
        if not self.find_own_units_with_name("generator"):
            return False
        self.maybe_build("smelter", self.neighboring_position_to_building("drill", "metal"))

    def maybe_build_bot_assembler(self):
        self.get_resources()
        return self.maybe_build("bot assembler", self.neighboring_position_to_building("laboratory"))

    def position_in_distance_from(self, from_pos: int, radius: int):
        self.game.map.area_neighborhood(from_pos, radius)

    def find_units_or_constructions_on_position(self, position) -> list:
        result = []
        for n in self.game.map.neighbors_of_position(position):
            for c in self.find_own_constructions():
                if c.Position.position == n:
                    result.append(c)
            for u in self.find_own_units():
                if u.Position.position == n:
                    result.append(u)
        return result

    def building_on_deposit(self, building: Entity, resource_type: str) -> bool:
        for res in self.resources_map.get(resource_type, []):
            if res.Position.position == building.Position.position:
                return True
        return False

    def neighboring_position_to_building(self, building_name: str, resource_name: str = "", prefer_empty: bool = False) -> int:
        buildings = self.find_own_units_and_constructions_of_name(building_name)
        if resource_name != "":
            # TODO handle pumps and drills
            x = len(buildings)
            buildings = list(filter(lambda x: self.building_on_deposit(x, resource_name), buildings))
            print("filtered buildings " + str(len(buildings)) + " out of " + str(x))
        # if prefer_empty:
        #     for b in sorted(buildings, key=lambda x: len(self.find_units_or_constructions_on_position(x.Position.position))):
        #         return b.Position.position
        for b in buildings:
            return b.Position.position
        return -1

    def anything_in_construction(self):
        print("in construction", len(self.find_own_constructions()))
        return len(self.find_own_constructions()) > 0

    def execute_juggernaut_strategy(self):
        # Iron drill
        self.maybe_build_drill("metal")
        # Reinforced concrete
        if self.maybe_build(
            "concrete plant",
            self.neighboring_position_to_building("drill", "metal")):
            return
        # Crystals drill
        self.maybe_build_drill("crystals")
        # Laboratory with shield projector
        self.assign_recipe("shield projector")
        if self.maybe_build_laboratory():
            return
        # Oil pump
        if self.maybe_build_oil_pump():
            return
        # Arsenal with plasma emitter
        self.assign_recipe("plasma emitter")
        if self.maybe_build_arsenal():
            return
        # Bot assembler connected to Laboratory with shield projector
        self.assign_recipe("juggernaut")
        self.maybe_build("bot assembler", self.neighboring_position_to_building("laboratory"))

    def execute_eagle_strategy(self):
        # Iron drill
        self.maybe_build_drill("metal")
        # Reinforced concrete
        if self.maybe_build(
            "concrete plant",
            self.neighboring_position_to_building("drill", "metal")):
            return
        # Oil pump
        if self.maybe_build_oil_pump():
            return
        self.maybe_build("forgepress", self.neighboring_position_to_building("nucleus"))
        self.assign_recipe("armor plates")
        self.maybe_build_smelter()
        self.maybe_build("generator", self.neighboring_position_to_building("drill", "metal"))
        self.maybe_build("factory", self.neighboring_position_to_building("drill", "metal"))
        self.assign_recipe("eagle")

    def maybe_build_factory(self):
        building_name = "factory"
        factories = self.find_own_units_and_constructions_of_name(building_name)
        if len(factories) >= self.config["building_limits"].get(building_name, 0):
            return False

        drills = self.find_own_units_and_constructions_of_name("drill")
        if len(drills) == 0:
            return False

        for d in drills:
            self.find_placement_and_build_construction(building_name, d.Position.position)

    def maybe_build_reinforced_concrete(self):
        # TODO check whether concrete is needed
        # TODO find suitable iron drill
        if len(self.find_own_units_and_constructions_of_name("drill")) == 0:
            return
        construction_entities = self.find_own_constructions()
        if len(construction_entities) > 0:
            self.maybe_build_concrete_plant(construction_entities[0].Position.position)

    def execute_kitsune_strategy(self):
        # Iron drill
        self.maybe_build_drill("metal")
        # Reinforced concrete
        self.maybe_build_reinforced_concrete()
        # Factory with kitsune
        self.maybe_build_factory()
        self.assign_recipe("kitsune")

    def load_config(self):
        path = sys.argv[0].replace("main.py", "config.json")
        file = open(os.path.join(self.cwd, path), 'r')
        new_config = json.load(file)
        if new_config != self.config:
            self.config = new_config
            print("New config loaded")


    def update_callback_closure(self):
        def update_callback(stepping):
            if not stepping:
                return
            self.step += 1  # save some cpu cycles by splitting work over multiple steps

            self.find_main_base()
            self.init_prototypes()

            self.resources = None

            if self.step % 20 == 1:
                self.load_config()

            if self.resources_map is None:
                self.get_closest_ores()

            if self.step % 10 == 1:
                self.combat()

            # print(self.iron_cnt)
            if self.step % 10 == 5:
                self.execute_eagle_strategy()
                # self.execute_juggernaut_strategy()
                # self.execute_kitsune_strategy()

            # self.maybe_build_iron_drill()

        return update_callback


if __name__ == "__main__":
    bot = Bot()
    bot.start()
