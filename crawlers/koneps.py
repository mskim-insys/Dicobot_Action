"""
crawlers/koneps.py
조달청 나라장터 입찰공고정보서비스 API 수집 및 필터링 모듈
"""

import argparse
import logging
import os
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from common.discord_webhook import send_notice_webhook
from common.history import HistoryManager

logger = logging.getLogger(__name__)

KONEPS_BASE_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch"
KONEPS_FALLBACK_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc"

KONEPS_TAG_GROUPS = {
    "manufacturing": {
        "name": "제조업 검사 자동화",
        "keywords_env": "KONEPS_MANUFACTURING_KEYWORDS",
        "webhook_env": "DISCORD_KONEPS_MANUFACTURING_WEBHOOK_URL",
        "default_keywords": ["외관검사", "머신비전", "스마트공장", "불량 선별", "조립 검사", "제조 AI"],
    },
    "foreign_worker": {
        "name": "외국인 근로자 / 인력 매칭",
        "keywords_env": "KONEPS_FOREIGN_WORKER_KEYWORDS",
        "webhook_env": "DISCORD_KONEPS_FOREIGN_WORKER_WEBHOOK_URL",
        "default_keywords": ["외국인 근로자", "계절근로자", "E-8", "인력중개", "근태관리", "노무 도급", "일자리 매칭"],
    },
    "industrial_safety": {
        "name": "중대재해 / 산업 안전",
        "keywords_env": "KONEPS_INDUSTRIAL_SAFETY_KEYWORDS",
        "webhook_env": "DISCORD_KONEPS_INDUSTRIAL_SAFETY_WEBHOOK_URL",
        "default_keywords": ["중대재해", "작업자 안전", "안전모 미착용", "끼임 방지", "위험구역 감시"],
    },
}


def calculate_date_range(lookback_days: int = 1) -> Tuple[str, str]:
    """조회 기간 계산 (과거 N일 전 00:00부터 오늘 23:59까지, YYYYMMDDHHMM)"""
    now = datetime.now()
    start_dt = (now - timedelta(days=lookback_days)).strftime("%Y%m%d0000")
    end_dt = now.strftime("%Y%m%d2359")
    return start_dt, end_dt


def parse_price(value: Any) -> int:
    """금액 문자열이나 숫자를 정수(원 단위)로 변환합니다."""
    if not value:
        return 0
    try:
        clean = str(value).replace(",", "").strip()
        return int(float(clean))
    except (ValueError, TypeError):
        return 0


def format_price_krw(amount: int) -> str:
    """원 단위 금액을 한국어 단위(억, 만 원)로 읽기 쉽게 포맷팅합니다."""
    if not amount or amount <= 0:
        return "금액 미기재 / 별도협의"

    eok = amount // 100_000_000
    remainder = amount % 100_000_000
    man = remainder // 10_000

    parts = []
    if eok > 0:
        parts.append(f"{eok}억")
    if man > 0:
        parts.append(f"{man:,}만")

    if not parts:
        return f"{amount:,}원"

    return " ".join(parts) + " 원"


def get_koneps_tag_keywords() -> Dict[str, List[str]]:
    """분류별 키워드를 환경변수에서 읽고, 미설정 시 기본 키워드를 사용합니다."""
    tag_keywords: Dict[str, List[str]] = {}
    for tag, config in KONEPS_TAG_GROUPS.items():
        raw_keywords = os.getenv(config["keywords_env"], ",".join(config["default_keywords"]))
        tag_keywords[tag] = [keyword.strip() for keyword in raw_keywords.split(",") if keyword.strip()]
    return tag_keywords


