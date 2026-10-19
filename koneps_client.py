"""
koneps_client.py
공공데이터포털 '조달청 나라장터 입찰공고정보서비스' API 클라이언트 모듈
"""

import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# 기본 엔드포인트 URL (12번: 나라장터검색조건 용역조회, 2번: 용역 기본조회)
KONEPS_BASE_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch"
KONEPS_FALLBACK_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc"


def calculate_date_range(lookback_days: int = 1) -> Tuple[str, str]:
    """
    조회 기간 계산 (과거 N일 전 00:00부터 오늘 23:59까지)
    형식: YYYYMMDDHHMM (예: 202610150000, 202610162359)
    """
    now = datetime.now()
    start_dt = (now - timedelta(days=lookback_days)).strftime("%Y%m%d0000")
    end_dt = now.strftime("%Y%m%d2359")
    return start_dt, end_dt


def fetch_bid_notices(
    api_key: str,
    start_dt: Optional[str] = None,
    end_dt: Optional[str] = None,
    page_no: int = 1,
    num_of_rows: int = 100,
    lookback_days: int = 1,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    조달청 나라장터 용역 입찰공고 목록을 조회합니다.
    인증키 인코딩/디코딩 문제 자동 대응 및 JSON 파싱을 수행합니다.

    Returns:
        (items, total_count)
    """
    if not api_key or not api_key.strip():
        raise ValueError("공공데이터포털 API 인증키(DATA_GO_KR_API_KEY)가 비어있습니다. .env 파일에 키를 입력해주세요.")

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

    # 전략 1: requests params에 decoded_key 전달 (requests가 한 번 인코딩)
    # 전략 2: 에러 발생 시 raw_key를 URL에 직접 붙여 재시도 (공공데이터포털 이중인코딩 방지)
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

    # 공공데이터포털 에러 응답(XML 형식 반환 등) 처리
    if "SERVICE ERROR" in raw_text or "SERVICE_KEY_IS_NOT_REGISTERED" in raw_text or "<OpenAPI_ServiceResponse>" in raw_text:
        # 두 번째 방식 시도
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

    # OpenAPI 응답 구조 정규화 (배열, 딕셔너리, 빈 값 케이스 대응)
    items: List[Dict[str, Any]] = []
    if isinstance(raw_items, list):
        items = raw_items
    elif isinstance(raw_items, dict):
        # {"item": [...]} 또는 {"item": {...}} 형태
        item_entry = raw_items.get("item", [])
        if isinstance(item_entry, list):
            items = item_entry
        elif isinstance(item_entry, dict):
            items = [item_entry]

    return items, total_count


def parse_price(value: Any) -> int:
    """
    금액 문자열이나 숫자를 정수(원 단위)로 변환합니다.
    """
    if not value:
        return 0
    try:
        clean = str(value).replace(",", "").strip()
        return int(float(clean))
    except (ValueError, TypeError):
        return 0


def format_price_krw(amount: int) -> str:
    """
    원 단위 금액을 한국어 단위(억, 만 원)로 읽기 쉽게 포맷팅합니다.
    예: 250000000 -> '2억 5,000만 원'
    """
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


def filter_bid_notices(
    items: List[Dict[str, Any]],
    keywords: Optional[List[str]] = None,
    min_price: int = 0,
    max_price: int = 0,
    enable_price_filter: bool = True,
) -> List[Dict[str, Any]]:
    """
    수집된 공고 목록에서 키워드와 금액 조건을 충족하는 공고를 필터링합니다.

    Args:
        items: 원본 공고 목록
        keywords: 포함할 키워드 리스트 (대소문자 무시)
        min_price: 최소 추정가격 (0이면 하한 없음)
        max_price: 최대 추정가격 (0이면 상한 없음)
        enable_price_filter: False로 설정 시 금액 조건을 검사하지 않고 모두 통과

    Returns:
        필터링 통과 공고 목록 (각 공고에 'matched_keywords' 및 'parsed_price' 필드 추가)
    """
    if keywords is None:
        keywords = ["비전", "AI", "머신비전", "인공지능", "딥러닝", "스마트", "스마트팩토리", "데이터", "검사기", "소프트웨어", "SW"]

    cleaned_keywords = [k.strip().lower() for k in keywords if k.strip()]
    filtered: List[Dict[str, Any]] = []

    for item in items:
        title = item.get("bidNtceNm", "")
        title_lower = title.lower()

        # 1. 키워드 검사
        matched = [k for k in cleaned_keywords if k in title_lower]
        if not matched:
            continue

        # 2. 금액 검사 (추정가격 presmptPrce 또는 배정예산 asignBdgtAmt)
        raw_price = item.get("presmptPrce") or item.get("asignBdgtAmt") or 0
        price = parse_price(raw_price)

        if enable_price_filter:
            if min_price > 0 and price > 0 and price < min_price:
                continue
            if max_price > 0 and price > 0 and price > max_price:
                continue

        item_copy = dict(item)
        item_copy["matched_keywords"] = matched
        item_copy["parsed_price"] = price
        item_copy["formatted_price"] = format_price_krw(price)

        # 상세 링크 보정
        if not item_copy.get("bidNtceDtlUrl"):
            bid_no = item_copy.get("bidNtceNo", "")
            bid_ord = item_copy.get("bidNtceOrd", "00")
            item_copy["bidNtceDtlUrl"] = (
                f"https://www.g2b.go.kr:8081/ep/invitation/publish/bidInfoDtl.do?bidno={bid_no}&bidseq={bid_ord}"
            )

        filtered.append(item_copy)

    return filtered

