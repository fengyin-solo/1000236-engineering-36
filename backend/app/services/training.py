"""安全培训业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "training"
REQUIRED_FIELDS = ["培训编号", "培训主题", "培训讲师"]
STATUS_ORDER = ["计划中", "已组织", "已完成", "需补训"]
ACTION_RULES = {"组织培训": "已组织", "登记考核": "已完成", "安排补训": "需补训"}
NEGATIVE_ACTIONS = []
BATCH_ACTION_RULES = {"确认完成": "已完成", "退回补考": "需补训"}
EXAM_FAIL_VALUES = {"否", "未通过", "不通过", "不合格"}


def _headcount(value: Any) -> int:
    """参训人数只认数字，占位文本按 0 计，避免汇总时报错。"""
    try:
        return int(str(value).strip())
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
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"培训记录已{action}"

    def summary(self) -> dict[str, int]:
        """汇总参训人数与完成数量，批量处理后前端据此同步刷新统计卡片。"""
        rows = store.rows(MODULE)
        return {
            "记录总数": len(rows),
            "参训人数": sum(_headcount(row.get("参训人数")) for row in rows),
            "完成数量": sum(1 for row in rows if row.get("status") == "已完成"),
            "需补训数量": sum(1 for row in rows if row.get("status") == "需补训"),
        }

    def run_batch_action(self, ids: list[int], action: str) -> tuple[dict[str, Any] | None, str]:
        """批量确认完成或退回补考：逐条处理，跳过项单独说明，其余记录继续。"""
        target = BATCH_ACTION_RULES.get(action)
        if target is None:
            return None, f"动作「{action}」不支持批量执行，可批量确认完成或退回补考"
        results: list[dict[str, Any]] = []
        seen: set[int] = set()
        succeeded = 0
        for entry_id in ids:
            item = self._apply_batch_item(entry_id, action, target, seen)
            results.append(item)
            if item["ok"]:
                succeeded += 1
        skipped = len(results) - succeeded
        result = {
            "action": action,
            "results": results,
            "succeeded": succeeded,
            "skipped": skipped,
            "summary": self.summary(),
        }
        return result, f"批量{action}：成功 {succeeded} 条，跳过 {skipped} 条"

    def _apply_batch_item(
        self,
        entry_id: int,
        action: str,
        target: str,
        seen: set[int],
    ) -> dict[str, Any]:
        if entry_id in seen:
            return {"id": entry_id, "ok": False, "message": f"培训记录 {entry_id} 重复选择，已跳过"}
        seen.add(entry_id)
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return {"id": entry_id, "ok": False, "message": f"培训记录 {entry_id} 不存在或已归档"}
        label = str(entry.get("培训编号") or f"#{entry_id}")
        if not str(entry.get("培训日期") or "").strip():
            return {"id": entry_id, "ok": False, "message": f"{label} 缺少培训日期，请先补登再{action}"}
        exam = str(entry.get("考核通过") or "").strip()
        if action == "确认完成" and exam in EXAM_FAIL_VALUES:
            return {"id": entry_id, "ok": False, "message": f"{label} 考核未通过，不能确认完成，可退回补考"}
        if entry.get("status") == target:
            return {"id": entry_id, "ok": False, "message": f"{label} 已是「{target}」状态，本次不重复生效"}
        entry["status"] = target
        entry["pending"] = target == "需补训"
        entry["abnormal"] = False
        return {"id": entry_id, "ok": True, "message": f"{label} 已{action}"}
