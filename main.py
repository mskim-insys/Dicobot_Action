"""
main.py
디스코드 통합 알리미 (나라장터 공고 & 뉴스) 메인 실행 스크립트
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv

from common.discord_webhook import build_news_embed, build_notice_embed, send_raw_webhook
from common.history import HistoryManager
from crawlers.koneps import run_koneps
from crawlers.news import run_news

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


def send_mock_test_card(webhook_url: str, target: str = "all") -> None:
    """웹훅 연결 및 Embed 디자인 테스트용 가상 카드 전송"""
    logger.info("디스코드 웹훅 테스트 카드를 전송합니다... (타깃: %s)", target)

    if target in ("all", "koneps"):
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
        send_raw_webhook(webhook_url, {"username": "나라장터 알리미", "embeds": [embed]})
        logger.info("✅ [나라장터] 테스트 카드 전송 완료!")

    if target in ("all", "news"):
        mock_news = {
            "title": "[테스트] 오픈AI, 차세대 멀티모달 추론 AI 모델 공개",
            "url": "https://news.naver.com",
            "press": "테크뉴스",
            "summary": "인공지능 분야의 새로운 패러다임을 열 차세대 추론 모델이 정식 공개되었습니다.",
            "published_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "matched_keywords": ["AI", "추론"],
        }
        news_webhook_url = os.getenv("DISCORD_NEWS_WEBHOOK_URL", "").strip() or webhook_url
        embed = build_news_embed(mock_news)
        send_raw_webhook(news_webhook_url, {"username": "디스코드 뉴스 알리미", "embeds": [embed]})
        logger.info("✅ [뉴스] 테스트 카드 전송 완료!")


def execute_pipeline(args: argparse.Namespace) -> None:
    """공통 이력 관리자 생성 및 선택된 크롤러(나라장터, 뉴스 등) 순차 실행"""
    load_dotenv(override=True)

    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

    # 웹훅 단독 테스트 모드
    if args.test_webhook:
        if not webhook_url:
            logger.error(".env 파일에 DISCORD_WEBHOOK_URL이 설정되지 않았습니다.")
            sys.exit(1)
        send_mock_test_card(webhook_url, target=args.target)
        return

    # 웹훅 필수 검증 (dry-run이 아닐 때)
    if not webhook_url and not args.dry_run:
        logger.error("필수 환경변수 DISCORD_WEBHOOK_URL이 설정되지 않았습니다.")
        sys.exit(1)

    history_mgr = HistoryManager()
    total_sent = 0

    logger.info("==========================================")
    logger.info("🚀 디스코드 알리미 파이프라인 가동 (타깃: %s)", args.target)
    logger.info("==========================================")

    # 1. 나라장터 공고 수집 실행
    if args.target in ("all", "koneps"):
        try:
            sent = run_koneps(args, webhook_url, history_mgr)
            total_sent += sent
        except Exception as e:
            logger.error("[나라장터] 파이프라인 실행 중 오류: %s", e)

    # 2. 뉴스 수집 실행
    if args.target in ("all", "news"):
        try:
            sent = run_news(args, webhook_url, history_mgr)
            total_sent += sent
        except Exception as e:
            logger.error("[뉴스] 파이프라인 실행 중 오류: %s", e)

    # 3. 전송 이력 저장
    history_mgr.save()
    logger.info("==========================================")
    logger.info("🎉 전체 작업 완료: 총 %d건 신규 전송됨", total_sent)
    logger.info("==========================================")


def main() -> None:
    parser = argparse.ArgumentParser(description="디스코드 통합 알리미 (나라장터 & 뉴스)")
    parser.add_argument(
        "--target",
        choices=["all", "koneps", "news"],
        default="all",
        help="실행할 크롤러 대상 선택 (all: 전체, koneps: 나라장터만, news: 뉴스만, 기본: all)",
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
