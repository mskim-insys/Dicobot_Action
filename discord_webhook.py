"""
discord_webhook.py (하위 호환성 래퍼)
실제 구현은 common/discord_webhook.py로 모듈화되었습니다.
"""

from common.discord_webhook import (
    build_discord_embed,
    build_news_embed,
    build_notice_embed,
    send_batch_notices,
    send_news_webhook,
    send_notice_webhook,
    send_raw_webhook,
)
