import unittest

from gateway_to_caen.neural import TacticalBrain
from gateway_to_caen.simulation import MAP_HEIGHT, MAP_WIDTH, BattleSimulation, Obstacle


class ObstacleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sim = BattleSimulation(TacticalBrain(seed=31), seed=3101, player_side="Allied")
        self.sim.terrain = [["open" for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]

    def test_generated_obstacles_round_trip(self) -> None:
        self.assertGreaterEqual(len(self.sim.obstacles), 20)
        payload = self.sim.to_dict()
        restored = BattleSimulation(TacticalBrain(seed=32), seed=1)
        restored.load_dict(payload)
        self.assertEqual(len(restored.obstacles), len(self.sim.obstacles))
        self.assertEqual(restored.obstacles[0].kind, self.sim.obstacles[0].kind)

    def test_order_inside_obstacle_is_shifted_clear(self) -> None:
        unit = self.sim.living_units("Allied")[0]
        obstacle = Obstacle("test", "bunker", 8.0, 8.0, 0.55, blocks_movement=True, blocks_los=True)
        self.sim.obstacles = [obstacle]
        self.sim.issue_order([unit.uid], "Advance", obstacle.x, obstacle.y)
        assert unit.target_x is not None and unit.target_y is not None
        self.assertIsNone(
            self.sim.colliding_obstacle(
                unit.target_x,
                unit.target_y,
                self.sim.unit_collision_radius(unit),
            )
        )

    def test_unit_steers_without_clipping_through_obstacle(self) -> None:
        unit = self.sim.living_units("Allied")[0]
        unit.x, unit.y = 3.0, 8.0
        obstacle = Obstacle("test", "bunker", 5.2, 8.0, 0.58, blocks_movement=True, blocks_los=True)
        self.sim.obstacles = [obstacle]
        self.sim.issue_order([unit.uid], "Advance", 8.5, 8.0)
        minimum = obstacle.radius + self.sim.unit_collision_radius(unit)
        maximum_diversion = 0.0
        for _ in range(260):
            self.sim._move_units(0.05)
            maximum_diversion = max(maximum_diversion, abs(unit.y - 8.0))
            self.assertGreaterEqual(self.sim.obstacle_distance(unit.x, unit.y, obstacle), minimum - 0.012)
        self.assertGreater(unit.x, 5.6)
        self.assertGreater(maximum_diversion, 0.4)

    def test_solid_obstacle_blocks_direct_line_of_sight(self) -> None:
        attacker = next(unit for unit in self.sim.living_units("Allied") if unit.unit_type == "Rifle")
        target = next(unit for unit in self.sim.living_units("Axis") if unit.unit_type == "Rifle")
        attacker.x, attacker.y = 3.0, 8.0
        target.x, target.y = 9.0, 8.0
        self.sim.obstacles = [Obstacle("test", "bunker", 6.0, 8.0, 0.55, blocks_movement=True, blocks_los=True)]
        self.assertFalse(self.sim.line_of_sight(attacker, target))


if __name__ == "__main__":
    unittest.main()
