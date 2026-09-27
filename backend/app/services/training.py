"""安全培训业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "training"
REQUIRED_FIELDS = ["培训编号", "培训主题", "培训讲师"]
STATUS_ORDER = ["计划中", "已组织", "已完成", "需补训"]
ACTION_RULES = {"组织培训": "已组织", "登记考核": "已完成", "安排补训": "需补训"}
NEGATIVE_ACTIONS = []

# 批量动作：确认完成 / 退回补考（补考即需补训）
BATCH_ACTION_RULES = {"确认完成": "已完成", "退回补考": "需补训"}
BATCH_NEGATIVE_ACTIONS = {"退回补考"}

# 考核通过字段里出现这些字样，一律视为考核未通过
FAIL_TOKENS = ("未通过", "不合格", "不及格", "未及格", "不通过", "失败")


def _is_fail(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and any(token in text for token in FAIL_TOKENS)


def _has_date(entry: dict[str, Any]) -> bool:
    return bool(str(entry.get("培训日期") or "").strip())


def _headcount(entry: dict[str, Any]) -> int:
    try:
        return max(int(str(entry.get("参训人数") or 0).strip()), 0)
    except (TypeError, ValueError):
        return 0


class TrainingService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("培训编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"培训记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于安全培训可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        self._apply_status(entry, target, abnormal=action in NEGATIVE_ACTIONS)
        return entry, f"培训记录已{action}"

    def run_batch_action(
        self, action: str, entry_ids: list[int]
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """逐条处理批量动作，每条记录独立给出结果，不因个别异常中断整批处理。

        - 重复选择的编号只真正处理一次，重复提交单独说明；
        - 考核未通过、缺少培训日期的记录单独说明并跳过，其他记录继续处理；
        - 已经处于目标状态的记录幂等返回，重复确认同一条只生效一次。
        """
        target = BATCH_ACTION_RULES[action]
        negative = action in BATCH_NEGATIVE_ACTIONS
        results: list[dict[str, Any]] = []
        seen: set[int] = set()

        for entry_id in entry_ids:
            if entry_id in seen:
                results.append({
                    "entry_id": entry_id,
                    "ok": False,
                    "code": "duplicate",
                    "message": f"培训记录 {entry_id} 在本次批量操作中被重复选择，仅按第一次提交处理",
                    "entry": None,
                })
                continue
            seen.add(entry_id)

            entry = store.find(MODULE, entry_id)
            if entry is None:
                results.append({
                    "entry_id": entry_id,
                    "ok": False,
                    "code": "not_found",
                    "message": f"培训记录 {entry_id} 不存在或已归档，已跳过",
                    "entry": None,
                })
                continue
            if _is_fail(entry.get("考核通过")):
                results.append({
                    "entry_id": entry_id,
                    "ok": False,
                    "code": "assessment_failed",
                    "message": f"培训记录 {entry_id} 考核未通过，不能{action}，已单独跳过",
                    "entry": entry,
                })
                continue
            if not _has_date(entry):
                results.append({
                    "entry_id": entry_id,
                    "ok": False,
                    "code": "missing_date",
                    "message": f"培训记录 {entry_id} 缺少培训日期，不能{action}，已单独跳过",
                    "entry": entry,
                })
                continue

            if entry.get("status") == target:
                results.append({
                    "entry_id": entry_id,
                    "ok": True,
                    "code": "already_applied",
                    "message": f"培训记录 {entry_id} 已是「{target}」状态，无需重复{action}",
                    "entry": entry,
                })
                continue

            self._apply_status(entry, target, abnormal=negative)
            results.append({
                "entry_id": entry_id,
                "ok": True,
                "code": "applied",
                "message": f"培训记录 {entry_id} 已{action}",
                "entry": entry,
            })

        return results, self.statistics()

    def statistics(self) -> dict[str, int]:
        """参训人数（全部记录合计）、完成数量与待补训数量，供页面卡片同步刷新。"""
        rows = store.rows(MODULE)
        return {
            "参训人数": sum(_headcount(row) for row in rows),
            "完成数量": sum(1 for row in rows if row.get("status") == "已完成"),
            "待补训数量": sum(1 for row in rows if row.get("status") == "需补训"),
        }

    def _apply_status(self, entry: dict[str, Any], target: str, *, abnormal: bool) -> None:
        entry["status"] = target
        entry["培训状态"] = target
        entry["pending"] = target != "已完成"
        entry["abnormal"] = abnormal
