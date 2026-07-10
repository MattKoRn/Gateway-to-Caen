import tempfile
import unittest
from pathlib import Path

from gateway_to_caen.campaign import CampaignState, FactionResources, UNIT_COSTS
from gateway_to_caen.campaign_simulation import CampaignBattleSimulation
from gateway_to_caen.neural import TacticalBrain


class CampaignPersistenceTests(unittest.TestCase):
    def test_survivors_resources_and_identity_persist_across_maps_and_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "campaign.json"
            brain = TacticalBrain(seed=101, epsilon=0.0)
            sim = CampaignBattleSimulation(brain, seed=1001, campaign_path=path)
            survivor = sim.living_units("Allied")[0]
            survivor_uid = survivor.uid
            survivor.men -= 2
            survivor.ammo = 63.0
            survivor.kills = 3
            resources_before = sim.campaign.resources["Allied"].supplies
            sim.force_result("Allied")
            self.assertTrue(sim.advance_post_battle(10.1))
            redeployed = sim.unit_by_id(survivor_uid)
            self.assertIsNotNone(redeployed)
            assert redeployed is not None
            self.assertEqual(redeployed.men, survivor.max_men - 2)
            self.assertEqual(redeployed.kills, 3)
            self.assertNotEqual(sim.campaign.resources["Allied"].supplies, resources_before)
            restored = CampaignBattleSimulation(TacticalBrain(seed=102), seed=1002, campaign_path=path)
            self.assertTrue(any(unit.uid == survivor_uid for unit in restored.campaign.rosters["Allied"]))
            self.assertGreaterEqual(restored.campaign.battle_index, 2)

    def test_neural_requisition_deducts_costs_for_both_sides(self) -> None:
        campaign = CampaignState.fresh()
        brain = TacticalBrain(seed=103, epsilon=0.0)
        before = {side: campaign.resources[side].supplies for side in ("Allied", "Axis")}
        records = campaign.requisition_for_battle(brain, seed=333, max_per_side=2)
        self.assertTrue(any(record.side == "Allied" for record in records))
        self.assertTrue(any(record.side == "Axis" for record in records))
        for side in ("Allied", "Axis"):
            self.assertLess(campaign.resources[side].supplies, before[side])

    def test_empty_destroyed_roster_stays_empty_when_loaded(self) -> None:
        campaign = CampaignState.fresh()
        campaign.rosters["Axis"] = []
        restored = CampaignState.from_dict(campaign.to_dict())
        self.assertEqual(restored.rosters["Axis"], [])

    def test_adaptive_difficulty_moves_with_recent_performance(self) -> None:
        campaign = CampaignState.fresh()
        start = campaign.difficulty
        for _ in range(4): campaign.update_scaling(True)
        high = campaign.difficulty
        self.assertGreater(high, start)
        for _ in range(6): campaign.update_scaling(False)
        self.assertLess(campaign.difficulty, high)
        self.assertGreaterEqual(campaign.reward_multiplier, 0.72)

    def test_each_map_rolls_new_objectives_and_theme_history(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            sim = CampaignBattleSimulation(TacticalBrain(seed=104), seed=5001, campaign_path=Path(folder) / "campaign.json")
            first = {item["title"] for item in sim.rolled_objectives}
            first_theme = sim.map_theme
            sim.new_battle(seed=5002)
            second = {item["title"] for item in sim.rolled_objectives}
            self.assertEqual(len(first), 4)
            self.assertEqual(len(second), 4)
            self.assertTrue(first != second or first_theme != sim.map_theme)
            self.assertGreaterEqual(len(sim.campaign.map_history), 2)


if __name__ == "__main__":
    unittest.main()
