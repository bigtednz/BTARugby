import math
import unittest
from datetime import date

from analytics.baseline_evaluation import (
    BASE_ELO,
    Match,
    actual_home_result,
    brier_score,
    calculate_calibration,
    calculate_metrics,
    confidence_band,
    initialise_state,
    log_loss,
    make_prediction,
    margin_errors,
    run_model_for_season,
    update_state_after_match,
    validate_probability_sum,
    walk_forward_splits,
    training_summary,
)


def match(
    season,
    match_id,
    home_team_id,
    away_team_id,
    home_score,
    away_score,
    round_name="Round 1",
):
    return Match(
        competition_code="NPC",
        season=season,
        match_id=match_id,
        match_date=date(season, 8, min(match_id % 28 + 1, 28)),
        round_name=round_name,
        home_team_id=home_team_id,
        home_team=f"Team {home_team_id}",
        away_team_id=away_team_id,
        away_team=f"Team {away_team_id}",
        home_score=home_score,
        away_score=away_score,
        match_status="Completed",
    )


class BaselineEvaluationTests(unittest.TestCase):
    def test_no_target_match_leakage_in_rolling_calculation(self):
        matches = [
            match(2022, 100, 1, 2, 30, 20),
            match(2023, 101, 1, 2, 10, 40),
        ]
        predictions, evaluations, _, _ = run_model_for_season(
            "RollingMarginOnlyBaseline", matches, 2023
        )

        self.assertEqual(len(predictions), 1)
        # If the 2023 target match leaked, the rolling signal would be strongly negative.
        self.assertGreater(predictions[0].predicted_margin, 0)
        self.assertEqual(len(evaluations), 1)

    def test_elo_is_captured_before_match_update(self):
        m = match(2022, 100, 1, 2, 35, 10)
        state = initialise_state([])
        summary = training_summary([])
        prediction = make_prediction("EloOnlyBaseline", m, state, summary, 2022)

        self.assertEqual(state.ratings[1], BASE_ELO)
        self.assertEqual(state.ratings[2], BASE_ELO)
        update_state_after_match(state, m)
        self.assertNotEqual(state.ratings[1], BASE_ELO)
        self.assertGreater(prediction.home_win_probability, 0.5)

    def test_brier_score_calculation(self):
        self.assertAlmostEqual(brier_score(0.7, 1.0), 0.09)
        self.assertAlmostEqual(brier_score(0.2, 0.0), 0.04)

    def test_log_loss_clipping(self):
        self.assertTrue(math.isfinite(log_loss(1.0, 0.0, 0.0, "H")))
        self.assertTrue(math.isfinite(log_loss(0.0, 0.0, 1.0, "H")))
        self.assertGreater(log_loss(0.0, 0.0, 1.0, "H"), 10)

    def test_margin_mae_and_rmse(self):
        mae, rmse, bias = margin_errors([5, -3, 10], [0, -6, 14])
        self.assertAlmostEqual(mae, 4.0)
        self.assertAlmostEqual(rmse, math.sqrt((25 + 9 + 16) / 3))
        self.assertAlmostEqual(bias, (5 + 3 - 4) / 3)

    def test_calibration_band_allocation_including_zero_and_one(self):
        self.assertEqual(confidence_band(0.0), ("0.00-0.10", 0.0, 0.1))
        self.assertEqual(confidence_band(1.0), ("0.90-1.00", 0.9, 1.0))
        self.assertEqual(confidence_band(0.42), ("0.40-0.50", 0.4, 0.5))

    def test_handling_of_draws(self):
        draw = match(2023, 111, 1, 2, 20, 20)
        self.assertEqual(actual_home_result(draw), 0.5)
        predictions, evaluations, _, _ = run_model_for_season(
            "HomeTeamBaseline",
            [match(2022, 100, 1, 2, 30, 20), draw],
            2023,
        )
        self.assertEqual(len(predictions), 1)
        self.assertIsNone(evaluations[0]["correct_winner"])

    def test_insufficient_history_fallback(self):
        m = match(2023, 101, 1, 2, 18, 24)
        predictions, _, _, _ = run_model_for_season("RollingMarginOnlyBaseline", [m], 2023)
        self.assertAlmostEqual(predictions[0].predicted_margin, 0.0)
        self.assertTrue(validate_probability_sum(
            predictions[0].home_win_probability,
            predictions[0].draw_probability,
            predictions[0].away_win_probability,
        ))

    def test_probability_sum_validation(self):
        self.assertTrue(validate_probability_sum(0.45, 0.05, 0.50))
        self.assertFalse(validate_probability_sum(0.45, 0.05, 0.60))

    def test_walk_forward_season_boundaries(self):
        matches = [
            match(2021, 1, 1, 2, 10, 7),
            match(2022, 2, 1, 3, 14, 12),
            match(2023, 3, 1, 4, 21, 20),
            match(2024, 4, 2, 4, 22, 20),
        ]
        self.assertEqual(walk_forward_splits(matches, None, None), [2023, 2024])
        self.assertEqual(walk_forward_splits(matches, 2024, 2024), [2024])

    def test_metrics_with_draws(self):
        matches = [
            match(2022, 100, 1, 2, 30, 20),
            match(2023, 101, 1, 2, 20, 20),
            match(2023, 102, 1, 3, 25, 10),
        ]
        _, evaluations, _, _ = run_model_for_season("HomeTeamBaseline", matches, 2023)
        metrics = calculate_metrics(evaluations)
        self.assertEqual(metrics["matches_evaluated"], 2.0)
        self.assertEqual(metrics["non_draw_matches_evaluated"], 1.0)
        self.assertIn("home_probability_brier", metrics)

    def test_calibration_rows(self):
        matches = [
            match(2022, 100, 1, 2, 30, 20),
            match(2023, 101, 1, 2, 25, 20),
            match(2023, 102, 2, 1, 18, 22),
        ]
        _, evaluations, _, _ = run_model_for_season("HomeTeamBaseline", matches, 2023)
        rows = calculate_calibration(evaluations)
        self.assertTrue(rows)
        self.assertEqual(sum(row["prediction_count"] for row in rows), 2)


if __name__ == "__main__":
    unittest.main()
