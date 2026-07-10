import tempfile
import unittest
from pathlib import Path

from gateway_to_caen.campaign_simulation import CampaignBattleSimulation
from gateway_to_caen.neural import TacticalBrain


class SmartEnemyAITests(unittest.TestCase):
    def test_enemy_is_conventional_and_player_gets_no_direct_auto_orders(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            brain = TacticalBrain(seed=201, epsilon=0.0)
            sim = CampaignBattleSimulation(brain, seed=2201, campaign_path=Path(folder) / "campaign.json")
            player_orders = {unit.uid: unit.order for unit in sim.living_units(sim.player_side)}
            for _ in range(25): sim.tick(0.1)
            self.assertEqual(brain.stats.decisions, 0)
            self.assertEqual(player_orders, {unit.uid: unit.order for unit in sim.living_units(sim.player_side)})
            self.assertTrue(any(unit.order != "Hold" for unit in sim.living_units(sim.enemy_side)))
            self.assertIn("Coordinated", sim.enemy_ai.last_plan)

    def test_higher_difficulty_improves_enemy_force_quality(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "campaign.json"
            sim = CampaignBattleSimulation(TacticalBrain(seed=202), seed=2202, campaign_path=path)
            sim.campaign.difficulty = 1.65
            sim.new_battle(seed=2203)
            enemy = sim.living_units(sim.enemy_side)
            self.assertGreater(sum(unit.experience for unit in enemy) / len(enemy), 0.45)


if __name__ == "__main__":
    unittest.main()
