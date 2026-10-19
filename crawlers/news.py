"""
crawlers/news.py
디스코드 테크 뉴스 및 트렌드 수집기 (GeekNews RSS 연동)
"""

import argparse
import logging
import os
import time
from typing import Any, Dict, List

import feedparser

from common.discord_webhook import build_tech_trend_embed, send_raw_webhook
from common.history import HistoryManager

logger = logging.getLogger(__name__)

GEEKNEWS_RSS_URL = "https://news.hada.io/rss/news"


def fetch_geeknews(limit: int = 5) -> List[Dict[str, Any]]:
    """
    긱뉴스(GeekNews) RSS 피드를 조회하여 최신 항목을 파싱합니다.
    """
    logger.info("[긱뉴스] RSS 피드 조회 중: %s", GEEKNEWS_RSS_URL)
    try:
        feed = feedparser.parse(GEEKNEWS_RSS_URL)
        if feed.bozo and not feed.entries:
            logger.warning("[긱뉴스] 피드 파싱 실패 또는 빈 응답: %s", feed.get("bozo_exception"))
            return []

        items: List[Dict[str, Any]] = []
        for entry in feed.entries[:limit]:
            item_id = entry.get("id") or entry.get("link", "")
            title = entry.get("title", "제목 없음").strip()
            link = entry.get("link", "")
            desc = entry.get("description", "")
            published = entry.get("published", "")

            items.append({
                "id": item_id,
                "title": title,
                "url": link,
                "summary": desc,
                "published_at": published,
                "source": "GeekNews",
                "author": entry.get("author", ""),
            })

        logger.info("[긱뉴스] 최신 글 %d건 파싱 완료", len(items))
        return items
    except Exception as e:
        logger.error("[긱뉴스] RSS 피드 수집 중 예외 발생: %s", e)
        return []


def run_news(
    args: argparse.Namespace,
    webhook_url: str,
    history_mgr: HistoryManager,
) -> int:
    """
    테크 뉴스 수집 파이프라인 메인 실행 함수 (1단계: 긱뉴스 연동)
    """
    logger.info("--- [테크 뉴스 / 긱뉴스] 수집 시작 ---")

    # 뉴스 전용 웹훅 URL이 있으면 우선 사용, 없으면 공통 웹훅 사용
    news_webhook_url = os.getenv("DISCORD_NEWS_WEBHOOK_URL", "").strip() or webhook_url
    if not news_webhook_url and not getattr(args, "dry_run", False):
        logger.warning("[뉴스 봇] 전송할 디스코드 웹훅 URL이 설정되지 않았습니다.")
        return 0

    limit = int(os.getenv("GEEKNEWS_LIMIT", "5"))
    items = fetch_geeknews(limit=limit)
    if not items:
        logger.info("[긱뉴스] 수집된 새로운 뉴스가 없습니다.")
        return 0

    # 키워드 필터링 (선택 사항: 환경변수 NEWS_KEYWORDS가 있으면 해당 키워드 포함 글만 필터링)
    raw_keywords = os.getenv("NEWS_KEYWORDS", "").strip()
    if raw_keywords:
        keywords = [k.strip().lower() for k in raw_keywords.split(",") if k.strip()]
        filtered = []
        for it in items:
            text = (it["title"] + " " + it["summary"]).lower()
            if any(k in text for k in keywords):
                filtered.append(it)
        items = filtered
        logger.info("[긱뉴스] 키워드 필터링 적용 후: %d건", len(items))

    # 중복 확인
    to_send: List[Dict[str, Any]] = []
    for it in items:
        item_id = it.get("id") or it.get("url")
        if not getattr(args, "force", False) and history_mgr.is_sent("geeknews", item_id):
            continue
        to_send.append(it)

    logger.info("[긱뉴스] 신규 전송 대상: %d건 (이전 전송 건 제외)", len(to_send))

    # Dry run 모드
    if getattr(args, "dry_run", False):
        logger.info("[Dry Run] 디스코드 전송 생략 (콘솔 출력):")
        for idx, it in enumerate(to_send, 1):
            print(f"  [{idx}] {it['title']} | {it['url']}")
        return len(to_send)

    # 디스코드 전송
    sent_count = 0
    for it in to_send:
        embed = build_tech_trend_embed(it)
        payload = {
            "username": "긱뉴스 트렌드",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/2965/2965879.png",
            "embeds": [embed],
        }
        if send_raw_webhook(news_webhook_url, payload):
            sent_count += 1
            item_id = it.get("id") or it.get("url")
            history_mgr.mark_sent("geeknews", item_id)
        time.sleep(1.0)  # 레이트 리밋 방지 간격

    logger.info("[긱뉴스] 완료: %d건 중 %d건 전송 성공", len(to_send), sent_count)
    return sent_count
