import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
from sqlalchemy.exc import SQLAlchemyError

from webapp.config import AppConfig
from webapp.data.repository import MatchCentreRepository, RepositoryError, assert_read_only, ensure_columns


class RepositoryTests(unittest.TestCase):
    def test_read_only_guard_rejects_writes(self):
        with self.assertRaises(ValueError):
            assert_read_only("DELETE FROM dbo.SomeTable")
        assert_read_only("SELECT * FROM dbo.vw_Gold_ProductionUpcomingPredictions")

    def test_empty_results_keep_expected_columns(self):
        rows = ensure_columns(pd.DataFrame(), ["MatchID", "HomeTeam"])
        self.assertEqual(list(rows.columns), ["MatchID", "HomeTeam"])
        self.assertTrue(rows.empty)

    @patch("webapp.data.repository.pd.read_sql_query")
    def test_upcoming_prediction_uses_parameterised_match_id(self, read_sql):
        read_sql.return_value = pd.DataFrame([{"MatchID": 950775}])
        engine = MagicMock()
        connection = engine.connect.return_value.__enter__.return_value
        repo = MatchCentreRepository(config(), engine=engine)

        result = repo.upcoming_prediction(950775)

        self.assertEqual(result.iloc[0]["MatchID"], 950775)
        self.assertEqual(read_sql.call_args.kwargs["params"], {"match_id": 950775})
        self.assertIsNotNone(connection)

    @patch("webapp.data.repository.pd.read_sql_query")
    def test_connection_failure_is_wrapped_safely(self, read_sql):
        read_sql.side_effect = SQLAlchemyError("server failed")
        repo = MatchCentreRepository(config(), engine=MagicMock())

        with self.assertRaises(RepositoryError):
            repo.upcoming_predictions()

    @patch("webapp.data.repository.pd.read_sql_query")
    def test_repository_result_handling_adds_missing_columns(self, read_sql):
        read_sql.return_value = pd.DataFrame([{"MatchID": 1}])
        repo = MatchCentreRepository(config(), engine=MagicMock())

        result = repo.upcoming_predictions()

        self.assertIn("HomeTeam", result.columns)
        self.assertEqual(result.iloc[0]["MatchID"], 1)

    @patch("webapp.data.repository.pd.read_sql_query")
    def test_completed_results_use_production_results_view(self, read_sql):
        read_sql.return_value = pd.DataFrame([{"MatchID": 950775, "HomeScore": 28, "AwayScore": 34}])
        repo = MatchCentreRepository(config(), engine=MagicMock())

        result = repo.completed_results()
        sql_text = str(read_sql.call_args.args[0])

        self.assertIn("vw_Gold_ProductionResults", sql_text)
        self.assertIn("ProductionEvaluationEligibleFlag", result.columns)
        self.assertIn("PredictionAvailableFlag", result.columns)
        self.assertEqual(result.iloc[0]["MatchID"], 950775)

    @patch("webapp.data.repository.pd.read_sql_query")
    def test_standings_use_result_ready_rows(self, read_sql):
        read_sql.return_value = pd.DataFrame([{"TeamName": "Waikato", "Played": 1}])
        repo = MatchCentreRepository(config(), engine=MagicMock())

        result = repo.standings()
        sql_text = str(read_sql.call_args.args[0])

        self.assertIn("vw_Gold_ProductionResults", sql_text)
        self.assertIn("ResultReadyFlag = 1", sql_text)
        self.assertEqual(result.iloc[0]["TeamName"], "Waikato")

    @patch("webapp.data.repository.pd.read_sql_query")
    def test_player_queries_are_read_only_sources(self, read_sql):
        read_sql.return_value = pd.DataFrame()
        repo = MatchCentreRepository(config(), engine=MagicMock())

        repo.player_appearances()
        appearances_sql = str(read_sql.call_args.args[0])
        repo.player_leaderboards()
        leaderboards_sql = str(read_sql.call_args.args[0])

        self.assertIn("Silver_PlayerAppearances", appearances_sql)
        self.assertIn("NPC_PlayerStats", leaderboards_sql)

    @patch("webapp.data.repository.pd.read_sql_query")
    def test_player_top10_uses_gold_ranked_view(self, read_sql):
        read_sql.return_value = pd.DataFrame([{"Discipline": "Carries", "CalculatedRank": 1}])
        repo = MatchCentreRepository(config(), engine=MagicMock())

        result = repo.player_top10_by_stat()
        sql_text = str(read_sql.call_args.args[0])

        self.assertIn("vw_Gold_PlayerTop10ByDiscipline", sql_text)
        self.assertEqual(result.iloc[0]["CalculatedRank"], 1)


def config():
    return AppConfig(
        sql_server="BIGTEDS",
        sql_database="RugbyAnalytics",
        sql_driver="ODBC Driver 17 for SQL Server",
        trusted_connection="yes",
        app_host="127.0.0.1",
        app_port=8050,
        app_debug=False,
        cache_ttl_seconds=300,
    )


if __name__ == "__main__":
    unittest.main()
