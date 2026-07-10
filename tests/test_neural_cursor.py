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
        self.ui_actions = []
        self.ui_visible = False
        self.battlefield_visible = True

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

    def _is_battlefield_visible(self):
        return self.battlefield_visible

    def _neural_can_navigate_ui(self):
        return True

    def _next_neural_ui_target(self):
        return {"kind": "notebook", "label": "Main tab: Command", "x": 320.0, "y": 18.0}

    def _neural_target_screen(self, target):
        return target["x"], target["y"]

    def _show_neural_ui_cursor(self, x, y, label):
        self.ui_visible = True

    def _hide_neural_ui_cursor(self):
        self.ui_visible = False

    def _neural_activate_ui_target(self, target):
        self.ui_actions.append(target["label"])
        return True


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

    def test_cursor_never_navigates_or_activates_non_map_ui(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            brain = TacticalBrain(seed=303, epsilon=0.0)
            sim = CampaignBattleSimulation(brain, seed=3303, campaign_path=Path(folder) / "campaign.json")
            app = FakeApp(sim, brain)
            cursor = NeuralCursorController(brain, seed=3303, enabled=True)
            cursor.reset_for_map(sim)
            cursor.phase = "idle"
            cursor.plan = None
            cursor.next_ui_visit_at = 0.0
            app.battlefield_visible = False
            for _ in range(80):
                cursor.update(app, 0.05)
                sim.elapsed += 0.05
            self.assertEqual(app.ui_actions, [])
            self.assertEqual(app.clicks, [])
            self.assertEqual(cursor.command_label, "WAITING FOR TACTICAL MAP")
            self.assertFalse(cursor.ui_mode)
            self.assertIsNone(cursor.ui_target)
            self.assertEqual(cursor.next_ui_visit_at, float("inf"))

            app.battlefield_visible = True
            for _ in range(400):
                cursor.update(app, 0.05)
                sim.elapsed += 0.05
                if any(item[0] == "left" for item in app.clicks):
                    break
            self.assertEqual(app.ui_actions, [])
            self.assertTrue(any(item[0] == "left" for item in app.clicks))

    def test_learning_uses_replay_memory(self) -> None:
        brain = TacticalBrain(seed=302, epsilon=0.0)
        state = [0.1] * 18
        for _ in range(10):
            brain.learn_transition(state, 0, 0.5, state)
        self.assertGreaterEqual(len(brain.replay_memory), 10)
        self.assertGreater(brain.stats.replay_steps, 0)


if __name__ == "__main__":
    unittest.main()
