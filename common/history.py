"""
common/history.py
크롤러별 전송 이력 및 중복 방지(Deduplication) 관리 모듈
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_FILE = "sent_history.json"
LEGACY_HISTORY_FILE = "sent_notices.json"


class HistoryManager:
    """크롤러별(koneps, news 등) 전송 완료 ID를 JSON 파일로 영구 보관/관리합니다."""

    def __init__(self, filepath: str = DEFAULT_HISTORY_FILE, max_history_per_category: int = 3000):
        self.filepath = filepath
        self.max_history = max_history_per_category
        self.data: Dict[str, Set[str]] = {}
        self.load()

    def load(self) -> None:
        """기존 이력 파일을 불러오며, 구버전 sent_notices.json도 자동 마이그레이션합니다."""
        self.data = {}

        # 1. 메인 이력 파일 로드
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    for cat, ids in raw.get("categories", {}).items():
                        self.data[cat] = set(ids)
                    logger.debug("이력 파일 로드 완료 (%s)", self.filepath)
            except Exception as e:
                logger.warning("이력 파일(%s) 로드 실패: %s", self.filepath, e)

        # 2. 구버전 sent_notices.json이 존재하면 koneps 카테고리로 통합
        if os.path.exists(LEGACY_HISTORY_FILE):
            try:
                with open(LEGACY_HISTORY_FILE, "r", encoding="utf-8") as f:
                    legacy_raw = json.load(f)
                    legacy_ids = legacy_raw.get("sent_ids", [])
                    if legacy_ids:
                        if "koneps" not in self.data:
                            self.data["koneps"] = set()
                        self.data["koneps"].update(legacy_ids)
                        logger.info("구버전 이력(%s)에서 %d건을 koneps 카테고리로 마이그레이션했습니다.", LEGACY_HISTORY_FILE, len(legacy_ids))
            except Exception as e:
                logger.warning("구버전 이력 파일 로드 실패: %s", e)

    def is_sent(self, category: str, item_id: str) -> bool:
        """해당 카테고리에서 이미 전송된 ID인지 확인"""
        if not item_id:
            return False
        return item_id in self.data.get(category, set())

    def mark_sent(self, category: str, item_id: str) -> None:
        """전송 완료 ID로 등록"""
        if not item_id:
            return
        if category not in self.data:
            self.data[category] = set()
        self.data[category].add(item_id)

    def save(self) -> None:
        """전송 이력을 JSON 파일로 저장합니다 (오래된 항목은 max_history에 맞춰 정리)"""
        out_categories: Dict[str, List[str]] = {}
        for cat, ids in self.data.items():
            id_list = list(ids)
            if len(id_list) > self.max_history:
                id_list = id_list[-self.max_history:]
            out_categories[cat] = id_list

        payload = {
            "categories": out_categories,
            "updated_at": datetime.now().isoformat(),
        }

        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            logger.debug("전송 이력 저장 완료 (%s)", self.filepath)
        except Exception as e:
            logger.error("전송 이력 저장 실패: %s", e)

