from typing import Optional

# Keep leaderboard ordering intact while presenting more readable magnitudes.
IMPACT_SCORE_DISPLAY_SCALE = 0.1


def scale_impact_score(value: Optional[float]) -> float:
    return round(float(value or 0.0) * IMPACT_SCORE_DISPLAY_SCALE, 2)

