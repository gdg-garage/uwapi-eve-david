import os
import random
import signal
from collections import defaultdict
from enum import Enum
from xml.dom.minidom import Entity

import uw
from uw import Prototype

class CombatMode(Enum):
    ATTACK = 1
    DEFEND = 2
    AUTOMATIC = 3

class Bot:
    def __init__(self):
        self.game = uw.Game()
        self.step = 0
        self.main_building = None
        self.resources_map = None
        self.prototypes = None

        self.construction_prototype_name_map = {}
        self.unit_prototype_name_map = {}
        self.construction_prototype_id_map = {}
        self.unit_prototype_id_map = {}
        self.construction_prototypes = None # deprecated
        self.unit_prototypes = None # deprecated

        self.entities = None

        self.building_limits = {
            "concrete plant": 2,
            "factory": 2,
            "laboratory": 1,
            "arsenal": 1,
            "bot assembler": 1,
        }

        self.drill_limits = {
            "metal": 3,
            "crystals": 1,
        }

        self.pump_limits = {
            "oil": 1,
            "aether": 0,
        }
        self.combat_mode = CombatMode.AUTOMATIC

        # register update callback
        self.game.add_update_callback(self.update_callback_closure())

    def find_main_base(self):
        if self.main_building:
            return
        for e in self.game.world.entities().values():
            if not (e.own() and hasattr(e, "Unit")):
                continue
            unit = self.game.prototypes.unit(e.Proto.proto)
            if not unit:
                continue
            if unit.get("name", "") == "nucleus":
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

        for p in self.game.prototypes.all():
            self.prototypes.append({
                "id": p,
                "name": self.game.prototypes.name(p),
                "type": self.game.prototypes.type(p),
            })
        print(self.construction_prototype_name_map)
        print(self.unit_prototype_name_map)
        self.construction_prototypes = list(filter(lambda x: x["type"] == Prototype.Construction, self.prototypes))
        self.unit_prototypes = list(filter(lambda x: x["type"] == Prototype.Unit, self.prototypes))

    def get_closest_ores(self):
        self.resources_map = defaultdict(list)
        for e in self.game.world.entities().values():
            if not (hasattr(e, "Unit")) and not e.own():
                continue
            unit = self.game.prototypes.unit(e.Proto.proto)
            if not unit:
                continue
            if "deposit" not in unit.get("name", ""):
                continue
            name = unit.get("name", "").replace(" deposit", "")
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

        if not self.game.try_reconnect():
            self.game.set_start_gui(True)
            lobby = os.environ.get("UNNATURAL_CONNECT_LOBBY", "")
            # addr = os.environ.get("UNNATURAL_CONNECT_ADDR", "192.168.2.102")
            # port = os.environ.get("UNNATURAL_CONNECT_PORT", 27543)
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

    def find_own_combat_units(self) -> list:
        return [
            e
            for e in self.game.world.entities().values()
            if e.own()
               and e.has("Unit")
               and self.game.prototypes.unit(e.Proto.proto)
               and self.game.prototypes.unit(e.Proto.proto).get("dps", 0) > 0
        ]

    def combat(self):
        if self.combat_mode == CombatMode.ATTACK:
            print("attack")
            self.attack_nearest_enemies()
        elif self.combat_mode == CombatMode.DEFEND:
            print("defend")
            self.go_to_nucleus()
        else:
            print("automatic")
            own_units = self.find_own_combat_units()
            if not own_units:
                return
            if len(own_units) >= 10:
                print("attack")
                self.attack_nearest_enemies()
            else:
                print("defend")
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
            #if len(self.game.commands.orders(_id)) == 0:
            enemy = sorted(
                enemy_units,
                key=lambda x: self.game.map.distance_estimate(
                    pos, x.Position.position
                ),
            )[0]
            self.game.commands.order(
                _id, self.game.commands.fight_to_entity(enemy.Id)
            )

    def go_to_nucleus(self):
        own_units = self.find_own_combat_units()
        if not own_units:
            return
        for u in own_units:
            _id = u.Id
            #if len(self.game.commands.orders(_id)) == 0:
            self.game.commands.order(
                _id, self.game.commands.run_to_entity(self.main_building.Id)
            )

    def assign_random_recipes(self):
        for e in self.game.world.entities().values():
            if not (e.own() and hasattr(e, "Unit")):
                continue
            recipes = self.game.prototypes.unit(e.Proto.proto)
            if not recipes:
                continue
            recipes = recipes["recipes"]
            # Build only juggernauts
            for recipe in recipes:
                if self.game.prototypes.name(recipe) == "juggernaut":
                    self.game.commands.command_set_recipe(e.Id, recipe)
                    break

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
        for c in self.construction_prototypes:
            if c["name"] == construction_name:
                # if self.game.map.test_construction_placement(c["id"], position):
                self.game.commands.command_place_construction(
                    c["id"],
                    self.game.map.find_construction_placement(c["id"], position))
                return True
        return False

    def maybe_build_concrete_plant(self, position: int) -> bool:
        building_name = "concrete plant"
        plants = self.find_own_units_and_constructions_of_name(building_name)
        if len(plants) >= self.building_limits[building_name]:
            return False

        print("building concrete plant")
        return self.find_placement_and_build_construction(building_name, position)

    def neighbouring_deposit(self, resource: str, position: int):
        for res in self.resources_map.get(resource, []):
            for neighbor in self.game.map.neighbors_of_position(position):
                if res.Position.position == neighbor:
                    return res

    def find_drills_with_resource_type(self, resource_type: str) -> list[Entity]:
        drills = self.find_own_units_and_constructions_of_name("drill")
        return list(filter(lambda x: self.neighbouring_deposit(resource_type, x.Position.position), drills))

    def find_pumps_with_resource_type(self, resource_type: str) -> list[Entity]:
        drills = self.find_own_units_and_constructions_of_name("pump")
        return list(filter(lambda x: self.neighbouring_deposit(resource_type, x.Position.position), drills))


    def maybe_build_drill(self, resource_type: str):
        drills = self.find_drills_with_resource_type(resource_type)
        if len(drills) >= self.drill_limits[resource_type]:
            return False

        # TODO Check if we have iron insufficiency
        if self.resources_map is None:
            return
        closest_deposits : list = self.resources_map.get(resource_type, [])
        # TODO check if enough reinforced concrete

        for d in closest_deposits:
            if self.find_placement_and_build_construction("drill", d.Position.position):
                break

    def maybe_set_recipe(self, building_name: str, recipe_name: str):
        # buildings = self.find_own_units_with_name(building_name)
        # for b in buildings:
        pass


    def maybe_build(self, building_name: str, position: int = -1):
        if position == -1:
            return False
        buildings = self.find_own_units_and_constructions_of_name(building_name)
        if len(buildings) >= self.building_limits.get(building_name, 0):
            return False

        print("position", position)
        return self.find_placement_and_build_construction(building_name, position)

    def maybe_build_pump(self, resource_type: str):
        pumps = self.find_pumps_with_resource_type(resource_type)
        if len(pumps) >= self.pump_limits.get(resource_type, 0):
            return False

        closest_deposits: list = self.resources_map.get(resource_type, [])
        for d in closest_deposits:
            if self.find_placement_and_build_construction("pump", d.Position.position):
                return True

    def position_in_distance_from(self, from_pos: int, radius: int):
        self.game.map.area_neighborhood(from_pos, radius)

    def neighboring_position_to_building(self, building_name: str, resource_name: str = "") -> int:
        buildings = self.find_own_units_and_constructions_of_name(building_name)
        if resource_name != "":
            # TODO handle pumps and drills
            pass
        for b in buildings:
            return b.Position.position
        return -1

    def execute_juggernaut_strategy(self):
        # Bot assembler connected to Laboratory with shield projector
        self.assign_recipe("juggernaut")
        self.maybe_build("bot assembler", self.neighboring_position_to_building("laboratory"))
        # Arsenal with plasma emitter
        self.assign_recipe("plasma emitter")
        self.maybe_build("arsenal", self.neighboring_position_to_building("drill"))
        # Oil pump
        self.maybe_build_pump("oil")
        # Laboratory with shield projector
        self.assign_recipe("shield projector")
        self.maybe_build("laboratory", self.neighboring_position_to_building("drill", "crystals"))
        # Crystals drill
        self.maybe_build_drill("crystals")
        # Reinforced concrete
        self.maybe_build_reinforced_concrete()
        # Iron drill
        self.maybe_build_drill("metal")


    def maybe_build_factory(self):
        building_name = "factory"
        factories = self.find_own_units_and_constructions_of_name(building_name)
        if len(factories) >= self.building_limits.get(building_name, 0):
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

    def update_callback_closure(self):
        def update_callback(stepping):
            if not stepping:
                return
            self.step += 1  # save some cpu cycles by splitting work over multiple steps

            self.find_main_base()
            self.init_prototypes()

            # self.assign_random_recipes()

            if self.resources_map is None:
                self.get_closest_ores()
                print("====== closest ores ======")
                print(self.resources_map)

            if self.step % 10 == 1:
                self.combat()

            # print(self.iron_cnt)
            if self.step % 10 == 5:
                # self.execute_juggernaut_strategy()
                self.execute_kitsune_strategy()

            # self.maybe_build_iron_drill()

            # if self.step % 10 == 5:
            #     self.assign_random_recipes()

        return update_callback


if __name__ == "__main__":
    bot = Bot()
    bot.start()
