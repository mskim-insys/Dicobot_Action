"""
crawlers/hackernews.py
해커 뉴스(Hacker News) 공식 Firebase REST API 연동 및 트렌드 수집 모듈
"""

import argparse
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from common.discord_webhook import build_tech_trend_embed, send_raw_webhook
from common.history import HistoryManager

logger = logging.getLogger(__name__)

HN_BASE_URL = "https://hacker-news.firebaseio.com/v0"


def fetch_hn_item(item_id: int) -> Optional[Dict[str, Any]]:
    """단일 아이템 정보 조회 (타임아웃 5초)"""
    url = f"{HN_BASE_URL}/item/{item_id}.json"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug("[HackerNews] 아이템 %d 조회 실패: %s", item_id, e)
    return None


def fetch_hackernews_top(
    limit: int = 5,
    min_score: int = 50,
    max_scan: int = 25,
    keywords: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Hacker News 인기 스토리(/v0/topstories.json)를 조회하고 상위 랭킹 글을 파싱합니다.
    """
    story_type = os.getenv("HN_STORY_TYPE", "topstories").strip()  # topstories, beststories
    url = f"{HN_BASE_URL}/{story_type}.json"
    logger.info("[HackerNews] %s 목록 조회 중...", story_type)

    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        story_ids = resp.json()[:max_scan]
    except Exception as e:
        logger.error("[HackerNews] 목록 조회 실패: %s", e)
        return []

    logger.info("[HackerNews] 상위 %d개 스토리 세부 정보 병렬 수집 중...", len(story_ids))
    with ThreadPoolExecutor(max_workers=5) as executor:
        items = list(executor.map(fetch_hn_item, story_ids))

    valid_stories: List[Dict[str, Any]] = []
    cleaned_keywords = [k.strip().lower() for k in keywords] if keywords else []

    for it in items:
        if not it or it.get("deleted") or it.get("dead"):
            continue
        if it.get("type") != "story":
            continue

        score = it.get("score", 0)
        if score < min_score:
            continue

        title = it.get("title", "").strip()
        text = it.get("text", "") or ""

        # 키워드 필터가 설정된 경우 검사
        if cleaned_keywords:
            search_str = f"{title} {text}".lower()
            if not any(k in search_str for k in cleaned_keywords):
                continue

        hn_id = it.get("id")
        hn_url = f"https://news.ycombinator.com/item?id={hn_id}"
        out_url = it.get("url") or hn_url
        comments_cnt = it.get("descendants", 0)
        time_sec = it.get("time", 0)
        pub_dt = datetime.fromtimestamp(time_sec).strftime("%Y-%m-%d %H:%M") if time_sec else ""

        valid_stories.append({
            "id": f"hn_{hn_id}",
            "raw_id": hn_id,
            "title": title,
            "url": out_url,
            "hn_url": hn_url,
            "source": "HackerNews",
            "author": it.get("by", ""),
            "points": score,
            "comments": comments_cnt,
            "published_at": pub_dt,
            "summary": text or f"Hacker News 인기 스토리 (추천 {score}개 · 댓글 {comments_cnt}개)",
        })

        if len(valid_stories) >= limit:
            break

    logger.info("[HackerNews] 최소 추천 %d점 이상 스토리 %d건 선정", min_score, len(valid_stories))
    return valid_stories


def run_hackernews(
    args: argparse.Namespace,
    webhook_url: str,
    history_mgr: HistoryManager,
) -> int:
    """Hacker News 수집 및 디스코드 전송 파이프라인 진입점"""
    logger.info("--- [글로벌 테크 / Hacker News] 수집 시작 ---")

    # 전용 웹훅 우선, 없으면 뉴스 공통 웹훅, 없으면 기본 웹훅
    hn_webhook = (
        os.getenv("DISCORD_HN_WEBHOOK_URL", "").strip()
        or os.getenv("DISCORD_NEWS_WEBHOOK_URL", "").strip()
        or webhook_url
    )
    if not hn_webhook and not getattr(args, "dry_run", False):
        logger.warning("[HackerNews] 전송할 디스코드 웹훅 URL이 설정되지 않았습니다.")
        return 0

    limit = int(os.getenv("HN_LIMIT", "5"))
    min_score = int(os.getenv("HN_MIN_SCORE", "50"))

    raw_keywords = os.getenv("HN_KEYWORDS", "").strip()
    keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()] if raw_keywords else None

    stories = fetch_hackernews_top(limit=limit, min_score=min_score, keywords=keywords)
    if not stories:
        logger.info("[HackerNews] 조건에 부합하는 새로운 스토리가 없습니다.")
        return 0

    # 중복 확인
    to_send: List[Dict[str, Any]] = []
    for s in stories:
        item_id = s.get("id")
        if not getattr(args, "force", False) and history_mgr.is_sent("hackernews", item_id):
            continue
        to_send.append(s)

    logger.info("[HackerNews] 신규 전송 대상: %d건 (이전 전송 건 제외)", len(to_send))

    # Dry Run
    if getattr(args, "dry_run", False):
        logger.info("[Dry Run] 디스코드 전송 생략 (콘솔 출력):")
        for idx, s in enumerate(to_send, 1):
            print(f"  [{idx}] [추천 {s['points']}개 | 댓글 {s['comments']}개] {s['title']}")
            print(f"      - 기사: {s['url']}")
            print(f"      - HN 토론: {s['hn_url']}")
        return len(to_send)

    # 전송
    sent_count = 0
    for s in to_send:
        embed = build_tech_trend_embed(s)
        payload = {
            "username": "Hacker News 트렌드",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/2111/2111432.png",
            "embeds": [embed],
        }
        if send_raw_webhook(hn_webhook, payload):
            sent_count += 1
            item_id = s.get("id")
            history_mgr.mark_sent("hackernews", item_id)
        time.sleep(1.0)

    logger.info("[HackerNews] 완료: %d건 중 %d건 전송 성공", len(to_send), sent_count)
    return sent_count

