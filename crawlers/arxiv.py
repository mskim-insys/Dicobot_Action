"""
crawlers/arxiv.py
Arxiv 최신 AI & 컴퓨터 비전(cs.AI + cs.CV) 논문 수집기 모듈
"""

import argparse
import html
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import feedparser

from common.discord_webhook import build_paper_embed, send_raw_webhook
from common.history import HistoryManager

logger = logging.getLogger(__name__)

# 기본 피드: cs.AI + cs.CV 통합 RSS
DEFAULT_ARXIV_RSS_URL = "https://rss.arxiv.org/rss/cs.ai+cs.cv"


def parse_arxiv_entry(entry: Any) -> Dict[str, Any]:
    """Arxiv RSS 엔트리에서 핵심 필드(제목, 초록, 저자, 링크, PDF 등)를 정제 추출합니다."""
    link = entry.get("link", "").strip()
    title = entry.get("title", "제목 없음").strip()
    # arXiv 제목에 붙은 버전/ID 접두사 정리 (있을 경우)
    title = re.sub(r"^(Updates on arXiv\.org|arXiv:[^\s]+)\s*", "", title).strip()

    raw_desc = entry.get("description", "")
    # "Abstract: ..." 부분 분리 추출
    abs_match = re.search(r"Abstract:\s*(.*)", raw_desc, re.DOTALL)
    if abs_match:
        abstract = abs_match.group(1).strip()
    else:
        # Abstract 접두사가 없으면 arXiv 태그 제거 후 본문 사용
        clean_desc = re.sub(r"arXiv:[^\n]+\n", "", raw_desc).strip()
        abstract = clean_desc

    abstract = html.unescape(abstract)

    # 저자 목록 추출
    authors_raw = entry.get("author") or ""
    if not authors_raw and "authors" in entry:
        authors_list = [a.get("name", "") for a in entry.get("authors", []) if a.get("name")]
    elif authors_raw:
        # 콤마로 구분된 저자 분리
        authors_list = [a.strip() for a in authors_raw.split(",") if a.strip()]
    else:
        authors_list = []

    # 분야 태그 (cs.AI, cs.CV 등)
    tags = [t.get("term") for t in entry.get("tags", []) if t.get("term")]
    category = ", ".join(tags) if tags else "cs.AI / cs.CV"

    # PDF 직링크 생성
    pdf_url = link.replace("/abs/", "/pdf/")
    if not pdf_url.endswith(".pdf"):
        pdf_url += ".pdf"

    return {
        "id": link,
        "title": title,
        "url": link,
        "abstract": abstract,
        "authors": authors_list,
        "category": category,
        "pdf_url": pdf_url,
    }


def fetch_arxiv_papers(
    rss_url: Optional[str] = None,
    limit: int = 5,
    keywords: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Arxiv RSS 피드를 조회하여 최신 논문 목록을 가져옵니다.
    """
    target_url = rss_url or os.getenv("ARXIV_RSS_URL", DEFAULT_ARXIV_RSS_URL).strip()
    logger.info("[Arxiv] 피드 조회 중: %s", target_url)

    try:
        feed = feedparser.parse(target_url)
        if feed.bozo and not feed.entries:
            logger.warning("[Arxiv] 피드 파싱 실패 또는 빈 응답: %s", feed.get("bozo_exception"))
            return []

        entries = feed.entries
        logger.info("[Arxiv] 전체 수집된 최신 논문: %d건", len(entries))

        cleaned_keywords = [k.strip().lower() for k in keywords] if keywords else []

        matched_papers: List[Dict[str, Any]] = []
        for entry in entries:
            paper = parse_arxiv_entry(entry)

            # 키워드 필터링 적용 (키워드가 지정된 경우)
            if cleaned_keywords:
                search_target = f"{paper['title']} {paper['abstract']}".lower()
                matched = [k for k in cleaned_keywords if k in search_target]
                if not matched:
                    continue
                paper["matched_keywords"] = matched

            matched_papers.append(paper)
            if len(matched_papers) >= limit:
                break

        logger.info("[Arxiv] 최종 선정된 논문: %d건 (상위 %d건 제한)", len(matched_papers), limit)
        return matched_papers
    except Exception as e:
        logger.error("[Arxiv] RSS 수집 중 예외 발생: %s", e)
        return []


def run_arxiv(
    args: argparse.Namespace,
    webhook_url: str,
    history_mgr: HistoryManager,
) -> int:
    """
    Arxiv 최신 논문 브리핑 파이프라인 실행 진입점
    """
    logger.info("--- [AI / 컴퓨터 비전 논문 (Arxiv)] 수집 시작 ---")

    # 1. 전송 채널 웹훅 결정 (논문 전용 웹훅 우선, 없으면 공통 웹훅)
    arxiv_webhook = os.getenv("DISCORD_ARXIV_WEBHOOK_URL", "").strip() or webhook_url
    if not arxiv_webhook and not getattr(args, "dry_run", False):
        logger.warning("[Arxiv] 전송할 디스코드 웹훅 URL이 설정되지 않았습니다.")
        return 0

    limit = int(os.getenv("ARXIV_LIMIT", "5"))

    # 2. 키워드 필터 설정 (선택 사항)
    raw_keywords = os.getenv("ARXIV_KEYWORDS", "").strip()
    keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()] if raw_keywords else None
    if keywords:
        logger.info("[Arxiv] 키워드 필터 적용 중 (%d개): %s", len(keywords), ", ".join(keywords))

    # 3. 논문 수집 (기존 전송 이력 체크를 위해 조금 더 넉넉하게 긁은 뒤 중복 제외)
    candidates = fetch_arxiv_papers(limit=limit * 3 if not getattr(args, "force", False) else limit, keywords=keywords)
    if not candidates:
        logger.info("[Arxiv] 조건에 부합하는 새로운 논문이 없습니다.")
        return 0

    # 4. 중복 확인
    to_send: List[Dict[str, Any]] = []
    for paper in candidates:
        paper_id = paper.get("id") or paper.get("url")
        if not getattr(args, "force", False) and history_mgr.is_sent("arxiv", paper_id):
            continue
        to_send.append(paper)
        if len(to_send) >= limit:
            break

    logger.info("[Arxiv] 신규 전송 대상: %d건 (이전 전송 건 제외, 최대 %d건)", len(to_send), limit)

    # 5. Dry-run 모드
    if getattr(args, "dry_run", False):
        logger.info("[Dry Run] 디스코드 전송 생략 (콘솔 출력):")
        for idx, p in enumerate(to_send, 1):
            print(f"  [{idx}] [{p['category']}] {p['title']}")
            print(f"      - 링크: {p['url']}")
            print(f"      - PDF: {p['pdf_url']}")
        return len(to_send)

    # 6. 디스코드 전송
    sent_count = 0
    for paper in to_send:
        embed = build_paper_embed(paper)
        payload = {
            "username": "Arxiv 논문 브리핑",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/3233/3233497.png",
            "embeds": [embed],
        }
        if send_raw_webhook(arxiv_webhook, payload):
            sent_count += 1
            paper_id = paper.get("id") or paper.get("url")
            history_mgr.mark_sent("arxiv", paper_id)
        time.sleep(1.0)  # 레이트 리밋 방지 간격

    logger.info("[Arxiv] 완료: %d건 중 %d건 전송 성공", len(to_send), sent_count)
    return sent_count

