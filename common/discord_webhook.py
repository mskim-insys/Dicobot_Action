"""
common/discord_webhook.py
디스코드 웹훅을 통해 깔끔한 카드형 Embed 메시지를 전송하는 공통 모듈
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def send_raw_webhook(webhook_url: str, payload: Dict[str, Any]) -> bool:
    """디스코드 웹훅으로 원시 페이로드를 전송합니다 (레이트 리밋 대응 포함)."""
    if not webhook_url or not webhook_url.startswith("https://"):
        raise ValueError("유효한 DISCORD_WEBHOOK_URL이 설정되지 않았습니다.")

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code == 429:
            retry_after = response.json().get("retry_after", 1.5)
            logger.warning("Discord 레이트 리밋 감지. %.2f초 대기 후 재시도합니다.", retry_after)
            time.sleep(retry_after)
            response = requests.post(webhook_url, json=payload, timeout=10)

        response.raise_for_status()
        return True
    except Exception as e:
        logger.error("디스코드 웹훅 전송 실패: %s", e)
        return False


def build_notice_embed(notice: Dict[str, Any]) -> Dict[str, Any]:
    """나라장터 공고 딕셔너리를 디스코드 Embed 카드 JSON 구조로 변환합니다."""
    title = notice.get("bidNtceNm", "공고명 없음")
    url = notice.get("bidNtceDtlUrl", "https://www.g2b.go.kr")
    instt_nm = notice.get("ntceInsttNm") or "기관 미상"
    dm_instt_nm = notice.get("dminsttNm") or instt_nm
    formatted_price = notice.get("formatted_price", "별도 협의")
    bid_clse_dt = notice.get("bidClseDt", "일정 확인 필요")
    bid_ntce_dt = notice.get("bidNtceDt", "-")
    bid_no = notice.get("bidNtceNo", "-")
    bid_ord = notice.get("bidNtceOrd", "00")
    matched_keywords = notice.get("matched_keywords", [])

    keyword_tags = " ".join([f"`#{kw}`" for kw in matched_keywords]) if matched_keywords else "`#공고`"

    if instt_nm == dm_instt_nm:
        org_display = instt_nm
    else:
        org_display = f"{instt_nm} (수요: {dm_instt_nm})"

    return {
        "title": f"📋 {title[:240]}",
        "url": url,
        "color": 0x3498DB,  # 블루 톤
        "fields": [
            {
                "name": "🏛️ 공고 / 수요기관",
                "value": org_display,
                "inline": False,
            },
            {
                "name": "💰 배정예산 / 추정가격",
                "value": f"**{formatted_price}**",
                "inline": True,
            },
            {
                "name": "⏰ 입찰 마감일시",
                "value": bid_clse_dt,
                "inline": True,
            },
            {
                "name": "🏷️ 매칭 키워드",
                "value": keyword_tags,
                "inline": False,
            },
            {
                "name": "📅 공고 등록일시",
                "value": bid_ntce_dt,
                "inline": True,
            },
            {
                "name": "🔗 바로가기",
                "value": f"[나라장터 공고 상세 페이지 열기]({url})",
                "inline": True,
            },
        ],
        "footer": {
            "text": f"나라장터 알리미 | 공고번호 {bid_no}-{bid_ord}",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def send_notice_webhook(
    webhook_url: str,
    notice: Dict[str, Any],
    bot_name: str = "나라장터 알리미",
    avatar_url: Optional[str] = "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
) -> bool:
    """나라장터 단일 공고 카드를 디스코드로 전송합니다."""
    embed = build_notice_embed(notice)
    payload = {
        "username": bot_name,
        "avatar_url": avatar_url,
        "embeds": [embed],
    }
    return send_raw_webhook(webhook_url, payload)


def build_news_embed(news_item: Dict[str, Any]) -> Dict[str, Any]:
    """뉴스 딕셔너리를 디스코드 Embed 카드 JSON 구조로 변환합니다."""
    title = news_item.get("title", "뉴스 제목 없음")
    url = news_item.get("url", "https://news.naver.com")
    press = news_item.get("press", "언론사")
    summary = news_item.get("summary", "")
    published_at = news_item.get("published_at", "")
    thumbnail_url = news_item.get("thumbnail_url")
    matched_keywords = news_item.get("matched_keywords", [])

    keyword_tags = " ".join([f"`#{kw}`" for kw in matched_keywords]) if matched_keywords else "`#뉴스`"

    embed: Dict[str, Any] = {
        "title": f"📰 {title[:240]}",
        "url": url,
        "description": summary[:300] if summary else None,
        "color": 0x2ECC71,  # 그린 톤
        "fields": [
            {
                "name": "🏢 언론사 / 출처",
                "value": press,
                "inline": True,
            },
            {
                "name": "🏷️ 키워드",
                "value": keyword_tags,
                "inline": True,
            },
        ],
        "footer": {
            "text": f"디스코드 뉴스 알리미 | {published_at}",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if thumbnail_url:
        embed["thumbnail"] = {"url": thumbnail_url}

    return embed


def send_news_webhook(
    webhook_url: str,
    news_item: Dict[str, Any],
    bot_name: str = "디스코드 뉴스 알리미",
    avatar_url: Optional[str] = "https://cdn-icons-png.flaticon.com/512/2965/2965879.png",
) -> bool:
    """단일 뉴스 카드를 디스코드로 전송합니다."""
    embed = build_news_embed(news_item)
    payload = {
        "username": bot_name,
        "avatar_url": avatar_url,
        "embeds": [embed],
    }
    return send_raw_webhook(webhook_url, payload)


# 기존 코드 호환성용 alias
build_discord_embed = build_notice_embed

