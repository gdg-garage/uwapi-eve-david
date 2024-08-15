import os
import random
from collections import defaultdict
from xml.dom.minidom import Entity

import uw
from uw import Prototype


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

        self.iron_position = None
        self.iron_cnt = 0
        self.concrete_cnt = 0
        self.entities = None

        self.building_limits = {
            "drill": 3,
            "concrete plant": 2,
            "factory": 1,
        }

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
        self.game.log_info("done")

    def attack_nearest_enemies(self):
        own_units = [
            e
            for e in self.game.world.entities().values()
            if e.own()
               and e.has("Unit")
               and self.game.prototypes.unit(e.Proto.proto)
               and self.game.prototypes.unit(e.Proto.proto).get("dps", 0) > 0
        ]
        if not own_units:
            return

        # Don't attack until attack group of 10 is ready
        if len(own_units) < 10:
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
            if len(self.game.commands.orders(_id)) == 0:
                enemy = sorted(
                    enemy_units,
                    key=lambda x: self.game.map.distance_estimate(
                        pos, x.Position.position
                    ),
                )[0]
                self.game.commands.order(
                    _id, self.game.commands.fight_to_entity(enemy.Id)
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

    def find_own_units_and_constructions_of_name(self, name: str):
        constructions = self.find_own_constructions()
        units = self.find_own_units()
        print("constr", len(constructions))
        print("units", len(units))
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

    def maybe_build_iron_drill(self):
        drills = self.find_own_units_and_constructions_of_name("drill")
        if len(drills) >= self.building_limits["drill"]:
            return False

        # TODO Check if we have iron insufficiency
        if self.resources_map is None:
            return
        closest_metal_deposits : list = self.resources_map.get("metal", [])
        # TODO check if enough reinforced concrete

        for d in closest_metal_deposits:
            if self.find_placement_and_build_construction("drill", d.Position.position):
                self.iron_cnt += 1
                self.iron_position = d.Position.position
                break

    def juggernaut_strategy(self):
        # Bot assembler connected to Laboratory with shield projector
        # Arsenal with plasma emitter
        # Oil pump
        # Laboratory with shield projector
        # Crystals drill
        # Reinforced concrete
        # Iron drill
        self.maybe_build_iron_drill()


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

        if not self.iron_position:
            return
        print("printing own constructions")
        construction_entities = self.find_own_constructions()
        if len(construction_entities) > 0:
            self.maybe_build_concrete_plant(construction_entities[0].Position.position)
        # self.find_placement_and_build_construction(
        #     "factory", self.iron_position)
        # self.assign_recipe("kitsune")

    def kitsune_strategy(self):
        # Iron drill
        self.maybe_build_iron_drill()
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

            self.assign_random_recipes()

            if self.resources_map is None:
                self.get_closest_ores()
                print("====== closest ores ======")
                print(self.resources_map)

            if self.step % 10 == 1:
                self.attack_nearest_enemies()

            # print(self.iron_cnt)
            # self.juggernaut_strategy()

            self.kitsune_strategy()

            # self.maybe_build_iron_drill()

            if self.step % 10 == 5:
                self.assign_random_recipes()

        return update_callback


if __name__ == "__main__":
    bot = Bot()
    bot.start()