def get_notice_webhook_routes(
    notice: Dict[str, Any],
    default_webhook_url: str,
) -> Dict[str, List[str]]:
    """공고 분류에 맞는 웹훅을 URL별로 묶어, 동일 채널 중복 전송을 방지합니다."""
    matched_tags = notice.get("matched_tag_ids", [])
    route_tags = matched_tags if matched_tags else ["koneps"]
    routes: Dict[str, List[str]] = {}

    for tag in route_tags:
        config = KONEPS_TAG_GROUPS.get(tag)
        webhook_url = default_webhook_url
        if config:
            webhook_url = os.getenv(config["webhook_env"], "").strip() or default_webhook_url
        if webhook_url:
            route_id = f"koneps_{tag}" if config else "koneps"
            routes.setdefault(webhook_url, []).append(route_id)

    return routes


def fetch_bid_notices(
    api_key: str,
    start_dt: Optional[str] = None,
    end_dt: Optional[str] = None,
    page_no: int = 1,
    num_of_rows: int = 100,
    lookback_days: int = 1,
) -> Tuple[List[Dict[str, Any]], int]:
    """조달청 나라장터 용역 입찰공고 목록을 조회합니다."""
    if not api_key or not api_key.strip():
        raise ValueError("공공데이터포털 API 인증키(DATA_GO_KR_API_KEY)가 비어있습니다.")

    raw_key = api_key.strip()
    decoded_key = urllib.parse.unquote(raw_key)

    if not start_dt or not end_dt:
        start_dt, end_dt = calculate_date_range(lookback_days)

    params = {
        "numOfRows": str(num_of_rows),
        "pageNo": str(page_no),
        "inqryDiv": "1",  # 1: 공고게시일시 기준
        "inqryBgnDt": start_dt,
        "inqryEndDt": end_dt,
        "type": "json",
    }

    try:
        req_params = dict(params)
        req_params["serviceKey"] = decoded_key
        response = requests.get(KONEPS_BASE_URL, params=req_params, timeout=15)
        response.raise_for_status()
        raw_text = response.text
    except Exception as e:
        logger.warning("기본 파라미터 호출 실패, raw URL 방식으로 재시도합니다: %s", e)
        url_with_key = f"{KONEPS_BASE_URL}?serviceKey={raw_key}"
        response = requests.get(url_with_key, params=params, timeout=15)
        response.raise_for_status()
        raw_text = response.text

    if "SERVICE ERROR" in raw_text or "SERVICE_KEY_IS_NOT_REGISTERED" in raw_text or "<OpenAPI_ServiceResponse>" in raw_text:
        if "serviceKey" in response.request.url and raw_key != decoded_key:
            url_with_key = f"{KONEPS_BASE_URL}?serviceKey={raw_key}"
            response = requests.get(url_with_key, params=params, timeout=15)
            raw_text = response.text

        if "SERVICE_KEY_IS_NOT_REGISTERED" in raw_text:
            raise ValueError(
                "공공데이터포털 인증키 등록 오류(SERVICE_KEY_IS_NOT_REGISTERED)입니다.\n"
                "- 키 발급 후 포털 서버 동기화까지 1~2시간 소요될 수 있습니다.\n"
                "- '조달청_나라장터 입찰공고정보서비스' 활용 신청이 승인되었는지 확인해주세요."
            )
        if "SERVICE ERROR" in raw_text or "<OpenAPI_ServiceResponse>" in raw_text:
            raise RuntimeError(f"공공데이터포털 API 오류 응답: {raw_text[:300]}")

    try:
        data = response.json()
    except Exception as e:
        raise RuntimeError(f"API 응답 JSON 파싱 실패: {e}\n응답 본문: {raw_text[:300]}")

    body = data.get("response", {}).get("body", {})
    total_count = int(body.get("totalCount", 0))
    raw_items = body.get("items", [])

    items: List[Dict[str, Any]] = []
    if isinstance(raw_items, list):
        items = raw_items
    elif isinstance(raw_items, dict):
        item_entry = raw_items.get("item", [])
        if isinstance(item_entry, list):
            items = item_entry
        elif isinstance(item_entry, dict):
            items = [item_entry]

    return items, total_count


