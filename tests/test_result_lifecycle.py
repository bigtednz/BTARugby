import unittest
from datetime import date, datetime

from analytics.result_lifecycle import (
    absolute_margin_error,
    derive_result_lifecycle,
    latest_pre_match_prediction,
    signed_margin_error,
)


class ResultLifecycleTests(unittest.TestCase):
    def test_confirmed_result_accepts_zero_scores_with_source_evidence(self):
        lifecycle = derive_result_lifecycle(
            home_score=0,
            away_score=0,
            source_status="Result",
            played=True,
            score_source="RugbyPass fixture JSON",
        )

        self.assertEqual(lifecycle.match_status, "Completed")
        self.assertEqual(lifecycle.score_status, "Confirmed")
        self.assertTrue(lifecycle.result_ready)
        self.assertEqual(lifecycle.validation_status, "Valid")

    def test_placeholder_zero_zero_without_final_evidence_is_pending(self):
        lifecycle = derive_result_lifecycle(home_score=0, away_score=0, source_status="Fixture", played=False)

        self.assertEqual(lifecycle.match_status, "Scheduled")
        self.assertEqual(lifecycle.score_status, "Pending")
        self.assertFalse(lifecycle.result_ready)

    def test_completed_without_scores_is_not_evaluation_ready(self):
        lifecycle = derive_result_lifecycle(home_score=None, away_score=None, source_status="Result", played=True)

        self.assertEqual(lifecycle.match_status, "Completed")
        self.assertEqual(lifecycle.score_status, "Unavailable")
        self.assertFalse(lifecycle.result_ready)

    def test_margin_errors_are_actual_minus_predicted(self):
        self.assertEqual(signed_margin_error(32, 38, 7.25), -13.25)
        self.assertEqual(absolute_margin_error(32, 38, 7.25), 13.25)

    def test_latest_pre_match_prediction_uses_kickoff_cutoff(self):
        kickoff = datetime(2026, 8, 7, 19, 10)
        rows = [
            {"ProductionPredictionID": 1, "PredictionGeneratedAt": datetime(2026, 8, 6, 9, 0)},
            {"ProductionPredictionID": 2, "PredictionGeneratedAt": datetime(2026, 8, 7, 19, 9)},
            {"ProductionPredictionID": 3, "PredictionGeneratedAt": datetime(2026, 8, 7, 19, 11)},
        ]

        self.assertEqual(latest_pre_match_prediction(rows, kickoff_datetime=kickoff)["ProductionPredictionID"], 2)

    def test_date_cutoff_is_used_when_kickoff_missing(self):
        rows = [
            {"ProductionPredictionID": 1, "PredictionGeneratedAt": datetime(2026, 8, 6, 9, 0)},
            {"ProductionPredictionID": 2, "PredictionGeneratedAt": datetime(2026, 8, 7, 9, 0)},
        ]

        self.assertEqual(
            latest_pre_match_prediction(rows, kickoff_datetime=None, match_date=date(2026, 8, 7))["ProductionPredictionID"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
