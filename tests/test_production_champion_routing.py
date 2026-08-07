from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from analytics import run_production_predictions as production


class ProductionChampionRoutingTests(unittest.TestCase):
    def _match(self):
        return production.ProductionMatch(
            match=SimpleNamespace(
                competition_code="NPC",
                season=2026,
                match_id=999001,
                match_date=SimpleNamespace(),  # Not used by patched helpers.
                round_name="Round 3",
                home_team_id=1,
                home_team="Home",
                away_team_id=2,
                away_team="Away",
                home_score=0,
                away_score=0,
                match_status="Scheduled",
            ),
            venue="Test Ground",
            source_system="test",
            source_url=None,
            kickoff_datetime_local=None,
            kickoff_datetime_utc=None,
            kickoff_time_known=False,
            kickoff_time_source=None,
        )

    @staticmethod
    def _champion(target_type, model_version_id, model_name, model_version="v0.2.0"):
        return production.Champion(
            target_type=target_type,
            model_version_id=model_version_id,
            model_name=model_name,
            model_version=model_version,
        )

    @staticmethod
    def _prediction(home, draw, away, margin):
        return SimpleNamespace(
            home_win_probability=home,
            draw_probability=draw,
            away_win_probability=away,
            predicted_margin=margin,
        )

    def test_different_probability_and_margin_champions_are_routed_separately(self):
        """
        Regression test for the v0.4 bug:
        production must not generate one hard-coded Elo prediction and then label it
        with two different champion IDs.
        """
        probability_champion = self._champion(
            production.PROBABILITY_TARGET, 101, "ProbabilityModel"
        )
        margin_champion = self._champion(
            production.MARGIN_TARGET, 202, "MarginModel"
        )
        champions = {
            production.PROBABILITY_TARGET: probability_champion,
            production.MARGIN_TARGET: margin_champion,
        }

        probability_result = self._prediction(0.70, 0.05, 0.25, 4.0)
        margin_result = self._prediction(0.55, 0.05, 0.40, 12.5)

        fake_state = SimpleNamespace(
            ratings={1: 1600.0, 2: 1500.0},
            rolling_margins={1: [5.0, 3.0, 7.0], 2: [-2.0, 1.0, -4.0]},
        )
        match = self._match()

        with (
            patch.object(production, "build_state_before_match", return_value=fake_state),
            patch.object(production.base, "training_summary", return_value={"draw_rate": 0.05}),
            patch.object(production.base, "average", side_effect=lambda values: sum(values) / len(values) if values else None),
            patch.object(production.base, "feature_cutoff_date", return_value=None),
            patch.object(production, "context_rest_days", return_value=None),
            patch.object(production, "head_to_head_context", return_value=None),
            patch.object(production, "data_quality_issues_for_prediction", return_value=[]),
            patch.object(
                production,
                "make_champion_prediction",
                side_effect=[probability_result, margin_result],
            ) as routed_prediction,
        ):
            result = production.build_prediction(
                match,
                [match.match],
                champions,
                sheets=set(),
                generated_at=SimpleNamespace(),
            )

        self.assertEqual(routed_prediction.call_count, 2)

        # Probability fields must come only from the probability champion.
        self.assertAlmostEqual(result.home_win_probability, 0.70)
        self.assertAlmostEqual(result.draw_probability, 0.05)
        self.assertAlmostEqual(result.away_win_probability, 0.25)

        # Margin must come only from the margin champion.
        self.assertAlmostEqual(result.predicted_home_margin, 12.5)

        # Stored champion metadata must remain aligned to the values used.
        self.assertEqual(result.probability_champion.model_version_id, 101)
        self.assertEqual(result.margin_champion.model_version_id, 202)

    def test_same_champion_reuses_one_prediction(self):
        champion = self._champion(
            production.PROBABILITY_TARGET, 1, "EloOnlyBaseline"
        )
        margin_champion = production.Champion(
            target_type=production.MARGIN_TARGET,
            model_version_id=1,
            model_name="EloOnlyBaseline",
            model_version="v0.2.0",
        )
        champions = {
            production.PROBABILITY_TARGET: champion,
            production.MARGIN_TARGET: margin_champion,
        }

        shared_result = self._prediction(0.60, 0.04, 0.36, 6.5)
        fake_state = SimpleNamespace(
            ratings={1: 1600.0, 2: 1500.0},
            rolling_margins={1: [1.0, 2.0, 3.0], 2: [0.0, -1.0, 2.0]},
        )
        match = self._match()

        with (
            patch.object(production, "build_state_before_match", return_value=fake_state),
            patch.object(production.base, "training_summary", return_value={"draw_rate": 0.04}),
            patch.object(production.base, "average", side_effect=lambda values: sum(values) / len(values) if values else None),
            patch.object(production.base, "feature_cutoff_date", return_value=None),
            patch.object(production, "context_rest_days", return_value=None),
            patch.object(production, "head_to_head_context", return_value=None),
            patch.object(production, "data_quality_issues_for_prediction", return_value=[]),
            patch.object(
                production,
                "make_champion_prediction",
                return_value=shared_result,
            ) as routed_prediction,
        ):
            result = production.build_prediction(
                match,
                [match.match],
                champions,
                sheets=set(),
                generated_at=SimpleNamespace(),
            )

        self.assertEqual(routed_prediction.call_count, 1)
        self.assertAlmostEqual(result.home_win_probability, 0.60)
        self.assertAlmostEqual(result.predicted_home_margin, 6.5)

    def test_unsupported_active_champion_fails_closed(self):
        champion = self._champion(
            production.MARGIN_TARGET,
            999,
            "FutureUnsupportedModel",
            "v9.9.9",
        )

        match = self._match().match
        fake_state = SimpleNamespace()

        with patch.object(production.base, "MODEL_NAMES", {"EloOnlyBaseline"}):
            with self.assertRaisesRegex(
                RuntimeError,
                "not supported by the production prediction engine",
            ):
                production.make_champion_prediction(
                    champion,
                    match,
                    fake_state,
                    summary={},
                )


if __name__ == "__main__":
    unittest.main()
