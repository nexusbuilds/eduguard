"""Time-banking incentive system for EduGuard.

Maps grade performance to daily full-access allowances and banked discretionary hours.

Rules:
- research_only (poor grades): 60 min full access / day, no banked bonus
- limited: 90 min full access / day + up to 30 min banked time
- full (excellent): 120 min full access / day + up to 30 min banked time
- Weekends and holidays: banked bonus increases to 60 min
- Significant grade improvement (>= 5 percentage points): +4 banked hours
- Max 1 banked hour (60 min) can be used per day
"""
from datetime import date, datetime, timedelta
from typing import Dict, Optional
from dataclasses import dataclass


# Tier base allowances in minutes
TIER_DAILY_MINUTES = {
    "research_only": 60,
    "limited": 90,
    "full": 120,
}

# Banked-time bonus per day (in minutes)
WEEKDAY_BANKED_BONUS_MIN = 30
WEEKEND_BANKED_BONUS_MIN = 60
HOLIDAY_BANKED_BONUS_MIN = 60

# Caps
MAX_BANKED_MINUTES_PER_DAY = 60  # 1 hour
SIGNIFICANT_IMPROVEMENT_THRESHOLD = 5.0  # percentage points
BANKED_HOURS_REWARD_FOR_IMPROVEMENT = 4

# Simple Canadian/North American holidays (month, day)
# Expand as needed; uses fixed-date holidays for simplicity.
HOLIDAYS = {
    (1, 1),   # New Year's Day
    (7, 1),   # Canada Day
    (12, 25), # Christmas
    (12, 26), # Boxing Day
}


@dataclass
class TimeAllowance:
    base_minutes: int
    banked_bonus_minutes: int
    max_banked_use_today: int
    current_banked_hours: int
    total_available_minutes: int
    explanation: str


def is_weekend_or_holiday(d: Optional[date] = None) -> bool:
    if d is None:
        d = date.today()
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return True
    if (d.month, d.day) in HOLIDAYS:
        return True
    return False


def get_tier_allowance(tier: str, banked_hours: int, d: Optional[date] = None) -> TimeAllowance:
    """Calculate today's time allowance for a child."""
    if d is None:
        d = date.today()

    tier = tier or "research_only"
    base = TIER_DAILY_MINUTES.get(tier, 60)

    if tier == "research_only":
        # Poor grades: base allowance only, no banked bonus
        bonus = 0
        explanation = f"{tier} tier: {base} minutes of full access today. Earn better grades to unlock banked discretionary time."
    else:
        if is_weekend_or_holiday(d):
            bonus = HOLIDAY_BANKED_BONUS_MIN
            explanation = f"{tier} tier: {base} minutes + up to {bonus} min banked time (weekend/holiday bonus)."
        else:
            bonus = WEEKDAY_BANKED_BONUS_MIN
            explanation = f"{tier} tier: {base} minutes + up to {bonus} min banked time today."

    # Cannot use more than 1 banked hour per day overall
    max_banked_use = min(MAX_BANKED_MINUTES_PER_DAY, banked_hours * 60, bonus)

    # Total available = base + whatever banked time they can use today
    total = base + max_banked_use

    return TimeAllowance(
        base_minutes=base,
        banked_bonus_minutes=bonus,
        max_banked_use_today=max_banked_use,
        current_banked_hours=banked_hours,
        total_available_minutes=total,
        explanation=explanation,
    )


def detect_improvement(old_tier: Optional[str], new_tier: str) -> bool:
    """Detect significant improvement as a tier upgrade."""
    if old_tier is None:
        return False
    tier_order = {"research_only": 0, "limited": 1, "full": 2}
    old_idx = tier_order.get(old_tier, 0)
    new_idx = tier_order.get(new_tier, 0)
    return new_idx > old_idx


def calculate_banked_hours_reward(old_tier: Optional[str], new_tier: str, current_banked: int) -> int:
    """Return new banked hours total if a tier upgrade is detected."""
    if detect_improvement(old_tier, new_tier):
        return current_banked + BANKED_HOURS_REWARD_FOR_IMPROVEMENT
    return current_banked
