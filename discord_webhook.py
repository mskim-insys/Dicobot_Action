"""
discord_webhook.py
디스코드 웹훅을 통해 깔끔한 카드형 Embed 메시지를 전송하는 모듈
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def build_discord_embed(notice: Dict[str, Any]) -> Dict[str, Any]:
    """
    공고 딕셔너리를 디스코드 Embed 카드 JSON 구조로 변환합니다.
    """
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

    # 태그 형태 문자열 생성
    keyword_tags = " ".join([f"`#{kw}`" for kw in matched_keywords]) if matched_keywords else "`#공고`"

    # 기관 정보 요약
    if instt_nm == dm_instt_nm:
        org_display = instt_nm
    else:
        org_display = f"{instt_nm} (수요: {dm_instt_nm})"

    embed = {
        "title": f"📋 {title[:240]}",
        "url": url,
        "color": 0x3498DB,  # 세련된 블루 톤
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

    return embed


def send_notice_webhook(
    webhook_url: str,
    notice: Dict[str, Any],
    bot_name: str = "나라장터 알리미",
    avatar_url: Optional[str] = "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
) -> bool:
    """
    단일 공고 Embed를 디스코드 웹훅으로 전송합니다.
    """
    if not webhook_url or not webhook_url.startswith("https://"):
        raise ValueError("유효한 DISCORD_WEBHOOK_URL이 설정되지 않았습니다.")

    embed = build_discord_embed(notice)
    payload = {
        "username": bot_name,
        "avatar_url": avatar_url,
        "embeds": [embed],
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code == 429:
            # 레이트 리밋 발생 시 대기 후 재시도
            retry_after = response.json().get("retry_after", 1.5)
            logger.warning("Discord 레이트 리밋 감지. %.2f초 대기 후 재시도합니다.", retry_after)
            time.sleep(retry_after)
            response = requests.post(webhook_url, json=payload, timeout=10)

        response.raise_for_status()
        return True
    except Exception as e:
        logger.error("웹훅 전송 실패 (공고번호: %s): %s", notice.get("bidNtceNo"), e)
        return False


def send_batch_notices(
    webhook_url: str,
    notices: List[Dict[str, Any]],
    delay_between_messages: float = 0.8,
) -> int:
    """
    여러 건의 공고를 순차적으로 전송하고, 성공한 건수를 반환합니다.
    디스코드 레이트 리밋 방지를 위해 메시지 간 딜레이를 둡니다.
    """
    success_count = 0
    for notice in notices:
        success = send_notice_webhook(webhook_url, notice)
        if success:
            success_count += 1
        time.sleep(delay_between_messages)
    return success_count

