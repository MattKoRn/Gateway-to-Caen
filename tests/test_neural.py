import tempfile
import unittest
from pathlib import Path

from gateway_to_caen.neural import TacticalBrain


class TacticalBrainTests(unittest.TestCase):
    def test_training_changes_output_and_persists(self) -> None:
        brain = TacticalBrain(seed=7, epsilon=0.0)
        state = [0.1] * 10
        before = brain.forward(state)[1]
        for _ in range(20):
            brain.train(state, 2, 1.0, state)
        after = brain.forward(state)[1]
        self.assertNotEqual(before[2], after[2])
        self.assertEqual(brain.stats.training_steps, 20)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "brain.json"
            brain.save(path)
            loaded = TacticalBrain.load_or_create(path)
            self.assertEqual(loaded.stats.training_steps, 20)
            self.assertAlmostEqual(loaded.forward(state)[1][2], after[2], places=7)


if __name__ == "__main__":
    unittest.main()
