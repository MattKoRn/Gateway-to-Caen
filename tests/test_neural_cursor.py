import tempfile
import unittest
from pathlib import Path

from gateway_to_caen.campaign_simulation import CampaignBattleSimulation
from gateway_to_caen.neural import TacticalBrain
from gateway_to_caen.neural_cursor import CursorFollowingCamera, NeuralCursorController


class FakeApp:
    def __init__(self, sim, brain):
        self.sim = sim
        self.brain = brain
        self.paused = False
        self.camera = CursorFollowingCamera(enabled=True)
        self.selected = set()
        self.clicks = []

    def _neural_left_click_world(self, x, y):
        unit = min(self.sim.living_units(self.sim.player_side), key=lambda item: (item.x-x)**2 + (item.y-y)**2)
        self.selected = {unit.uid}
        self.clicks.append(("left", unit.uid))

    def _neural_order_button(self, order):
        self.clicks.append(("order", order))
        for uid in self.selected:
            unit = self.sim.unit_by_id(uid)
            if unit:
                unit.order = order

    def _neural_right_click_world(self, x, y):
        self.clicks.append(("right", round(x, 2), round(y, 2)))
        self.sim.issue_order(self.selected, next(iter(self.selected)) and self.sim.unit_by_id(next(iter(self.selected))).order, x, y)


class NeuralCursorTests(unittest.TestCase):
    def test_cursor_performs_visible_select_command_and_destination_actions(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            brain = TacticalBrain(seed=301, epsilon=0.0)
            sim = CampaignBattleSimulation(brain, seed=3301, campaign_path=Path(folder) / "campaign.json")
            app = FakeApp(sim, brain)
            cursor = NeuralCursorController(brain, seed=3301, enabled=True)
            cursor.reset_for_map(sim)
            for _ in range(500):
                cursor.update(app, 0.05)
                sim.elapsed += 0.05
                if any(item[0] == "right" for item in app.clicks) or any(item == ("order", "Hold") for item in app.clicks):
                    break
            self.assertTrue(any(item[0] == "left" for item in app.clicks))
            self.assertTrue(any(item[0] == "order" for item in app.clicks))
            self.assertIsNotNone(app.camera.cursor_focus)

    def test_learning_uses_replay_memory(self) -> None:
        brain = TacticalBrain(seed=302, epsilon=0.0)
        state = [0.1] * 18
        for _ in range(10):
            brain.learn_transition(state, 0, 0.5, state)
        self.assertGreaterEqual(len(brain.replay_memory), 10)
        self.assertGreater(brain.stats.replay_steps, 0)


if __name__ == "__main__":
    unittest.main()
