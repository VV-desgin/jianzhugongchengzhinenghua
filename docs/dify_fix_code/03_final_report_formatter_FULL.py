import json

def main(
    project_name: str = "",
    project_id: str = "",
    project_type: str = "",
    layer_count: int = 0,
    object_count: int = 0,
    total_rules: int = 0,
    passed_rules: int = 0,
    failed_rules: int = 0,
    review_report: str = "",
    bom_report: str = "",
    bom_count: int = 0,
    confirm_count: int = 0,
    fiber_report: str = "",
    fiber_status: str = "",
    fiber_count: int = 0,
    splice_count: int = 0,
    conflict_count: int = 0,
    construction_report: str = "",
    construction_status: str = "",
    instruction_count: int = 0,
    work_package_count: int = 0,
    unknown_count: int = 0,
    environment_pending_count: int = 0,
    manual_package_count: int = 0,
    review_state: str = "",
    **kwargs,
) -> dict:

    def number(value):
        try:
            return int(value or 0)
        except Exception:
            return 0

    layer_count = number(layer_count)
    object_count = number(object_count)
    total_rules = number(total_rules)
    passed_rules = number(passed_rules)
    failed_rules = number(failed_rules)
    bom_count = number(bom_count)
    confirm_count = number(confirm_count)
    fiber_count = number(fiber_count)
    splice_count = number(splice_count)
    conflict_count = number(conflict_count)
    instruction_count = number(instruction_count)
    work_package_count = number(work_package_count)
    unknown_count = number(unknown_count)
    environment_pending_count = number(environment_pending_count)
    manual_package_count = number(manual_package_count)

    pending_count = (confirm_count + conflict_count + unknown_count
                   + environment_pending_count + manual_package_count)

    warning_text = ""

    machine_error = bool(
        str(fiber_status) in ("失败", "FAILED", "解析失败")
        or str(construction_status) in ("失败", "FAILED", "解析失败")
        or review_state in ("error", "missing")
    )
    if machine_error:
        overall_status = "BLOCKED"
        conclusion = "必需模块失败，当前结果不得用于正式交付。"
    elif failed_rules > 0:
        overall_status = "CONDITIONAL_PASS_ESTIMATED"
        warning_text = "> **重要提示：当前设计尚未通过智能审查，以下均为预估成果。**"
        conclusion = f"当前设计存在 {failed_rules} 项审查未通过问题，只能作为预估参考，不得作为正式施工依据。"
    elif (
        pending_count > 0
        or str(fiber_status) == "待确认"
        or str(construction_status) == "待确认"
    ):
        overall_status = "CONDITIONAL_PASS"
        conclusion = f"自动流程已完成，共有 {pending_count} 项待人工确认或冲突项，确认后可进入正式交付。"
    else:
        overall_status = "PASS"
        conclusion = "工程解析、审查、BOM、纤芯和施工指令均完成，可进入正式交付。"


        conclusion = (
            "工程解析、智能审查、BOM生成、纤芯分配"
            "和施工指令生成均已完成，可进入正式施工交付。"
        )

    final_report = f"""# 通信工程智能化全流程交付报告

{warning_text}

## 一、项目基本信息

| 项目 | 内容 |
|---|---|
| 工程名称 | {project_name or "未提供"} |
| 项目编号 | {project_id or "未提供"} |
| 工程类型 | {project_type or "未识别"} |
| 图层数量 | {layer_count} |
| 工程对象数量 | {object_count} |
| 全流程状态 | **{overall_status}** |

## 二、智能审查结果

### 审查统计

| 指标 | 数量 |
|---|---:|
| 审查规则/检查项 | {total_rules} |
| 通过 | {passed_rules} |
| 未通过 | {failed_rules} |

{review_report or "未生成智能审查报告。"}

---

## 三、BOM物料清单

### BOM统计

| 指标 | 数量 |
|---|---:|
| BOM物料种类 | {bom_count} |
| 待人工确认项 | {confirm_count} |

{bom_report or "未生成BOM物料清单。"}

---

## 四、纤芯分配与接续结果

### 纤芯统计

| 指标 | 数量 |
|---|---:|
| 分配状态 | {fiber_status or "未提供"} |
| 分配纤芯数 | {fiber_count} |
| 接续记录数 | {splice_count} |
| 冲突记录数 | {conflict_count} |

{fiber_report or "未生成纤芯分配报告。"}

---

## 五、施工指令

### 施工指令统计

| 指标 | 数量 |
|---|---:|
| 指令状态 | {construction_status or "未提供"} |
| 施工对象数 | {instruction_count} |
| 施工任务包数 | {work_package_count} |
| 未知对象数 | {unknown_count} |

{construction_report or "未生成施工指令报告。"}

---

## 六、交付结论

**结论：{overall_status}**

{conclusion}

### 待处理事项汇总

| 类型 | 数量 |
|---|---:|
| 审查未通过项 | {failed_rules} |
| BOM待确认项 | {confirm_count} |
| 纤芯冲突项 | {conflict_count} |
| 未知施工对象 | {unknown_count} |

> 本报告由通信工程智能化总控工作流自动生成。结构化结果仍保留在各专业模块中，用于后续导出、复核和施工数据传递。
"""

    return {
        "final_report": final_report,
        "overall_status": overall_status,
        "pending_count": pending_count,
        "result_type": "formal" if overall_status == "PASS" else "estimated_or_conditional",
        "stage_results_json": json.dumps({
            "review_state": review_state,
            "fiber_status": fiber_status,
            "construction_status": construction_status,
            "pending_count": pending_count,
        }, ensure_ascii=False),
    }