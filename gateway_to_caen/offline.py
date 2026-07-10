"""Offline progress, reward calculation, and persistent campaign profile."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .persistence import atomic_write_json, read_json

MAX_OFFLINE_SECONDS = 30 * 24 * 60 * 60


def format_duration(total_seconds: int | float) -> str:
    """Return a full days/hours/minutes/seconds duration string."""
    remaining = max(0, int(total_seconds))
    days, remaining = divmod(remaining, 24 * 60 * 60)
    hours, remaining = divmod(remaining, 60 * 60)
    minutes, seconds = divmod(remaining, 60)
    def unit(value: int, singular: str) -> str:
        return f"{value} {singular if value == 1 else singular + 's'}"

    return ", ".join((unit(days, "day"), unit(hours, "hour"), unit(minutes, "minute"), unit(seconds, "second")))


@dataclass
class OfflineRewards:
    offline_seconds: int = 0
    rewarded_seconds: int = 0
    command_points: int = 0
    supplies: int = 0
    reinforcement_tokens: int = 0
    intelligence_reports: int = 0
    capped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "OfflineRewards":
        data = data if isinstance(data, dict) else {}
        valid = set(cls.__dataclass_fields__)
        return cls(**{key: data[key] for key in valid if key in data})

    def combine(self, other: "OfflineRewards") -> "OfflineRewards":
        return OfflineRewards(
            offline_seconds=self.offline_seconds + other.offline_seconds,
            rewarded_seconds=min(MAX_OFFLINE_SECONDS, self.rewarded_seconds + other.rewarded_seconds),
            command_points=self.command_points + other.command_points,
            supplies=self.supplies + other.supplies,
            reinforcement_tokens=self.reinforcement_tokens + other.reinforcement_tokens,
            intelligence_reports=self.intelligence_reports + other.intelligence_reports,
            capped=self.capped or other.capped,
        )


@dataclass
class CampaignProfile:
    version: int = 1
    command_points: int = 0
    supplies: int = 0
    reinforcement_tokens: int = 0
    intelligence_reports: int = 0
    lifetime_offline_seconds: int = 0
    sessions: int = 0
    last_seen_utc: float = 0.0
    pending_report: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CampaignProfile":
        data = data if isinstance(data, dict) else {}
        valid = set(cls.__dataclass_fields__)
        profile = cls(**{key: data[key] for key in valid if key in data})
        profile.command_points = max(0, int(profile.command_points))
        profile.supplies = max(0, int(profile.supplies))
        profile.reinforcement_tokens = max(0, int(profile.reinforcement_tokens))
        profile.intelligence_reports = max(0, int(profile.intelligence_reports))
        profile.lifetime_offline_seconds = max(0, int(profile.lifetime_offline_seconds))
        profile.sessions = max(0, int(profile.sessions))
        profile.last_seen_utc = max(0.0, float(profile.last_seen_utc))
        profile.pending_report = profile.pending_report if isinstance(profile.pending_report, dict) else {}
        return profile

    def apply(self, rewards: OfflineRewards) -> None:
        self.command_points += rewards.command_points
        self.supplies += rewards.supplies
        self.reinforcement_tokens += rewards.reinforcement_tokens
        self.intelligence_reports += rewards.intelligence_reports
        self.lifetime_offline_seconds += rewards.offline_seconds


def calculate_offline_rewards(seconds: int | float) -> OfflineRewards:
    """Calculate deterministic rewards, capped at thirty rewarded days."""
    offline_seconds = max(0, int(seconds))
    rewarded_seconds = min(offline_seconds, MAX_OFFLINE_SECONDS)
    return OfflineRewards(
        offline_seconds=offline_seconds,
        rewarded_seconds=rewarded_seconds,
        command_points=rewarded_seconds // 60,
        supplies=rewarded_seconds // 10,
        reinforcement_tokens=rewarded_seconds // (30 * 60),
        intelligence_reports=rewarded_seconds // (60 * 60),
        capped=offline_seconds > MAX_OFFLINE_SECONDS,
    )


def load_profile(path: Path) -> CampaignProfile:
    return CampaignProfile.from_dict(read_json(path, {}))


def save_profile(path: Path, profile: CampaignProfile) -> None:
    atomic_write_json(path, profile.to_dict())


def claim_offline_progress(
    path: Path,
    now: float | None = None,
) -> tuple[CampaignProfile, OfflineRewards | None]:
    """Claim elapsed rewards and retain the report until the player dismisses it."""
    current = time.time() if now is None else float(now)
    profile = load_profile(path)
    existing = OfflineRewards.from_dict(profile.pending_report) if profile.pending_report else None

    if profile.last_seen_utc <= 0.0:
        profile.last_seen_utc = current
        profile.sessions += 1
        save_profile(path, profile)
        return profile, existing

    elapsed = max(0, int(current - profile.last_seen_utc))
    report = existing
    if elapsed > 0:
        earned = calculate_offline_rewards(elapsed)
        profile.apply(earned)
        report = earned if report is None else report.combine(earned)
        profile.pending_report = report.to_dict()

    profile.last_seen_utc = current
    profile.sessions += 1
    save_profile(path, profile)
    return profile, report


def touch_profile(path: Path, profile: CampaignProfile, now: float | None = None) -> None:
    profile.last_seen_utc = time.time() if now is None else float(now)
    save_profile(path, profile)


def dismiss_pending_report(path: Path, profile: CampaignProfile) -> None:
    profile.pending_report = {}
    save_profile(path, profile)
