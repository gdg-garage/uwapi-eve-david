import os
import random
from collections import defaultdict

import uw
from uw import Prototype


class Bot:
    def __init__(self):
        self.game = uw.Game()
        self.step = 0
        self.main_building = None
        self.resources_map = None
        self.prototypes = None
        self.constructions = None

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
        for p in self.game.prototypes.all():
            self.prototypes.append({
                "id": p,
                "name": self.game.prototypes.name(p),
                "type": self.game.prototypes.type(p),
            })
        self.constructions = list(filter(lambda x: x["type"] == Prototype.Construction, self.prototypes))
        print("=======")
        print(self.constructions)

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
            sorted(self.resources_map[r], key=lambda x: self.game.map.distance_estimate(
                        self.main_building.Position.position, x.Position.position
                    ))

    def start(self):
        self.game.log_info("starting")
        self.game.set_player_name("eve-david")

        if not self.game.try_reconnect():
            self.game.set_start_gui(True)
            lobby = os.environ.get("UNNATURAL_CONNECT_LOBBY", "")
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


    def build_drill(self, deposit: uw.world.Entity):
        print("hello")
        for c in self.constructions:
            print(c["name"])
            if c["name"] == "drill":
                self.game.commands.command_place_construction(c["id"], deposit.Position.position)

    def maybe_build_iron_drill(self):
        if self.resources_map is None:
            return
        closest_metal_deposits : list = self.resources_map.get("metal", [])
        # check if enough reinforced concrete
        if len(closest_metal_deposits) > 0:
            self.build_drill(closest_metal_deposits[0])
        pass

    def update_callback_closure(self):
        def update_callback(stepping):
            if not stepping:
                return
            self.step += 1  # save some cpu cycles by splitting work over multiple steps

            self.init_prototypes()

            if self.resources_map is None:
                self.get_closest_ores()
                print("====== closest ores ======")
                print(self.resources_map)

            if self.step % 10 == 1:
                self.attack_nearest_enemies()

            self.maybe_build_iron_drill()

            if self.step % 10 == 5:
                self.assign_random_recipes()

        return update_callback


if __name__ == "__main__":
    bot = Bot()
    bot.start()