def filter_bid_notices(
    items: List[Dict[str, Any]],
    keywords: Optional[List[str]] = None,
    min_price: int = 0,
    max_price: int = 0,
    enable_price_filter: bool = True,
    tag_keywords: Optional[Dict[str, List[str]]] = None,
) -> List[Dict[str, Any]]:
    """수집된 공고 목록에서 키워드와 금액 조건을 충족하는 공고를 필터링합니다."""
    if keywords is None:
        keywords = ["비전", "AI", "머신비전", "인공지능", "딥러닝", "스마트", "스마트팩토리", "데이터", "검사기", "소프트웨어", "SW"]

    if tag_keywords is None:
        tag_keywords = {
            tag: config["default_keywords"]
            for tag, config in KONEPS_TAG_GROUPS.items()
        }

    all_keywords = list(dict.fromkeys(
        [keyword.strip() for keyword in keywords if keyword.strip()]
        + [keyword for group in tag_keywords.values() for keyword in group]
    ))
    cleaned_keywords = [k.lower() for k in all_keywords]
    filtered: List[Dict[str, Any]] = []

    for item in items:
        title = item.get("bidNtceNm", "")
        title_lower = title.lower()

        matched = [
            keyword for keyword, cleaned_keyword in zip(all_keywords, cleaned_keywords)
            if cleaned_keyword in title_lower
        ]
        if not matched:
            continue

        matched_tag_ids = [
            tag
            for tag, tag_group_keywords in tag_keywords.items()
            if any(keyword.lower() in title_lower for keyword in tag_group_keywords)
        ]
        raw_price = item.get("presmptPrce") or item.get("asignBdgtAmt") or 0
        price = parse_price(raw_price)

        if enable_price_filter:
            if min_price > 0 and price > 0 and price < min_price:
                continue
            if max_price > 0 and price > 0 and price > max_price:
                continue

        item_copy = dict(item)
        item_copy["matched_keywords"] = matched
        item_copy["matched_tag_ids"] = matched_tag_ids
        item_copy["matched_tags"] = [KONEPS_TAG_GROUPS[tag]["name"] for tag in matched_tag_ids]
        item_copy["parsed_price"] = price
        item_copy["formatted_price"] = format_price_krw(price)

        if not item_copy.get("bidNtceDtlUrl"):
            bid_no = item_copy.get("bidNtceNo", "")
            bid_ord = item_copy.get("bidNtceOrd", "00")
            item_copy["bidNtceDtlUrl"] = (
                f"https://www.g2b.go.kr:8081/ep/invitation/publish/bidInfoDtl.do?bidno={bid_no}&bidseq={bid_ord}"
            )

        filtered.append(item_copy)

    return filtered


def get_notice_key(notice: Dict[str, Any]) -> str:
    """공고 고유 식별자 반환 (공고번호_차수)"""
    no = notice.get("bidNtceNo", "")
    ord_no = notice.get("bidNtceOrd", "00")
    return f"{no}_{ord_no}" if no else ""


