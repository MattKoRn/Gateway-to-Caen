import tempfile
import unittest
from pathlib import Path

from gateway_to_caen.offline import (
    CampaignProfile,
    calculate_offline_rewards,
    claim_offline_progress,
    dismiss_pending_report,
    format_duration,
    load_profile,
    save_profile,
)


class OfflineProgressTests(unittest.TestCase):
    def test_duration_includes_all_units(self) -> None:
        self.assertEqual(format_duration(90061), "1 day, 1 hour, 1 minute, 1 second")

    def test_reward_rates(self) -> None:
        rewards = calculate_offline_rewards(3600)
        self.assertEqual(rewards.command_points, 60)
        self.assertEqual(rewards.supplies, 360)
        self.assertEqual(rewards.reinforcement_tokens, 2)
        self.assertEqual(rewards.intelligence_reports, 1)

    def test_claim_is_applied_once_and_report_persists_until_dismissed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "campaign_profile.json"
            profile = CampaignProfile(last_seen_utc=1_000.0)
            save_profile(path, profile)

            claimed, report = claim_offline_progress(path, now=4_600.0)
            self.assertIsNotNone(report)
            assert report is not None
            self.assertEqual(claimed.command_points, 60)
            self.assertTrue(claimed.pending_report)

            reloaded, repeated = claim_offline_progress(path, now=4_600.0)
            self.assertEqual(reloaded.command_points, 60)
            self.assertIsNotNone(repeated)

            dismiss_pending_report(path, reloaded)
            self.assertFalse(load_profile(path).pending_report)


if __name__ == "__main__":
    unittest.main()
