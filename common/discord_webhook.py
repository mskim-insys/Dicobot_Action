"""
common/discord_webhook.py
디스코드 웹훅을 통해 깔끔한 카드형 Embed 메시지를 전송하는 공통 모듈
(나라장터 공고, 테크 트렌드 뉴스, AI/컴퓨터비전 논문 브리핑 지원)
"""

import html
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def clean_html(raw_html: Optional[str]) -> str:
    """HTML 태그 제거 및 엔티티 언이스케이프"""
    if not raw_html:
        return ""
    # 태그 제거
    clean = re.sub(r"<[^>]+>", " ", raw_html)
    # 공백 정규화 및 HTML 특수문자 변환 (&amp; 등)
    clean = html.unescape(clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


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


# ==============================================================
# 1. 나라장터 공고 카드 포맷터
# ==============================================================
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
    org_display = instt_nm if instt_nm == dm_instt_nm else f"{instt_nm} (수요: {dm_instt_nm})"

    return {
        "title": f"📋 {title[:240]}",
        "url": url,
        "color": 0x3498DB,  # 블루 톤
        "fields": [
            {"name": "🏛️ 공고 / 수요기관", "value": org_display, "inline": False},
            {"name": "💰 배정예산 / 추정가격", "value": f"**{formatted_price}**", "inline": True},
            {"name": "⏰ 입찰 마감일시", "value": bid_clse_dt, "inline": True},
            {"name": "🏷️ 매칭 키워드", "value": keyword_tags, "inline": False},
            {"name": "📅 공고 등록일시", "value": bid_ntce_dt, "inline": True},
            {"name": "🔗 바로가기", "value": f"[나라장터 공고 상세 페이지 열기]({url})", "inline": True},
        ],
        "footer": {"text": f"나라장터 알리미 | 공고번호 {bid_no}-{bid_ord}"},
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
    payload = {"username": bot_name, "avatar_url": avatar_url, "embeds": [embed]}
    return send_raw_webhook(webhook_url, payload)


# ==============================================================
# 2. 테크 뉴스 및 트렌드 카드 포맷터 (GeekNews, Hacker News 등)
# ==============================================================
def build_tech_trend_embed(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    국내외 테크 트렌드/뉴스 아이템을 디스코드 Embed로 포맷팅합니다.
    (비용 절감을 위해 LLM 요약 없이 원문 링크와 요약 스니펫 제공)
    """
    title = clean_html(item.get("title", "제목 없음"))
    url = item.get("url") or item.get("link", "https://news.hada.io")
    source = item.get("source", "테크 트렌드")
    summary = clean_html(item.get("summary") or item.get("description", ""))
    published = item.get("published_at") or item.get("published", "")
    author = item.get("author", "")

    # 글자 수 제한 및 마크다운 정돈
    desc = summary[:320] + ("..." if len(summary) > 320 else "") if summary else "본문 요약이 제공되지 않는 기사입니다. 바로가기 링크를 참조하세요."

    # 출처별 테마 색상 (GeekNews: 주황, HackerNews: 다홍, 일반: 에메랄드)
    color_map = {
        "GeekNews": 0xF39C12,
        "HackerNews": 0xFF6600,
        "TechNews": 0x2ECC71,
    }
    color = color_map.get(source, 0x1ABC9C)

    fields = [
        {"name": "🏢 출처", "value": f"**{source}**" + (f" ({author})" if author else ""), "inline": True},
        {"name": "🔗 원문 보기", "value": f"[기사 링크 열기]({url})", "inline": True},
    ]

    # 추가 메타데이터가 있는 경우 (예: HackerNews 포인트, 댓글수)
    if "points" in item or "comments" in item:
        pts = item.get("points", 0)
        cmts = item.get("comments", 0)
        fields.append({"name": "🔥 반응", "value": f"추천 {pts}개 | 댓글 {cmts}개", "inline": True})

    return {
        "title": f"🔥 [{source}] {title[:220]}",
        "url": url,
        "description": desc,
        "color": color,
        "fields": fields,
        "footer": {"text": f"모닝 브리핑 봇 | {published or '오늘의 소식'}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ==============================================================
# 3. AI / 컴퓨터 비전 최신 논문 카드 포맷터 (Arxiv, HuggingFace 등)
# ==============================================================
def build_paper_embed(paper: Dict[str, Any]) -> Dict[str, Any]:
    """
    최신 AI/CV 논문 정보를 디스코드 Embed로 포맷팅합니다.
    """
    title = clean_html(paper.get("title", "논문 제목 없음"))
    url = paper.get("url") or paper.get("link", "https://arxiv.org")
    category = paper.get("category", "cs.CV")
    abstract = clean_html(paper.get("abstract") or paper.get("summary", ""))
    authors = paper.get("authors") or []
    pdf_url = paper.get("pdf_url") or url.replace("/abs/", "/pdf/") + ".pdf"

    author_str = ", ".join(authors[:3]) + (" 외" if len(authors) > 3 else "") if authors else "저자 정보 없음"
    desc = abstract[:320] + ("..." if len(abstract) > 320 else "") if abstract else "초록이 제공되지 않습니다."

    return {
        "title": f"📄 [{category}] {title[:220]}",
        "url": url,
        "description": desc,
        "color": 0x5865F2,  # 디스코드 인디고 퍼플
        "fields": [
            {"name": "✍️ 저자", "value": author_str, "inline": False},
            {"name": "🏷️ 분야", "value": f"`{category}`", "inline": True},
            {"name": "📥 PDF 다운로드", "value": f"[PDF 바로 열기]({pdf_url})", "inline": True},
        ],
        "footer": {"text": "Arxiv AI 논문 브리핑"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def send_briefing_webhook(
    webhook_url: str,
    embed: Dict[str, Any],
    bot_name: str = "모닝 브리핑 봇",
    avatar_url: Optional[str] = "https://cdn-icons-png.flaticon.com/512/3233/3233497.png",
) -> bool:
    """단일 브리핑 카드(뉴스 또는 논문)를 디스코드로 전송합니다."""
    payload = {"username": bot_name, "avatar_url": avatar_url, "embeds": [embed]}
    return send_raw_webhook(webhook_url, payload)


# 하위 호환성 유지용
build_discord_embed = build_notice_embed
build_news_embed = build_tech_trend_embed
send_news_webhook = send_briefing_webhook


def send_batch_notices(
    webhook_url: str,
    notices: List[Dict[str, Any]],
    delay_between_messages: float = 0.8,
) -> int:
    """여러 건의 공고를 순차적으로 전송하고, 성공한 건수를 반환합니다."""
    success_count = 0
    for notice in notices:
        success = send_notice_webhook(webhook_url, notice)
        if success:
            success_count += 1
        time.sleep(delay_between_messages)
    return success_count
