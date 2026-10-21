"""
main.py
디스코드 통합 알리미 (나라장터 공고, 테크 뉴스, Hacker News, AI 논문 브리핑) 메인 실행 스크립트
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv

from common.discord_webhook import (
    build_news_embed,
    build_notice_embed,
    build_paper_embed,
    send_raw_webhook,
)
from common.history import HistoryManager
from crawlers.arxiv import run_arxiv
from crawlers.hackernews import run_hackernews
from crawlers.huggingface import run_huggingface
from crawlers.koneps import run_koneps
from crawlers.news import RSS_FEEDS, run_news, run_rss_feed

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("DiscordBots")


def get_webhook(target_type: str) -> str:
    """타깃별 전용 웹훅 우선 조회, 없으면 공통 DISCORD_WEBHOOK_URL 조회"""
    common = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if target_type == "koneps":
        return os.getenv("DISCORD_KONEPS_WEBHOOK_URL", "").strip() or common
    if target_type in ("news", "geeknews"):
        return os.getenv("DISCORD_NEWS_WEBHOOK_URL", "").strip() or common
    if target_type == "hackernews":
        return (
            os.getenv("DISCORD_HN_WEBHOOK_URL", "").strip()
            or os.getenv("DISCORD_NEWS_WEBHOOK_URL", "").strip()
            or common
        )
    if target_type == "arxiv":
        return os.getenv("DISCORD_ARXIV_WEBHOOK_URL", "").strip() or common
    if target_type == "huggingface":
        return os.getenv("DISCORD_HUGGINGFACE_WEBHOOK_URL", "").strip() or common
    if target_type in RSS_FEEDS:
        config = RSS_FEEDS[target_type]
        return (
            os.getenv(config["webhook_env"], "").strip()
            or os.getenv("DISCORD_NEWS_WEBHOOK_URL", "").strip()
            or common
        )
    return common


def send_mock_test_card(target: str = "all") -> None:
    """웹훅 연결 및 Embed 디자인 테스트용 가상 카드 전송"""
    logger.info("디스코드 웹훅 테스트 카드를 전송합니다... (타깃: %s)", target)

    # 1. 나라장터 카드 테스트
    if target in ("all", "koneps"):
        url = get_webhook("koneps")
        if url:
            mock_notice = {
                "bidNtceNo": "20261019001",
                "bidNtceOrd": "00",
                "bidNtceNm": "[테스트] 2026년 AI 스마트팩토리 비전 검사 시스템 구축 용역",
                "ntceInsttNm": "중소벤처기업진흥공단",
                "dminsttNm": "스마트제조혁신추진단",
                "presmptPrce": 250000000,
                "formatted_price": "2억 5,000만 원",
                "bidNtceDt": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "bidClseDt": "2026-10-31 18:00",
                "matched_keywords": ["머신비전", "AI", "스마트팩토리"],
                "bidNtceDtlUrl": "https://www.g2b.go.kr",
            }
            embed = build_notice_embed(mock_notice)
            send_raw_webhook(url, {"username": "나라장터 알리미", "embeds": [embed]})
            logger.info("✅ [나라장터] 테스트 카드 전송 완료!")
        else:
            logger.warning("⚠️ [나라장터] 웹훅 URL이 없어 테스트를 건너뜁니다.")

    # 2. 테크 뉴스 (GeekNews) 카드 테스트
    if target in ("all", "news", "geeknews"):
        url = get_webhook("geeknews")
        if url:
            mock_news = {
                "title": "[테스트] 긱뉴스 주간 AI & 테크 하이라이트",
                "url": "https://news.hada.io",
                "source": "GeekNews",
                "summary": "• 차세대 AI 에이전트 아키텍처 오픈소스 공개\n• 최신 LLM 경량화 모델 벤치마크 비교\n• 개발자를 위한 생산성 도구 모음",
                "published_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            embed = build_news_embed(mock_news)
            send_raw_webhook(url, {"username": "긱뉴스 트렌드", "embeds": [embed]})
            logger.info("✅ [긱뉴스] 테스트 카드 전송 완료!")
        else:
            logger.warning("⚠️ [긱뉴스] 웹훅 URL이 없어 테스트를 건너뜁니다.")

    # 3. Hacker News 카드 테스트
    if target in ("all", "news", "hackernews"):
        url = get_webhook("hackernews")
        if url:
            mock_hn = {
                "title": "[테스트] Show HN: Modern Open-Source AI Agent Framework",
                "url": "https://github.com/example/ai-agent",
                "hn_url": "https://news.ycombinator.com/item?id=99999999",
                "source": "HackerNews",
                "points": 342,
                "comments": 158,
                "published_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "summary": "Show HN: 초고속 비동기 파이썬 기반의 새로운 경량 AI 에이전트 프레임워크가 릴리즈되었습니다.",
            }
            embed = build_news_embed(mock_hn)
            send_raw_webhook(url, {"username": "Hacker News 트렌드", "embeds": [embed]})
            logger.info("✅ [Hacker News] 테스트 카드 전송 완료!")
        else:
            logger.warning("⚠️ [Hacker News] 웹훅 URL이 없어 테스트를 건너뜁니다.")

    # 4. Arxiv AI 논문 카드 테스트
    if target in ("all", "arxiv"):
        url = get_webhook("arxiv")
        if url:
            mock_paper = {
                "title": "[테스트] Real-time Object Detection with Next-Gen Vision Transformers",
                "url": "https://arxiv.org/abs/2610.12345",
                "category": "cs.CV, cs.AI",
                "authors": ["홍길동", "John Doe", "Jane Smith"],
                "abstract": "본 논문에서는 엣지 디바이스에서 초당 120 FPS로 동작하는 차세대 비전 트랜스포머 기반의 실시간 객체 탐지 알고리즘을 제안합니다.",
                "pdf_url": "https://arxiv.org/pdf/2610.12345.pdf",
            }
            embed = build_paper_embed(mock_paper)
            send_raw_webhook(url, {"username": "Arxiv 논문 브리핑", "embeds": [embed]})
            logger.info("✅ [Arxiv 논문] 테스트 카드 전송 완료!")
        else:
            logger.warning("⚠️ [Arxiv 논문] 웹훅 URL이 없어 테스트를 건너뜁니다.")

    # 5. Hugging Face Daily Papers 카드 테스트
    if target in ("all", "huggingface"):
        url = get_webhook("huggingface")
        if url:
            mock_paper = {
                "title": "[테스트] Hugging Face Daily Papers",
                "url": "https://huggingface.co/papers/2610.12345",
                "category": "Daily Paper",
                "authors": ["홍길동", "Jane Smith"],
                "abstract": "Hugging Face Daily Papers REST API에서 제공하는 논문 알림 테스트입니다.",
                "pdf_url": "https://arxiv.org/pdf/2610.12345.pdf",
                "source": "Hugging Face Daily Papers",
            }
            send_raw_webhook(url, {
                "username": "Hugging Face Daily Papers",
                "embeds": [build_paper_embed(mock_paper)],
            })
            logger.info("✅ [Hugging Face Daily Papers] 테스트 카드 전송 완료!")
        else:
            logger.warning("⚠️ [Hugging Face Daily Papers] 웹훅 URL이 없어 테스트를 건너뜁니다.")

    # 6. 추가 RSS/Atom 피드 카드 테스트
    for source, config in RSS_FEEDS.items():
        if target not in ("all", "news", source):
            continue
        url = get_webhook(source)
        if not url:
            logger.warning("[%s] 웹훅 URL이 없어 테스트를 건너뜁니다.", config["name"])
            continue
        mock_item = {
            "title": f"[테스트] {config['name']} RSS 알림",
            "url": config["url"],
            "source": config["name"],
            "summary": f"{config['name']} 피드의 테스트 알림입니다.",
            "published_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        send_raw_webhook(url, {
            "username": config["name"],
            "embeds": [build_news_embed(mock_item)],
        })
        logger.info("[%s] 테스트 카드 전송 완료!", config["name"])


def execute_pipeline(args: argparse.Namespace) -> None:
    """공통 이력 관리자 생성 및 선택된 크롤러 순차 실행"""
    load_dotenv(override=True)

    common_webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

    # 웹훅 단독 테스트 모드
    if args.test_webhook:
        send_mock_test_card(target=args.target)
        return

    # 웹훅 유효성 검증 (dry-run이 아닐 때)
    any_webhook = (
        common_webhook
        or os.getenv("DISCORD_KONEPS_WEBHOOK_URL")
        or os.getenv("DISCORD_NEWS_WEBHOOK_URL")
        or os.getenv("DISCORD_HN_WEBHOOK_URL")
        or os.getenv("DISCORD_ARXIV_WEBHOOK_URL")
        or os.getenv("DISCORD_HUGGINGFACE_WEBHOOK_URL")
        or any(os.getenv(config["webhook_env"]) for config in RSS_FEEDS.values())
    )
    if not any_webhook and not args.dry_run:
        logger.error("디스코드 웹훅 URL이 하나도 설정되지 않았습니다. .env 파일을 확인해주세요.")
        sys.exit(1)

    history_mgr = HistoryManager()
    total_sent = 0

    logger.info("==========================================")
    logger.info("🚀 디스코드 알리미 파이프라인 가동 (타깃: %s)", args.target)
    logger.info("==========================================")

    # 1. 나라장터 공고 수집 실행
    if args.target in ("all", "koneps"):
        try:
            sent = run_koneps(args, common_webhook, history_mgr)
            total_sent += sent
        except Exception as e:
            logger.error("[나라장터] 파이프라인 실행 중 오류: %s", e)

    # 2. 국내 테크 뉴스 (GeekNews) 수집 실행
    if args.target in ("all", "news", "geeknews"):
        try:
            sent = run_news(args, common_webhook, history_mgr)
            total_sent += sent
        except Exception as e:
            logger.error("[긱뉴스] 파이프라인 실행 중 오류: %s", e)

    # 3. 글로벌 테크 뉴스 (Hacker News) 수집 실행
    if args.target in ("all", "news", "hackernews"):
        try:
            sent = run_hackernews(args, common_webhook, history_mgr)
            total_sent += sent
        except Exception as e:
            logger.error("[HackerNews] 파이프라인 실행 중 오류: %s", e)

    # 4. Arxiv AI 논문 수집 실행 (cs.AI + cs.CV)
    if args.target in ("all", "arxiv"):
        try:
            sent = run_arxiv(args, common_webhook, history_mgr)
            total_sent += sent
        except Exception as e:
            logger.error("[Arxiv] 파이프라인 실행 중 오류: %s", e)

    # 5. Hugging Face Daily Papers
    if args.target in ("all", "huggingface"):
        try:
            sent = run_huggingface(args, get_webhook("huggingface"), history_mgr)
            total_sent += sent
        except Exception as e:
            logger.error("[Hugging Face] 파이프라인 실행 중 오류: %s", e)

    # 6. 추가 RSS/Atom 피드
    for source, config in RSS_FEEDS.items():
        if args.target not in ("all", "news", source):
            continue
        try:
            total_sent += run_rss_feed(source, args, get_webhook(source), history_mgr)
        except Exception as e:
            logger.error("[%s] 파이프라인 실행 중 오류: %s", config["name"], e)

    # 5. 전송 이력 저장
    history_mgr.save()
    logger.info("==========================================")
    logger.info("🎉 전체 작업 완료: 총 %d건 신규 전송됨", total_sent)
    logger.info("==========================================")


def main() -> None:
    parser = argparse.ArgumentParser(description="디스코드 통합 알리미 (나라장터, 뉴스, AI 논문)")
    parser.add_argument(
        "--target",
        choices=["all", "koneps", "news", "geeknews", "hackernews", "arxiv", "huggingface", *RSS_FEEDS],
        default="all",
        help="실행 대상 선택 (all: 전체, news: 전체 뉴스 피드, arxiv/huggingface: 논문, koneps: 나라장터)",
    )
    parser.add_argument("--test-webhook", action="store_true", help="가상 카드를 전송하여 디스코드 웹훅을 테스트합니다.")
    parser.add_argument("--dry-run", action="store_true", help="실제 전송 없이 수집/필터링 결과만 콘솔에 출력합니다.")
    parser.add_argument("--force", action="store_true", help="중복 체크를 무시하고 강제 전송합니다.")
    parser.add_argument("--no-price-filter", action="store_true", help="나라장터 금액 필터를 해제합니다.")
    parser.add_argument("--lookback", type=int, default=None, help="과거 며칠 전부터 조회할지 일수 지정 (기본: .env 설정값 또는 1일)")
    parser.add_argument("--interval", type=int, default=None, help="주기적 자동 실행 간격(분). 지정 시 해당 분마다 무한 반복 실행합니다.")
    args = parser.parse_args()

    load_dotenv(override=True)

    interval = args.interval
    if interval is None:
        raw_interval = os.getenv("INTERVAL_MINUTES", "").strip()
        if raw_interval.isdigit() and int(raw_interval) > 0:
            interval = int(raw_interval)

    # 단발 실행 모드 (GitHub Actions 또는 수동 1회 실행)
    if not interval or interval <= 0:
        execute_pipeline(args)
        return

    # 주기적 반복 실행 모드 (로컬 PC 백그라운드용)
    logger.info("🔁 [주기적 실행 모드 시작] %d분마다 자동으로 수집합니다. (종료: Ctrl+C)", interval)
    try:
        while True:
            execute_pipeline(args)
            next_time = (datetime.now() + timedelta(minutes=interval)).strftime("%Y-%m-%d %H:%M:%S")
            logger.info("⏳ 다음 실행 예정 시각: %s (%d분 대기 중...)\n", next_time, interval)
            time.sleep(interval * 60)
    except KeyboardInterrupt:
        logger.info("\n🛑 사용자에 의해 주기적 실행이 종료되었습니다.")


if __name__ == "__main__":
    main()
