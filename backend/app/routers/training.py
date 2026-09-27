"""安全培训接口：维护培训记录，覆盖组织培训、登记考核、安排补训等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ActionResult,
    BatchActionPayload,
    BatchActionResult,
    EntryPayload,
    PageResult,
)
from app.services.training import BATCH_ACTION_RULES, TrainingService

router = APIRouter(prefix="/api/training", tags=["安全培训"])

service = TrainingService()

LIST_FIELDS = ["培训编号", "培训主题", "培训讲师", "培训日期", "参训人数", "考核通过", "培训资料", "培训状态"]
STATUSES = ["计划中", "已组织", "已完成", "需补训"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按培训编号检索"),
    status: str | None = Query(default=None, description="计划中、已组织、已完成、需补训"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按培训编号与状态过滤安全培训列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/statistics")
def get_statistics() -> dict[str, int]:
    """参训人数、完成数量等汇总口径，批量动作后前端用它同步刷新卡片。"""
    return service.statistics()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出安全培训清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "training", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条培训记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"培训记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条培训记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="培训记录已登记", entry=entry)


@router.post("/batch-actions", response_model=BatchActionResult)
def run_batch_action(payload: BatchActionPayload) -> BatchActionResult:
    """批量确认完成 / 退回补考：一次处理多条并逐条返回结果。

    考核未通过、缺少培训日期或重复选择的记录单独说明，其余记录继续处理；
    重复确认同一条只生效一次，汇总里带刷新后的参训人数与完成数量。
    """
    action = (payload.action or "").strip()
    if action not in BATCH_ACTION_RULES:
        allowed = "、".join(BATCH_ACTION_RULES)
        raise HTTPException(status_code=400, detail=f"批量动作「{action}」不支持，仅支持：{allowed}")
    if not payload.entry_ids:
        raise HTTPException(status_code=400, detail="请至少选择一条培训记录后再执行批量操作")

    raw_results, statistics = service.run_batch_action(action, payload.entry_ids)
    success_count = sum(1 for item in raw_results if item["ok"] and item["code"] == "applied")
    skipped_count = sum(1 for item in raw_results if not item["ok"])
    kept_count = sum(1 for item in raw_results if item["ok"] and item["code"] == "already_applied")
    parts = [f"成功处理 {success_count} 条"]
    if kept_count:
        parts.append(f"已处于目标状态 {kept_count} 条（未重复生效）")
    if skipped_count:
        parts.append(f"跳过 {skipped_count} 条")
    message = f"批量{action}完成：" + "，".join(parts)

    return BatchActionResult(
        ok=True,
        action=action,
        message=message,
        results=raw_results,
        success_count=success_count,
        skipped_count=skipped_count,
        statistics=statistics,
    )


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条培训记录执行组织培训、登记考核、安排补训；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
