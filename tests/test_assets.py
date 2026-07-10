import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from gateway_to_caen.asset_bundle import ensure_assets


class PackagedAssetTests(unittest.TestCase):
    def test_bundle_extracts_every_unit_sprite_and_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"XDG_DATA_HOME": folder}):
            root = ensure_assets()
            for side in ("allied", "axis"):
                for unit_type in ("rifle", "support", "scout", "mortar", "armour"):
                    for size in (40, 56, 72):
                        path = root / "sprites" / f"{side}_{unit_type}_{size}.png"
                        self.assertTrue(path.exists(), path)
                        self.assertGreater(path.stat().st_size, 200)
            self.assertTrue((root / "ui" / "neural_cursor.png").exists())

    def test_sound_files_are_valid_mono_wav_assets(self) -> None:
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"XDG_DATA_HOME": folder}):
            root = ensure_assets() / "sounds"
            required = ("ui_click", "select", "order", "requisition", "objective", "battle_start", "gunfire", "explosion", "victory", "defeat")
            for name in required:
                with wave.open(str(root / f"{name}.wav"), "rb") as audio:
                    self.assertEqual(audio.getnchannels(), 1)
                    self.assertGreater(audio.getnframes(), 1000)


if __name__ == "__main__":
    unittest.main()
