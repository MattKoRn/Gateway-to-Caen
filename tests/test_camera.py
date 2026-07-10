import unittest
from gateway_to_caen.camera import TacticalCamera
from gateway_to_caen.neural import TacticalBrain
from gateway_to_caen.simulation import MAP_HEIGHT, MAP_WIDTH, BattleSimulation

class TacticalCameraTests(unittest.TestCase):

    def setUp(self) -> None:
        self.sim = BattleSimulation(TacticalBrain(seed=17), seed=1701, player_side='Allied')

    def test_selected_unit_gets_camera_priority(self) -> None:
        camera = TacticalCamera(enabled=True)
        unit = self.sim.living_units('Allied')[0]
        camera.update(self.sim, {unit.uid}, 0.3)
        self.assertEqual(camera.focus_label, 'Selected formation')
        self.assertGreater(camera.target_zoom, 2.0)
        half_w = MAP_WIDTH / (2 * camera.target_zoom)
        half_h = MAP_HEIGHT / (2 * camera.target_zoom)
        self.assertAlmostEqual(camera.target_x, max(unit.x, half_w), delta=0.01)
        self.assertAlmostEqual(camera.target_y, max(unit.y, half_h), delta=0.01)

    def test_recent_fire_focuses_action(self) -> None:
        camera = TacticalCamera(enabled=True)
        unit = self.sim.living_units('Allied')[0]
        unit.last_fire = self.sim.elapsed
        camera.update(self.sim, set(), 0.3)
        self.assertEqual(camera.focus_label, 'Active firefight')
        self.assertGreater(camera.target_zoom, 1.2)

    def test_manual_zoom_disables_auto_camera(self) -> None:
        camera = TacticalCamera(enabled=True)
        camera.manual_zoom(0.5)
        self.assertFalse(camera.enabled)
        self.assertGreater(camera.zoom, 1.0)

    def test_camera_position_is_clamped_to_map(self) -> None:
        camera = TacticalCamera(enabled=True)
        camera.target_zoom = 2.5
        camera.target_x = -100.0
        camera.target_y = 100.0
        camera._clamp_target()
        half_w = MAP_WIDTH / (2 * camera.target_zoom)
        half_h = MAP_HEIGHT / (2 * camera.target_zoom)
        self.assertGreaterEqual(camera.target_x, half_w)
        self.assertLessEqual(camera.target_y, MAP_HEIGHT - half_h)

    def test_battle_over_returns_to_overview(self) -> None:
        camera = TacticalCamera(enabled=True)
        self.sim.force_result('Allied')
        camera.update(self.sim, set(), 0.3)
        self.assertEqual(camera.focus_label, 'After-action overview')
        self.assertEqual(camera.target_zoom, 1.0)
if __name__ == '__main__':
    unittest.main()

class AutoCameraDetailTests(unittest.TestCase):

    def test_auto_camera_can_open_friendly_details(self) -> None:
        import time
        from gateway_to_caen.camera import AutoCameraMixin

        class Harness(AutoCameraMixin):
            pass
        harness = Harness()
        harness._camera_init(True)
        harness.sim = BattleSimulation(TacticalBrain(seed=41), seed=4101, player_side='Allied')
        harness.selected = set()
        unit = harness.sim.living_units('Allied')[0]
        harness.camera.focus_unit_ids = (unit.uid,)
        harness._auto_detail_next_real = time.perf_counter() - 1
        harness._update_auto_detail_selection()
        self.assertEqual(harness.selected, {unit.uid})
        self.assertEqual(harness._auto_detail_uid, unit.uid)
