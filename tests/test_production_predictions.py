import unittest
from datetime import date, datetime

from analytics.baseline_evaluation import Match
from analytics.run_production_predictions import (
    Champion,
    PROBABILITY_TARGET,
    MARGIN_TARGET,
    ProductionMatch,
    build_prediction,
    champion_registry_issues,
    confidence_level,
    data_quality_issues_for_prediction,
    is_eligible_scheduled_match,
    predicted_winner,
    quality_issue,
    should_write_prediction,
    validate_probability_sum,
)


def match(season, match_id, status="Scheduled", home_score=None, away_score=None, day=10):
    return Match(
        competition_code="NPC",
        season=season,
        match_id=match_id,
        match_date=date(season, 8, day),
        round_name="Round 1",
        home_team_id=1,
        home_team="Home",
        away_team_id=2,
        away_team="Away",
        home_score=home_score,
        away_score=away_score,
        match_status=status,
    )


def production_match(m):
    return ProductionMatch(m, venue="Venue", source_system="RugbyPass", source_url="https://example.test")


def champions():
    return {
        PROBABILITY_TARGET: Champion(PROBABILITY_TARGET, 1, "EloOnlyBaseline", "v0.2.0"),
        MARGIN_TARGET: Champion(MARGIN_TARGET, 1, "EloOnlyBaseline", "v0.2.0"),
    }


class ProductionPredictionTests(unittest.TestCase):
    def test_champion_registry_rules(self):
        valid = [
            Champion(PROBABILITY_TARGET, 1, "EloOnlyBaseline", "v0.2.0"),
            Champion(MARGIN_TARGET, 1, "EloOnlyBaseline", "v0.2.0"),
        ]
        duplicate = valid + [Champion(MARGIN_TARGET, 2, "Other", "v1")]

        self.assertEqual(champion_registry_issues(valid), [])
        self.assertIn("Multiple active champions for margin", champion_registry_issues(duplicate))
        self.assertIn("Missing active champion for margin", champion_registry_issues(valid[:1]))

    def test_duplicate_prediction_prevention(self):
        self.assertTrue(should_write_prediction(0, replace=False))
        self.assertTrue(should_write_prediction(1, replace=True))
        self.assertFalse(should_write_prediction(1, replace=False))

    def test_confidence_band_boundaries(self):
        self.assertEqual(confidence_level(0.59, 0.01, 0.40), "Low")
        self.assertEqual(confidence_level(0.60, 0.01, 0.39), "Moderate")
        self.assertEqual(confidence_level(0.70, 0.01, 0.29), "High")
        self.assertEqual(confidence_level(0.80, 0.01, 0.19), "Very High")

    def test_scheduled_eligibility_excludes_completed(self):
        self.assertTrue(is_eligible_scheduled_match(match(2026, 10), 2026, None, None, datetime(2026, 8, 1)))
        self.assertFalse(is_eligible_scheduled_match(match(2026, 11, "Completed", 20, 10), 2026, None))
        self.assertFalse(is_eligible_scheduled_match(match(2025, 12), 2026, None))
        self.assertTrue(is_eligible_scheduled_match(match(2026, 13), None, 13))
        self.assertFalse(is_eligible_scheduled_match(match(2026, 14), None, 13))

    def test_unknown_time_production_eligibility(self):
        future = match(2026, 15, day=10)
        same_day = match(2026, 16, day=10)

        self.assertTrue(is_eligible_scheduled_match(future, now_utc=datetime(2026, 8, 8, 12, 0)))
        self.assertFalse(is_eligible_scheduled_match(same_day, now_utc=datetime(2026, 8, 10, 0, 30)))

    def test_known_time_production_eligibility(self):
        m = match(2026, 17, day=10)
        kickoff_utc = datetime(2026, 8, 10, 7, 10)

        self.assertTrue(is_eligible_scheduled_match(m, kickoff_datetime_utc=kickoff_utc, now_utc=datetime(2026, 8, 10, 7, 0)))
        self.assertFalse(is_eligible_scheduled_match(m, kickoff_datetime_utc=kickoff_utc, now_utc=datetime(2026, 8, 10, 7, 11)))

    def test_probability_validation_and_predicted_winner(self):
        self.assertTrue(validate_probability_sum(0.55, 0.05, 0.40))
        self.assertFalse(validate_probability_sum(0.55, 0.05, 0.45))
        self.assertFalse(validate_probability_sum(1.1, 0.0, -0.1))
        self.assertEqual(predicted_winner(0.55, 0.05, 0.40), "H")
        self.assertEqual(predicted_winner(0.35, 0.05, 0.60), "A")
        self.assertEqual(predicted_winner(0.30, 0.40, 0.30), "D")

    def test_feature_cutoff_validation(self):
        scheduled = production_match(match(2026, 20, day=10))
        prediction = type("Prediction", (), {
            "home_win_probability": 0.55,
            "draw_probability": 0.05,
            "away_win_probability": 0.40,
        })()
        issues = data_quality_issues_for_prediction(scheduled, prediction, date(2026, 8, 10), 1500.0, 1500.0)
        self.assertTrue(any(issue["issue_code"] == "FEATURE_CUTOFF_LEAKAGE" for issue in issues))

    def test_critical_versus_warning_issue_shape(self):
        scheduled = production_match(match(2026, 21))
        critical = quality_issue(scheduled, "BAD", "Critical", "Bad issue", True)
        warning = quality_issue(scheduled, "WARN", "Warning", "Warning issue", False)
        self.assertTrue(critical["blocking"])
        self.assertFalse(warning["blocking"])

    def test_prediction_explanation_separates_used_and_contextual_fields(self):
        history = [
            match(2025, 1, "Completed", 30, 20, day=1),
            Match("NPC", 2025, 2, date(2025, 8, 2), "Round 1", 2, "Away", 1, "Home", 18, 21, "Completed"),
        ]
        scheduled = production_match(match(2026, 30, day=20))
        prediction = build_prediction(
            scheduled,
            history + [scheduled.match],
            champions(),
            sheets=set(),
            generated_at=datetime(2026, 8, 1),
        )

        self.assertIsNotNone(prediction.adjusted_elo_difference)
        self.assertIsNotNone(prediction.home_rolling_margin)
        self.assertEqual(prediction.probability_champion.model_name, "EloOnlyBaseline")
        self.assertTrue(any(issue["issue_code"] == "MISSING_TEAM_SHEET" for issue in prediction.issues))

    def test_repeatable_prediction_results(self):
        history = [match(2025, 1, "Completed", 30, 20, day=1)]
        scheduled = production_match(match(2026, 31, day=20))
        first = build_prediction(scheduled, history + [scheduled.match], champions(), set(), datetime(2026, 8, 1))
        second = build_prediction(scheduled, history + [scheduled.match], champions(), set(), datetime(2026, 8, 1))

        self.assertEqual(first.home_win_probability, second.home_win_probability)
        self.assertEqual(first.predicted_home_margin, second.predicted_home_margin)
        self.assertEqual(first.confidence_level, second.confidence_level)


if __name__ == "__main__":
    unittest.main()
