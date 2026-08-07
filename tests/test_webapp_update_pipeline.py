import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from webapp.config import AppConfig
from webapp.data.update_pipeline import build_update_steps, format_update_result, run_update_pipeline


class UpdatePipelineTests(unittest.TestCase):
    def test_default_plan_rebuilds_local_sql_layers_without_scraper(self):
        steps = build_update_steps(config())
        commands = [" ".join(step.command) for step in steps]

        self.assertNotIn("rugbypass_scraper", " ".join(commands))
        self.assertIn("analytics/backfill_result_lifecycle.py --season 2026", commands[0])
        self.assertTrue(any("database/load_npc_to_silver.sql" in command for command in commands))
        self.assertTrue(commands[-1].endswith("analytics/run_production_predictions.py --replace --season 2026"))

    def test_scraper_can_be_included_by_configuration(self):
        steps = build_update_steps(config(data_update_run_scraper=True))

        self.assertIn("rugbypass_scraper/rugbypass_scraper/scraper.py", " ".join(steps[0].command))

    @patch("webapp.data.update_pipeline.subprocess.run")
    def test_pipeline_runs_allowlisted_steps(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = "ok"
        run.return_value.stderr = ""

        result = run_update_pipeline(config(data_update_run_predictions=False), root=Path("D:/Cursor/BTA_Rugby"))

        self.assertTrue(result.succeeded)
        self.assertEqual(run.call_count, 4)
        for call in run.call_args_list:
            self.assertIsInstance(call.args[0], list)
            self.assertEqual(call.kwargs["cwd"], Path("D:/Cursor/BTA_Rugby"))

    def test_status_text_is_safe_and_short(self):
        result = format_update_result(
            type(
                "Result",
                (),
                {
                    "succeeded": True,
                    "finished_at": datetime(2026, 8, 7, 22, 0),
                    "message": "Latest data update complete (5 steps).",
                },
            )()
        )

        self.assertIn("Succeeded", result)
        self.assertIn("Latest data update complete", result)


def config(**overrides):
    values = {
        "sql_server": "BIGTEDS",
        "sql_database": "RugbyAnalytics",
        "sql_driver": "ODBC Driver 17 for SQL Server",
        "trusted_connection": "yes",
        "app_host": "127.0.0.1",
        "app_port": 8050,
        "app_debug": False,
        "cache_ttl_seconds": 300,
    }
    values.update(overrides)
    return AppConfig(**values)


if __name__ == "__main__":
    unittest.main()
