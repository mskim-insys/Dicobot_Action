import os
import unittest
from unittest.mock import patch

from main import get_webhook


class HuggingFaceWebhookRoutingTests(unittest.TestCase):
    def test_prefers_huggingface_webhook(self):
        env = {
            "DISCORD_HUGGINGFACE_WEBHOOK_URL": "https://discord.com/api/webhooks/hf",
            "DISCORD_ARXIV_WEBHOOK_URL": "https://discord.com/api/webhooks/arxiv",
            "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/common",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                get_webhook("huggingface"),
                "https://discord.com/api/webhooks/hf",
            )

    def test_falls_back_to_arxiv_then_common_webhook(self):
        with patch.dict(
            os.environ,
            {
                "DISCORD_ARXIV_WEBHOOK_URL": "https://discord.com/api/webhooks/arxiv",
                "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/common",
            },
            clear=True,
        ):
            self.assertEqual(
                get_webhook("huggingface"),
                "https://discord.com/api/webhooks/arxiv",
            )

        with patch.dict(
            os.environ,
            {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/common"},
            clear=True,
        ):
            self.assertEqual(
                get_webhook("huggingface"),
                "https://discord.com/api/webhooks/common",
            )


if __name__ == "__main__":
    unittest.main()
