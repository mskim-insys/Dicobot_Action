"""
crawlers/news.py
디스코드 뉴스 알리미 수집기 모듈 (기획서 반영 대기 템플릿)
"""

import argparse
import logging
import os
from typing import Any, Dict, List

from common.discord_webhook import send_news_webhook
from common.history import HistoryManager

logger = logging.getLogger(__name__)


def run_news(
    args: argparse.Namespace,
    webhook_url: str,
    history_mgr: HistoryManager,
) -> int:
    """
    IT / AI 뉴스 수집 파이프라인 실행 진입점.
    사용자의 기획서(네이버 뉴스 API, IT 포털 RSS, 크롤링 등)에 맞춰 구현될 예정입니다.
    """
    logger.info("--- [뉴스 봇] 수집 시작 ---")

    # 뉴스 전용 웹훅 URL이 별도 지정되어 있다면 우선 사용, 없으면 공통 웹훅 사용
    news_webhook_url = os.getenv("DISCORD_NEWS_WEBHOOK_URL", "").strip() or webhook_url
    if not news_webhook_url:
        logger.warning("[뉴스 봇] 웹훅 URL이 없어 건너뜁니다.")
        return 0

    # 기획서가 오기 전 임시 안내 로그
    logger.info("[뉴스 봇] 🚀 뉴스봇 기획서 대기 중입니다. 기획서가 전달되면 즉시 수집 로직이 연동됩니다.")

    # 아래는 구조 예시:
    # 1. 뉴스 데이터 수집 (네이버 뉴스 API / GeekNews / IT World 등)
    # 2. 키워드 필터링
    # 3. history_mgr.is_sent("news", news_url) 로 중복 체크
    # 4. send_news_webhook(news_webhook_url, news_item) 으로 전송
    # 5. history_mgr.mark_sent("news", news_url)

    return 0

