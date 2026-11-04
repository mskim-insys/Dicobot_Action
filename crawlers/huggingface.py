"""
crawlers/huggingface.py
Hugging Face Daily Papers REST API 수집기 모듈
"""

import argparse
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from common.discord_webhook import build_paper_embed, send_raw_webhook
from common.history import HistoryManager

logger = logging.getLogger(__name__)

DAILY_PAPERS_API_URL = "https://huggingface.co/api/daily_papers"


def parse_daily_paper(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Daily Papers API 항목을 공통 논문 카드 형식으로 변환합니다."""
    paper = entry.get("paper")
    if not isinstance(paper, dict):
        paper = entry

    paper_id = paper.get("id") or entry.get("id")
    title = paper.get("title") or entry.get("title")
    if not paper_id or not title:
        return None

    raw_authors = paper.get("authors") or entry.get("authors") or []
    if not isinstance(raw_authors, list):
        logger.warning("[Hugging Face] 저자 목록 형식이 올바르지 않아 저자 정보를 생략합니다.")
        raw_authors = []
    authors = [
        author.get("name", "").strip() if isinstance(author, dict) else str(author).strip()
        for author in raw_authors
    ]
    authors = [author for author in authors if author]

    paper_url = f"https://huggingface.co/papers/{paper_id}"
    return {
        "id": str(paper_id),
        "title": str(title).strip(),
        "url": paper_url,
        "abstract": paper.get("summary") or paper.get("abstract") or entry.get("summary", ""),
        "authors": authors,
        "category": "Daily Paper",
        "pdf_url": f"https://arxiv.org/pdf/{paper_id}.pdf",
        "source": "Hugging Face Daily Papers",
    }


def fetch_daily_papers(
    limit: int = 5,
    paper_date: Optional[str] = None,
    keywords: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """공개 Daily Papers REST API를 조회하여 논문 목록을 가져옵니다."""
    params: Dict[str, str] = {}
    if paper_date:
        try:
            datetime.strptime(paper_date, "%Y-%m-%d")
        except ValueError:
            logger.error("[Hugging Face] 날짜 형식은 YYYY-MM-DD여야 합니다: %s", paper_date)
            return []
        params["date"] = paper_date

    logger.info("[Hugging Face] Daily Papers API 조회 중%s", f" (date={paper_date})" if paper_date else "")
    try:
        response = requests.get(DAILY_PAPERS_API_URL, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.error("[Hugging Face] API 요청 실패: %s", exc)
        return []
    except ValueError as exc:
        logger.error("[Hugging Face] API 응답 JSON 파싱 실패: %s", exc)
        return []

    if not isinstance(payload, list):
        logger.error("[Hugging Face] 예상하지 못한 API 응답 형식입니다.")
        return []

    cleaned_keywords = [keyword.strip().lower() for keyword in keywords or [] if keyword.strip()]
    papers: List[Dict[str, Any]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            logger.warning("[Hugging Face] 논문 항목 형식이 올바르지 않아 건너뜁니다.")
            continue
        paper = parse_daily_paper(entry)
        if paper is None:
            logger.warning("[Hugging Face] ID 또는 제목이 없는 논문 항목을 건너뜁니다.")
            continue
        if cleaned_keywords:
            search_target = f"{paper['title']} {paper['abstract']}".lower()
            matched = [keyword for keyword in cleaned_keywords if keyword in search_target]
            if not matched:
                continue
            paper["matched_keywords"] = matched
        papers.append(paper)
        if len(papers) >= limit:
            break

    logger.info("[Hugging Face] 최종 선정된 논문: %d건", len(papers))
    return papers


def run_huggingface(
    args: argparse.Namespace,
    webhook_url: str,
    history_mgr: HistoryManager,
) -> int:
    """Hugging Face Daily Papers 브리핑 파이프라인 실행 진입점"""
    logger.info("--- [Hugging Face Daily Papers] 수집 시작 ---")

    target_webhook = os.getenv("DISCORD_HUGGINGFACE_WEBHOOK_URL", "").strip() or webhook_url
    if not target_webhook and not getattr(args, "dry_run", False):
        logger.warning("[Hugging Face] 전송할 디스코드 웹훅 URL이 설정되지 않았습니다.")
        return 0

    try:
        limit = int(os.getenv("HF_DAILY_PAPERS_LIMIT", "5"))
    except ValueError:
        logger.error("[Hugging Face] HF_DAILY_PAPERS_LIMIT은 양의 정수여야 합니다.")
        return 0
    if limit < 1:
        logger.error("[Hugging Face] HF_DAILY_PAPERS_LIMIT은 양의 정수여야 합니다.")
        return 0
    paper_date = os.getenv("HF_DAILY_PAPERS_DATE", "").strip() or None
    raw_keywords = os.getenv("HF_DAILY_PAPERS_KEYWORDS", "").strip()
    keywords = [keyword.strip() for keyword in raw_keywords.split(",") if keyword.strip()] or None

    candidates = fetch_daily_papers(
        limit=limit * 3 if not getattr(args, "force", False) else limit,
        paper_date=paper_date,
        keywords=keywords,
    )
    if not candidates:
        logger.info("[Hugging Face] 조건에 부합하는 논문이 없습니다.")
        return 0

    to_send: List[Dict[str, Any]] = []
    for paper in candidates:
        paper_id = paper["id"]
        if not getattr(args, "force", False) and history_mgr.is_sent("huggingface", paper_id):
            continue
        to_send.append(paper)
        if len(to_send) >= limit:
            break

    logger.info("[Hugging Face] 신규 전송 대상: %d건 (최대 %d건)", len(to_send), limit)

    if getattr(args, "dry_run", False):
        logger.info("[Dry Run] 디스코드 전송 생략 (콘솔 출력):")
        for idx, paper in enumerate(to_send, 1):
            print(f"  [{idx}] [Hugging Face Daily Papers] {paper['title']}")
            print(f"      - 링크: {paper['url']}")
        return len(to_send)

    sent_count = 0
    for paper in to_send:
        payload = {
            "username": "Hugging Face Daily Papers",
            "embeds": [build_paper_embed(paper)],
        }
        if send_raw_webhook(target_webhook, payload):
            sent_count += 1
            history_mgr.mark_sent("huggingface", paper["id"])
        time.sleep(1.0)

    logger.info("[Hugging Face] 완료: %d건 중 %d건 전송 성공", len(to_send), sent_count)
    return sent_count