def run_koneps(
    args: argparse.Namespace,
    webhook_url: str,
    history_mgr: HistoryManager,
) -> int:
    """나라장터 공고 수집, 필터링, 중복 확인 및 웹훅 전송 파이프라인 실행"""
    target_webhook = os.getenv("DISCORD_KONEPS_WEBHOOK_URL", "").strip() or webhook_url
    tag_keywords = get_koneps_tag_keywords()
    tag_webhooks = [
        os.getenv(config["webhook_env"], "").strip()
        for config in KONEPS_TAG_GROUPS.values()
    ]
    if not target_webhook and not any(tag_webhooks) and not getattr(args, "dry_run", False):
        logger.warning("[나라장터] 전송할 디스코드 웹훅 URL이 설정되지 않았습니다.")
        return 0

    api_key = os.getenv("DATA_GO_KR_API_KEY", "").strip()
    if not api_key:
        logger.error("[나라장터] DATA_GO_KR_API_KEY 환경변수가 설정되지 않아 건너뜁니다.")
        return 0

    raw_keywords = os.getenv("TARGET_KEYWORDS", "비전,머신비전,AI,인공지능,딥러닝,스마트,스마트팩토리,데이터,검사기,소프트웨어,SW")
    keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
    search_keywords = list(dict.fromkeys(
        keywords + [keyword for group in tag_keywords.values() for keyword in group]
    ))

    raw_enable_price = os.getenv("ENABLE_PRICE_FILTER", "true").strip().lower()
    enable_price_filter = raw_enable_price in ("true", "1", "yes", "y")
    if getattr(args, "no_price_filter", False):
        enable_price_filter = False

    min_price = int(os.getenv("MIN_PRICE", "50000000"))
    max_price = int(os.getenv("MAX_PRICE", "1000000000"))
    if min_price == 0 and max_price == 0:
        enable_price_filter = False

    lookback_days = args.lookback if getattr(args, "lookback", None) is not None else int(os.getenv("LOOKBACK_DAYS", "1"))

    start_dt, end_dt = calculate_date_range(lookback_days)
    logger.info("--- [나라장터] 수집 시작 (%s ~ %s, 최근 %d일) ---", start_dt, end_dt, lookback_days)

    try:
        raw_items, total_count = fetch_bid_notices(
            api_key=api_key,
            start_dt=start_dt,
            end_dt=end_dt,
            num_of_rows=100,
            lookback_days=lookback_days,
        )
        logger.info("[나라장터] 원본 조회 %d건 중 %d건 수집", total_count, len(raw_items))
    except Exception as e:
        logger.error("[나라장터] API 호출 실패: %s", e)
        return 0

    matched_notices = filter_bid_notices(
        items=raw_items,
        keywords=search_keywords,
        min_price=min_price,
        max_price=max_price,
        enable_price_filter=enable_price_filter,
        tag_keywords=tag_keywords,
    )
    logger.info("[나라장터] 조건 필터 통과: %d건", len(matched_notices))

    to_send: List[Tuple[Dict[str, Any], Dict[str, List[str]]]] = []
    for notice in matched_notices:
        n_key = get_notice_key(notice)
        if not getattr(args, "force", False) and history_mgr.is_sent("koneps", n_key):
            continue
        routes = get_notice_webhook_routes(notice, target_webhook)
        if not routes:
            logger.warning("[나라장터] 공고에 연결된 웹훅이 없습니다: %s", notice.get("bidNtceNm"))
            continue

        pending_routes = {
            url: [
                route_id for route_id in route_ids
                if getattr(args, "force", False) or not history_mgr.is_sent(route_id, n_key)
            ]
            for url, route_ids in routes.items()
        }
        pending_routes = {url: route_ids for url, route_ids in pending_routes.items() if route_ids}
        if pending_routes:
            to_send.append((notice, pending_routes))

    logger.info("[나라장터] 신규 전송 대상: %d건", len(to_send))

    if getattr(args, "dry_run", False):
        logger.info("[Dry Run] 디스코드 전송 생략 (콘솔 출력):")
        for idx, (notice, routes) in enumerate(to_send, 1):
            print(
                f"  [{idx}] {notice.get('bidNtceNm')} | "
                f"분류: {', '.join(notice.get('matched_tags', [])) or '기본'} | "
                f"전송 채널: {len(routes)} | {notice.get('formatted_price')} | "
                f"{notice.get('bidNtceDtlUrl')}"
            )
        return len(to_send)

    sent_count = 0
    for notice, routes in to_send:
        n_key = get_notice_key(notice)
        all_routes_sent = True
        for webhook_url, route_ids in routes.items():
            if send_notice_webhook(webhook_url, notice):
                sent_count += 1
                for route_id in route_ids:
                    if n_key:
                        history_mgr.mark_sent(route_id, n_key)
            else:
                all_routes_sent = False
        if n_key and all_routes_sent:
            history_mgr.mark_sent("koneps", n_key)

    logger.info("[나라장터] 완료: %d건 중 %d개 채널 전송 성공", len(to_send), sent_count)
    return sent_count
