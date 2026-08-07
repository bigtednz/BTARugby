import unittest
from datetime import date, datetime

import pandas as pd

from webapp.presentation import (
    average_prediction_confidence,
    filter_fixtures,
    fixture_url,
    format_kickoff,
    format_margin,
    format_prediction_comparison,
    format_result,
    format_result_winner,
    highest_outcome_probability,
    safe_error_message,
    sort_fixtures,
)


def frame():
    return pd.DataFrame([
        {
            "MatchID": 2,
            "Season": 2026,
            "Round": "Round 2",
            "MatchDate": date(2026, 8, 7),
            "KickoffDateTimeLocal": datetime(2026, 8, 7, 17, 5),
            "KickoffTimeKnownFlag": True,
            "KickoffTimeStatus": "Confirmed",
            "HomeTeam": "Canterbury",
            "AwayTeam": "Waikato",
            "HomeWinProbability": 0.35,
            "DrawProbability": 0.05,
            "AwayWinProbability": 0.60,
            "PredictedHomeMargin": -5.2,
            "ConfidenceLevel": "Moderate",
        },
        {
            "MatchID": 1,
            "Season": 2026,
            "Round": "Round 1",
            "MatchDate": date(2026, 8, 6),
            "KickoffDateTimeLocal": datetime(2026, 8, 6, 19, 10),
            "KickoffTimeKnownFlag": True,
            "KickoffTimeStatus": "Confirmed",
            "HomeTeam": "Waikato",
            "AwayTeam": "Otago",
            "HomeWinProbability": 0.55,
            "DrawProbability": 0.04,
            "AwayWinProbability": 0.41,
            "PredictedHomeMargin": 3.3,
            "ConfidenceLevel": "Low",
        },
        {
            "MatchID": 3,
            "Season": 2025,
            "Round": "Round 1",
            "MatchDate": date(2025, 8, 8),
            "KickoffDateTimeLocal": None,
            "KickoffTimeKnownFlag": False,
            "KickoffTimeStatus": "time TBC",
            "HomeTeam": "Taranaki",
            "AwayTeam": "Southland",
            "HomeWinProbability": 0.48,
            "DrawProbability": 0.04,
            "AwayWinProbability": 0.48,
            "PredictedHomeMargin": 0.01,
            "ConfidenceLevel": "Low",
        },
    ])


class PresentationTests(unittest.TestCase):
    def test_highest_outcome_probability_and_average(self):
        rows = frame()
        self.assertEqual(highest_outcome_probability(rows.iloc[0].to_dict()), 0.60)
        self.assertAlmostEqual(average_prediction_confidence(rows), (0.60 + 0.55 + 0.48) / 3)

    def test_team_filter_matches_home_and_away(self):
        rows = frame()
        self.assertEqual(set(filter_fixtures(rows, team="Waikato")["MatchID"]), {1, 2})
        self.assertEqual(set(filter_fixtures(rows, team="Otago")["MatchID"]), {1})

    def test_season_round_confidence_and_date_filters(self):
        rows = frame()
        self.assertEqual(list(filter_fixtures(rows, season=2025)["MatchID"]), [3])
        self.assertEqual(set(filter_fixtures(rows, round_name="Round 1")["MatchID"]), {1, 3})
        self.assertEqual(set(filter_fixtures(rows, confidence="Moderate")["MatchID"]), {2})
        self.assertEqual(set(filter_fixtures(rows, date_start="2026-08-06", date_end="2026-08-06")["MatchID"]), {1})

    def test_clear_filter_equivalent_values_return_sorted_rows(self):
        rows = filter_fixtures(frame(), season="All", round_name="All", team="All", confidence="All")
        self.assertEqual(list(rows["MatchID"]), [3, 1, 2])

    def test_margin_display(self):
        rows = frame()
        self.assertEqual(format_margin(rows.iloc[1].to_dict()), "Waikato by 3.3")
        self.assertEqual(format_margin(rows.iloc[0].to_dict()), "Waikato by 5.2")
        self.assertEqual(format_margin(rows.iloc[2].to_dict()), "Effectively even")

    def test_result_display(self):
        row = {"HomeTeam": "North Harbour", "AwayTeam": "Counties Manukau", "HomeScore": 28, "AwayScore": 34}
        self.assertEqual(format_result(row), "28-34")
        self.assertEqual(format_result_winner(row), "Counties Manukau won by 6")
        self.assertEqual(format_result_winner({**row, "HomeScore": 20, "AwayScore": 20}), "Draw")
        self.assertEqual(format_result({**row, "HomeScore": 0, "AwayScore": 0}), "0-0")
        self.assertEqual(format_result({**row, "HomeScore": 0, "AwayScore": 0, "ResultReadyFlag": 0, "ScoreStatus": "Pending"}), "Awaiting result")
        self.assertEqual(format_result_winner({**row, "HomeScore": 0, "AwayScore": 0}), "Draw")

    def test_prediction_comparison_display(self):
        row = {"PredictedWinner": "Waikato", "PredictedHomeMargin": 3.25, "CorrectWinner": True}
        self.assertEqual(format_prediction_comparison(row), "Predicted Waikato by 3.2 - right winner")
        self.assertEqual(format_prediction_comparison({**row, "CorrectWinner": False}), "Predicted Waikato by 3.2 - wrong winner")
        self.assertEqual(format_prediction_comparison({}), "Production prediction unavailable")

    def test_kickoff_display_never_manufactures_midnight(self):
        rows = frame()
        self.assertEqual(format_kickoff(rows.iloc[1].to_dict()), "Thu 6 Aug, 7:10 PM")
        self.assertEqual(format_kickoff(rows.iloc[2].to_dict()), "Fri 8 Aug - time TBC")

    def test_fixture_sorting_and_url_generation(self):
        rows = sort_fixtures(frame())
        self.assertEqual(list(rows["MatchID"]), [3, 1, 2])
        self.assertEqual(fixture_url(950775), "/match/950775")
        self.assertEqual(fixture_url(None), "/")

    def test_safe_error_message_hides_connection_details(self):
        message = safe_error_message(Exception("DRIVER={x};SERVER=BIGTEDS;DATABASE=RugbyAnalytics"))
        self.assertNotIn("BIGTEDS", message)
        self.assertIn("database", message)


if __name__ == "__main__":
    unittest.main()
