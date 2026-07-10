import unittest

from gateway_to_caen.neural import TacticalBrain
from gateway_to_caen.simulation import MAP_HEIGHT, MAP_WIDTH, BattleSimulation


class SimulationTests(unittest.TestCase):
    def test_new_battle_and_ai_learning(self) -> None:
        brain = TacticalBrain(seed=4, epsilon=0.0)
        sim = BattleSimulation(brain, seed=99)
        self.assertEqual(len(sim.terrain), MAP_HEIGHT)
        self.assertEqual(len(sim.terrain[0]), MAP_WIDTH)
        self.assertEqual(len(sim.living_units("Allied")), 6)
        self.assertEqual(len(sim.living_units("Axis")), 6)
        for _ in range(50):
            sim.tick(0.1)
        self.assertGreater(brain.stats.decisions, 0)
        self.assertGreaterEqual(brain.stats.training_steps, 0)

    def test_round_trip_save_preserves_side_and_fog(self) -> None:
        brain = TacticalBrain(seed=5)
        sim = BattleSimulation(brain, seed=123, player_side="Axis")
        sim.tick(0.2)
        payload = sim.to_dict()
        restored = BattleSimulation(brain, seed=456)
        restored.load_dict(payload)
        self.assertEqual(restored.seed, sim.seed)
        self.assertEqual(len(restored.units), len(sim.units))
        self.assertEqual(restored.operation_name, sim.operation_name)
        self.assertEqual(restored.player_side, "Axis")
        self.assertTrue(restored.explored_tiles["Axis"])

    def test_orders_only_apply_to_player_side(self) -> None:
        brain = TacticalBrain(seed=8)
        sim = BattleSimulation(brain, seed=44, player_side="Axis")
        allied = sim.living_units("Allied")[0]
        axis = sim.living_units("Axis")[0]
        sim.issue_order([allied.uid, axis.uid], "Advance", 12.0, 8.0)
        self.assertEqual(allied.order, "Hold")
        self.assertEqual(axis.order, "Advance")
        self.assertEqual(axis.target_x, 12.0)

    def test_movement_uses_velocity_and_is_continuous(self) -> None:
        brain = TacticalBrain(seed=9)
        sim = BattleSimulation(brain, seed=55, player_side="Allied")
        unit = sim.living_units("Allied")[0]
        start = (unit.x, unit.y)
        sim.issue_order([unit.uid], "Advance", 10.0, unit.y)
        sim.tick(0.05)
        first_position = (unit.x, unit.y)
        first_speed = unit.speed
        sim.tick(0.05)
        self.assertNotEqual(start, first_position)
        self.assertGreater(first_speed, 0.0)
        self.assertGreater(unit.x, first_position[0])
        self.assertGreaterEqual(unit.speed, first_speed)

    def test_fog_of_war_reveals_nearby_enemy(self) -> None:
        brain = TacticalBrain(seed=10)
        sim = BattleSimulation(brain, seed=66, player_side="Allied")
        scout = next(unit for unit in sim.living_units("Allied") if unit.unit_type == "Scout")
        enemy = sim.living_units("Axis")[0]
        self.assertNotIn(enemy, sim.visible_enemy_units("Allied"))
        scout.x, scout.y = enemy.x - 1.0, enemy.y
        sim.visibility_accumulator = 1.0
        sim.tick(0.01)
        self.assertIn(enemy, sim.visible_enemy_units("Allied"))

    def test_battle_rotates_to_new_map_after_ten_seconds(self) -> None:
        brain = TacticalBrain(seed=11)
        sim = BattleSimulation(brain, seed=77)
        original_seed = sim.seed
        sim.force_result("Allied")
        self.assertTrue(sim.battle_over)
        self.assertFalse(sim.advance_post_battle(9.9))
        self.assertTrue(sim.advance_post_battle(0.2))
        self.assertFalse(sim.battle_over)
        self.assertNotEqual(sim.seed, original_seed)
        self.assertEqual(len(sim.living_units("Allied")), 6)
        self.assertEqual(len(sim.living_units("Axis")), 6)


if __name__ == "__main__":
    unittest.main()
