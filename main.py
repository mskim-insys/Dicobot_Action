"""
main.py
나라장터 공고 수집 및 디스코드 웹훅 전송 메인 실행 스크립트
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Set

from dotenv import load_dotenv

import discord_webhook
import koneps_client

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
logger = logging.getLogger("KonepsNotifier")

SENT_HISTORY_FILE = "sent_notices.json"


def load_sent_history() -> Set[str]:
    """이미 전송된 공고 ID 목록을 불러옵니다."""
    if not os.path.exists(SENT_HISTORY_FILE):
        return set()
    try:
        with open(SENT_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("sent_ids", []))
    except Exception as e:
        logger.warning("전송 이력 파일(%s) 로드 실패: %s", SENT_HISTORY_FILE, e)
        return set()


def save_sent_history(sent_ids: Set[str], max_history: int = 2000) -> None:
    """전송된 공고 ID 목록을 저장합니다 (최대 max_history개 보관)."""
    # 최신 순으로 최대 보관 개수 제한
    id_list = list(sent_ids)
    if len(id_list) > max_history:
        id_list = id_list[-max_history:]
    try:
        with open(SENT_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"sent_ids": id_list, "updated_at": datetime.now().isoformat()}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("전송 이력 파일 저장 실패: %s", e)


def get_notice_key(notice: Dict[str, Any]) -> str:
    """공고 고유 식별자 반환 (공고번호-차수)"""
    no = notice.get("bidNtceNo", "")
    ord_no = notice.get("bidNtceOrd", "00")
    return f"{no}_{ord_no}" if no else ""


def send_mock_test_card(webhook_url: str) -> None:
    """웹훅 연결 및 Embed 디자인 테스트용 가상 공고 전송"""
    mock_notice = {
        "bidNtceNo": "20261016001",
        "bidNtceOrd": "00",
        "bidNtceNm": "[테스트] 2026년 스마트공장 머신비전 AI 품질검사 시스템 고도화 용역",
        "ntceInsttNm": "중소벤처기업진흥공단",
        "dminsttNm": "스마트제조혁신추진단",
        "presmptPrce": 250000000,
        "formatted_price": "2억 5,000만 원",
        "bidNtceDt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "bidClseDt": "2026-10-31 18:00",
        "matched_keywords": ["머신비전", "AI", "스마트공장"],
        "bidNtceDtlUrl": "https://www.g2b.go.kr",
    }
    logger.info("디스코드 웹훅 테스트 카드를 전송합니다...")
    success = discord_webhook.send_notice_webhook(webhook_url, mock_notice)
    if success:
        logger.info("✅ 테스트 웹훅 전송 성공! 디스코드 채널을 확인해보세요.")
    else:
        logger.error("❌ 테스트 웹훅 전송 실패! 웹훅 URL을 확인해주세요.")


def execute_pipeline(args: argparse.Namespace) -> None:
    """공고 수집, 필터링, 중복 확인 및 웹훅 전송 파이프라인 1회 실행"""
    # .env 파일 로드
    load_dotenv(override=True)

    api_key = os.getenv("DATA_GO_KR_API_KEY", "").strip()
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

    # 웹훅 단독 테스트 모드
    if args.test_webhook:
        if not webhook_url:
            logger.error(".env 파일에 DISCORD_WEBHOOK_URL이 설정되지 않았습니다.")
            sys.exit(1)
        send_mock_test_card(webhook_url)
        return

    # 환경변수 검증
    missing_vars = []
    if not api_key:
        missing_vars.append("DATA_GO_KR_API_KEY (공공데이터포털 인증키)")
    if not webhook_url and not args.dry_run:
        missing_vars.append("DISCORD_WEBHOOK_URL (디스코드 웹훅 URL)")

    if missing_vars:
        logger.error("필수 환경변수가 누락되었습니다:")
        for v in missing_vars:
            logger.error("  - %s", v)
        logger.error(".env 파일에 값을 입력한 후 다시 실행해주세요.")
        sys.exit(1)

    # 설정값 파싱
    raw_keywords = os.getenv("TARGET_KEYWORDS", "비전,머신비전,AI,인공지능,딥러닝,스마트,스마트팩토리,데이터,검사기,소프트웨어,SW")
    keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]

    # 금액 필터 활성화 여부 확인
    raw_enable_price = os.getenv("ENABLE_PRICE_FILTER", "true").strip().lower()
    enable_price_filter = raw_enable_price in ("true", "1", "yes", "y")
    if args.no_price_filter:
        enable_price_filter = False

    min_price = int(os.getenv("MIN_PRICE", "50000000"))
    max_price = int(os.getenv("MAX_PRICE", "1000000000"))
    if min_price == 0 and max_price == 0:
        enable_price_filter = False

    lookback_days = args.lookback if args.lookback is not None else int(os.getenv("LOOKBACK_DAYS", "1"))

    start_dt, end_dt = koneps_client.calculate_date_range(lookback_days)
    logger.info("=== 나라장터 공고 수집 시작 ===")
    logger.info("조회 기간: %s ~ %s (최근 %d일)", start_dt, end_dt, lookback_days)
    logger.info("타깃 키워드 (%d개): %s", len(keywords), ", ".join(keywords))
    if enable_price_filter:
        logger.info("금액 필터: %s ~ %s", koneps_client.format_price_krw(min_price), koneps_client.format_price_krw(max_price))
    else:
        logger.info("금액 필터: 미적용 (모든 금액대 공고 포함)")

    # 1. API 호출
    try:
        raw_items, total_count = koneps_client.fetch_bid_notices(
            api_key=api_key,
            start_dt=start_dt,
            end_dt=end_dt,
            num_of_rows=100,
            lookback_days=lookback_days,
        )
        logger.info("조회 완료: 전체 응답 공고 %d건 (수집된 공고 %d건)", total_count, len(raw_items))
    except Exception as e:
        logger.error("조달청 API 호출 중 오류 발생: %s", e)
        return

    # 2. 키워드 및 금액 필터링
    matched_notices = koneps_client.filter_bid_notices(
        items=raw_items,
        keywords=keywords,
        min_price=min_price,
        max_price=max_price,
        enable_price_filter=enable_price_filter,
    )
    logger.info("조건 필터링 통과: %d건", len(matched_notices))

    if not matched_notices:
        logger.info("조건에 부합하는 새로운 공고가 없습니다.")
        return

    # 3. 중복 알림 방지 (Deduplication)
    sent_ids = load_sent_history()
    to_send: List[Dict[str, Any]] = []

    for notice in matched_notices:
        n_key = get_notice_key(notice)
        if not args.force and n_key in sent_ids:
            continue
        to_send.append(notice)

    logger.info("신규 전송 대상 공고: %d건 (기존 전송 완료 제외)", len(to_send))

    # Dry-run 모드일 경우 콘솔에만 출력
    if args.dry_run:
        logger.info("[Dry Run] 디스코드 전송을 생략하고 수집된 공고 목록을 출력합니다:")
        for idx, notice in enumerate(to_send, 1):
            print(f"\n[{idx}] {notice.get('bidNtceNm')}")
            print(f"    - 기관: {notice.get('ntceInsttNm')} (수요: {notice.get('dminsttNm')})")
            print(f"    - 금액: {notice.get('formatted_price')}")
            print(f"    - 마감: {notice.get('bidClseDt')}")
            print(f"    - 키워드: {', '.join(notice.get('matched_keywords', []))}")
            print(f"    - 링크: {notice.get('bidNtceDtlUrl')}")
        return

    if not to_send:
        logger.info("새로 전송할 공고가 없습니다.")
        return

    # 4. 디스코드 웹훅 전송
    logger.info("디스코드 웹훅으로 %d건의 공고 전송을 시작합니다...", len(to_send))
    sent_count = 0
    for notice in to_send:
        success = discord_webhook.send_notice_webhook(webhook_url, notice)
        if success:
            sent_count += 1
            n_key = get_notice_key(notice)
            if n_key:
                sent_ids.add(n_key)

    # 5. 전송 이력 저장
    save_sent_history(sent_ids)
    logger.info("=== 작업 완료: 총 %d건 중 %d건 전송 성공 ===", len(to_send), sent_count)


def main() -> None:
    parser = argparse.ArgumentParser(description="나라장터 IT/AI 공고 디스코드 알리미")
    parser.add_argument("--test-webhook", action="store_true", help="가상 공고 카드를 디스코드로 1건 전송하여 웹훅을 테스트합니다.")
    parser.add_argument("--dry-run", action="store_true", help="실제 디스코드 전송 없이 API 조회 및 필터링 결과만 출력합니다.")
    parser.add_argument("--force", action="store_true", help="중복 체크를 무시하고 필터링된 모든 공고를 전송합니다.")
    parser.add_argument("--no-price-filter", action="store_true", help="금액 필터를 해제하고 키워드만 일치하면 모든 금액대의 공고를 수집합니다.")
    parser.add_argument("--lookback", type=int, default=None, help="과거 며칠 전부터 조회할지 일수 지정 (기본: .env 설정값 또는 1일)")
    parser.add_argument("--interval", type=int, default=None, help="주기적 자동 실행 간격(분 단위). 지정 시 해당 분마다 무한 반복 실행합니다.")
    args = parser.parse_args()

    # .env 파일 로드
    load_dotenv(override=True)

    # 실행 간격 확인 (CLI 인자 또는 .env의 INTERVAL_MINUTES)
    interval = args.interval
    if interval is None:
        raw_interval = os.getenv("INTERVAL_MINUTES", "").strip()
        if raw_interval.isdigit() and int(raw_interval) > 0:
            interval = int(raw_interval)

    # 1회 단발 실행 (기본 모드: GitHub Actions 또는 수동 실행)
    if not interval or interval <= 0:
        execute_pipeline(args)
        return

    # 주기적 반복 실행 모드 (로컬 PC 백그라운드용)
    logger.info("🔁 [주기적 실행 모드 시작] %d분마다 자동으로 공고를 수집합니다. (종료: Ctrl+C)", interval)
    try:
        while True:
            execute_pipeline(args)
            next_time = (datetime.now() + timedelta(minutes=interval)).strftime("%Y-%m-%d %H:%M:%S")
            logger.info("⏳ 다음 실행 예정 시각: %s (%d분 대기 중...)\n", next_time, interval)
            time.sleep(interval * 60)
    except KeyboardInterrupt:
        logger.info("\n🛑 사용자에 의해 주기적 실행이 안전하게 종료되었습니다.")


if __name__ == "__main__":
    main()
