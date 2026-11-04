import os
import unittest
from unittest.mock import patch

from crawlers.koneps import (
    filter_bid_notices,
    get_koneps_tag_keywords,
    get_notice_webhook_routes,
)


class FilterBidNoticesTests(unittest.TestCase):
    def test_tag_keywords_can_be_overridden(self):
        with patch.dict(os.environ, {"KONEPS_MANUFACTURING_KEYWORDS": "robot, vision"}):
            tag_keywords = get_koneps_tag_keywords()

        self.assertEqual(tag_keywords["manufacturing"], ["robot", "vision"])

    def test_matches_multiple_tag_groups_and_keeps_keywords(self):
        notice = {"bidNtceNm": "외국인 근로자 근태관리 및 작업자 안전 시스템 구축"}
        tag_keywords = {
            "foreign_worker": ["외국인 근로자", "근태관리"],
            "industrial_safety": ["작업자 안전"],
        }

        filtered = filter_bid_notices([notice], keywords=[], tag_keywords=tag_keywords)

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["matched_tag_ids"], ["foreign_worker", "industrial_safety"])
        self.assertEqual(
            filtered[0]["matched_keywords"],
            ["외국인 근로자", "근태관리", "작업자 안전"],
        )

    def test_unclassified_notice_can_still_match_general_keyword(self):
        notice = {"bidNtceNm": "AI 데이터 플랫폼 구축"}
        tag_keywords = {"manufacturing": ["외관검사"]}

        filtered = filter_bid_notices([notice], keywords=["AI", "데이터"], tag_keywords=tag_keywords)

        self.assertEqual(filtered[0]["matched_tag_ids"], [])


class NoticeWebhookRoutesTests(unittest.TestCase):
    def test_sends_to_each_matching_group_channel(self):
        env = {
            "DISCORD_KONEPS_MANUFACTURING_WEBHOOK_URL": "https://discord.com/api/webhooks/manufacturing",
            "DISCORD_KONEPS_INDUSTRIAL_SAFETY_WEBHOOK_URL": "https://discord.com/api/webhooks/safety",
        }
        with patch.dict(os.environ, env):
            routes = get_notice_webhook_routes(
                {"matched_tag_ids": ["manufacturing", "industrial_safety"]},
                "https://discord.com/api/webhooks/default",
            )

        self.assertEqual(
            routes,
            {
                "https://discord.com/api/webhooks/manufacturing": ["koneps_manufacturing"],
                "https://discord.com/api/webhooks/safety": ["koneps_industrial_safety"],
            },
        )

    def test_uses_default_and_deduplicates_shared_channel(self):
        with patch.dict(os.environ, {}, clear=True):
            routes = get_notice_webhook_routes(
                {"matched_tag_ids": ["manufacturing", "industrial_safety"]},
                "https://discord.com/api/webhooks/default",
            )

        self.assertEqual(
            routes,
            {
                "https://discord.com/api/webhooks/default": [
                    "koneps_manufacturing",
                    "koneps_industrial_safety",
                ]
            },
        )

    def test_unclassified_notice_uses_default_channel(self):
        routes = get_notice_webhook_routes({}, "https://discord.com/api/webhooks/default")

        self.assertEqual(
            routes,
            {"https://discord.com/api/webhooks/default": ["koneps"]},
        )

    def test_missing_default_does_not_route_to_an_unconfigured_group(self):
        with patch.dict(os.environ, {}, clear=True):
            routes = get_notice_webhook_routes(
                {"matched_tag_ids": ["manufacturing"]},
                "",
            )

        self.assertEqual(routes, {})


if __name__ == "__main__":
    unittest.main()
