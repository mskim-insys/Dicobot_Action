"""
koneps_client.py (하위 호환성 래퍼)
실제 구현은 crawlers/koneps.py로 모듈화되었습니다.
"""

from crawlers.koneps import (
    KONEPS_BASE_URL,
    KONEPS_FALLBACK_URL,
    calculate_date_range,
    fetch_bid_notices,
    filter_bid_notices,
    format_price_krw,
    get_notice_key,
    parse_price,
    run_koneps,
)
