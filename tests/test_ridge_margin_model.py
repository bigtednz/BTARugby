import unittest
from datetime import date

from analytics.baseline_evaluation import Match, walk_forward_splits
from analytics.ridge_margin_model import (
    FeatureRow,
    fit_ridge_model,
    predict_margin,
    run_ridge_for_season,
    select_champion_status,
)


def match(season, match_id, home_team_id, away_team_id, home_score, away_score):
    return Match(
        competition_code="NPC",
        season=season,
        match_id=match_id,
        match_date=date(season, 8, min(match_id % 28 + 1, 28)),
        round_name="Round 1",
        home_team_id=home_team_id,
        home_team=f"Team {home_team_id}",
        away_team_id=away_team_id,
        away_team=f"Team {away_team_id}",
        home_score=home_score,
        away_score=away_score,
        match_status="Completed",
    )


def row(m, values):
    return FeatureRow(
        match=m,
        values={
            "PreMatchEloDiff": values.get("PreMatchEloDiff", 55.0),
            "Rolling3MarginDiff": values.get("Rolling3MarginDiff"),
            "Rolling5MarginDiff": values.get("Rolling5MarginDiff"),
            "SeasonToDateMarginDiff": values.get("SeasonToDateMarginDiff"),
            "Rolling5PointsForDiff": values.get("Rolling5PointsForDiff"),
            "Rolling5PointsAgainstDiff": values.get("Rolling5PointsAgainstDiff"),
            "HomeAwayFormDiff": values.get("HomeAwayFormDiff"),
            "RestDaysDiff": values.get("RestDaysDiff"),
            "HeadToHeadMargin": values.get("HeadToHeadMargin"),
            "ReturningPlayersDiff": values.get("ReturningPlayersDiff"),
            "ReturningStartersDiff": values.get("ReturningStartersDiff"),
        },
        target=None if m.home_score is None else float(m.home_score - m.away_score),
        feature_cutoff_date=None,
    )


class RidgeMarginModelTests(unittest.TestCase):
    def test_training_only_standardisation_and_imputation(self):
        train = [
            row(match(2022, 1, 1, 2, 30, 20), {"Rolling3MarginDiff": 0.0}),
            row(match(2022, 2, 2, 3, 20, 25), {"Rolling3MarginDiff": 10.0}),
            row(match(2022, 3, 3, 4, 25, 20), {"Rolling3MarginDiff": None}),
        ]
        model = fit_ridge_model(train, alpha=1.0)
        param = next(p for p in model.parameters if p.feature_name == "Rolling3MarginDiff")

        self.assertAlmostEqual(param.imputation_value, 5.0)
        self.assertAlmostEqual(param.feature_mean, 5.0)
        self.assertGreater(param.feature_stddev, 0.0)

    def test_target_season_isolation(self):
        train_match = match(2022, 1, 1, 2, 30, 20)
        eval_match = match(2023, 2, 1, 2, 5, 55)
        feature_rows = {
            1: row(train_match, {"Rolling3MarginDiff": 0.0}),
            2: row(eval_match, {"Rolling3MarginDiff": 1000.0}),
        }
        predictions, evaluations, _, summary, model = run_ridge_for_season(
            [train_match, eval_match], feature_rows, 2023, alpha=1.0
        )

        self.assertEqual(summary["training_end"], train_match.match_date)
        learned = next(p for p in model.parameters if p.feature_name == "Rolling3MarginDiff")
        self.assertAlmostEqual(learned.feature_mean, 0.0)
        self.assertEqual(len(predictions), 1)
        self.assertEqual(len(evaluations), 1)

    def test_prediction_equals_intercept_plus_contributions(self):
        rows = [
            row(match(2022, 1, 1, 2, 30, 20), {"Rolling3MarginDiff": 5.0}),
            row(match(2022, 2, 2, 3, 15, 30), {"Rolling3MarginDiff": -5.0}),
            row(match(2022, 3, 3, 4, 25, 20), {"Rolling3MarginDiff": 1.0}),
        ]
        model = fit_ridge_model(rows, alpha=1.0)
        predicted, contributions = predict_margin(model, rows[0])

        self.assertAlmostEqual(predicted, sum(c["contribution"] for c in contributions))
        self.assertEqual(contributions[0]["feature_name"], "Intercept")
        self.assertEqual(contributions[0]["contribution_rank"], 0)
        self.assertTrue(all(c["contribution_rank"] is not None for c in contributions))

    def test_missing_feature_indicator_is_created(self):
        rows = [
            row(match(2022, 1, 1, 2, 30, 20), {"ReturningPlayersDiff": None}),
            row(match(2022, 2, 2, 3, 20, 25), {"ReturningPlayersDiff": 3.0}),
        ]
        model = fit_ridge_model(rows, alpha=1.0)
        indicator = next(p for p in model.parameters if p.feature_name == "ReturningPlayersDiff_Missing")

        self.assertTrue(indicator.is_missingness_indicator)
        self.assertAlmostEqual(indicator.imputation_value, 0.5)

    def test_walk_forward_boundaries(self):
        matches = [
            match(2021, 1, 1, 2, 20, 10),
            match(2022, 2, 1, 2, 22, 12),
            match(2023, 3, 1, 2, 25, 17),
            match(2024, 4, 1, 2, 18, 21),
        ]

        self.assertEqual(walk_forward_splits(matches, None, None), [2023, 2024])

    def test_champion_selection_rules(self):
        ridge = {
            2023: {"matches_evaluated": 10, "margin_mae": 9.0, "mean_margin_error": 0.2, "large_error_rate": 0.1},
            2024: {"matches_evaluated": 10, "margin_mae": 10.0, "mean_margin_error": 0.1, "large_error_rate": 0.1},
            2025: {"matches_evaluated": 10, "margin_mae": 12.0, "mean_margin_error": -0.1, "large_error_rate": 0.2},
        }
        benchmark = {
            2023: {"matches_evaluated": 10, "margin_mae": 10.0, "mean_margin_error": 0.5, "large_error_rate": 0.2},
            2024: {"matches_evaluated": 10, "margin_mae": 11.0, "mean_margin_error": 0.4, "large_error_rate": 0.2},
            2025: {"matches_evaluated": 10, "margin_mae": 11.0, "mean_margin_error": 0.4, "large_error_rate": 0.2},
        }

        self.assertEqual(select_champion_status(ridge, benchmark)["status"], "Champion")
        ridge[2024]["margin_mae"] = 15.0
        self.assertEqual(select_champion_status(ridge, benchmark)["status"], "Rejected")

    def test_repeated_runs_are_identical(self):
        rows = [
            row(match(2022, 1, 1, 2, 30, 20), {"Rolling3MarginDiff": 5.0}),
            row(match(2022, 2, 2, 3, 15, 30), {"Rolling3MarginDiff": -5.0}),
            row(match(2022, 3, 3, 4, 25, 20), {"Rolling3MarginDiff": 1.0}),
        ]
        model_a = fit_ridge_model(rows, alpha=10.0)
        model_b = fit_ridge_model(rows, alpha=10.0)

        self.assertEqual(model_a.intercept, model_b.intercept)
        self.assertEqual([p.coefficient for p in model_a.parameters], [p.coefficient for p in model_b.parameters])


if __name__ == "__main__":
    unittest.main()
