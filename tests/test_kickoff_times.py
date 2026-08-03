import unittest
from datetime import datetime

from analytics.kickoff_times import (
    kickoff_from_match_dict,
    kickoff_from_values,
    kickoff_status,
    parse_time_value,
)
from analytics.backfill_kickoff_times import kickoff_infos_from_snapshot


class KickoffTimeTests(unittest.TestCase):
    def test_date_only_source_remains_unknown(self):
        info = kickoff_from_values("2026-10-04", None, "Not supplied by source")

        self.assertFalse(info.kickoff_time_known)
        self.assertIsNone(info.kickoff_datetime_local)
        self.assertIsNone(info.kickoff_datetime_utc)

    def test_date_only_does_not_become_midnight(self):
        info = kickoff_from_values("2026-10-04", "", "Not supplied by source")

        self.assertIsNone(info.kickoff_datetime_local)
        self.assertIsNone(info.kickoff_datetime_utc)

    def test_known_nzst_local_time_converts_to_utc(self):
        info = kickoff_from_values("2026-08-06", "19:10pm NZST", "RugbyPass")

        self.assertEqual(info.kickoff_datetime_local, datetime(2026, 8, 6, 19, 10))
        self.assertEqual(info.kickoff_datetime_utc, datetime(2026, 8, 6, 7, 10))

    def test_known_nzdt_local_time_converts_to_utc(self):
        info = kickoff_from_values("2026-10-04", "17:05pm NZDT", "RugbyPass")

        self.assertEqual(info.kickoff_datetime_local, datetime(2026, 10, 4, 17, 5))
        self.assertEqual(info.kickoff_datetime_utc, datetime(2026, 10, 4, 4, 5))

    def test_daylight_saving_transition_after_jump(self):
        info = kickoff_from_values("2026-09-27", "03:05 NZDT", "RugbyPass")

        self.assertEqual(info.kickoff_datetime_utc, datetime(2026, 9, 26, 14, 5))

    def test_rugbypass_match_dict_fields(self):
        info = kickoff_from_match_dict({
            "id": 950837,
            "dateId": "20261004",
            "time": "17:05pm NZDT",
            "timeSmall": "17:05",
            "epoch": 1791086700,
        })

        self.assertTrue(info.kickoff_time_known)
        self.assertIn("time=17:05pm NZDT", info.kickoff_time_source)
        self.assertEqual(info.match_date, "2026-10-04")

    def test_time_parser_accepts_rendered_card_time(self):
        self.assertEqual(parse_time_value("7:10pm"), (19, 10))
        self.assertEqual(parse_time_value("17:05"), (17, 5))

    def test_power_bi_view_status_output(self):
        self.assertEqual(kickoff_status(True, "RugbyPass"), "Confirmed")
        self.assertEqual(kickoff_status(False, "Not supplied by source"), "Not supplied by source")

    def test_idempotent_backfill_parses_same_snapshot_the_same_way(self):
        snapshot = (
            '<div id="current-game-days">'
            '[{"tournaments":[{"games":[{"id":950837,"dateId":"20261004",'
            '"time":"17:05pm NZDT","timeSmall":"17:05","epoch":1791086700}]}]}]'
            '</div>'
        )

        first = kickoff_infos_from_snapshot(snapshot)
        second = kickoff_infos_from_snapshot(snapshot)

        self.assertEqual(first[950837], second[950837])


if __name__ == "__main__":
    unittest.main()
