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

    def test_round_trip_save(self) -> None:
        brain = TacticalBrain(seed=5)
        sim = BattleSimulation(brain, seed=123)
        sim.tick(0.2)
        payload = sim.to_dict()
        restored = BattleSimulation(brain, seed=456)
        restored.load_dict(payload)
        self.assertEqual(restored.seed, sim.seed)
        self.assertEqual(len(restored.units), len(sim.units))
        self.assertEqual(restored.operation_name, sim.operation_name)


if __name__ == "__main__":
    unittest.main()
