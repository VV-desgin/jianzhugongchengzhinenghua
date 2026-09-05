import json


def main(
    engineering_data: str,
    required_cores: int = 1,
    kb_result=None,
) -> dict:
    """
    纤芯分配工具压缩版（修复版）：
    - FIB-01：聚合占用与逐芯表一致性校验、满占用禁止新增、重复占用检出；
    - FIB-02：默认连续选芯（ALLOCATION_POLICY=contiguous，可切 smallest_free）；
    - FIB-04：cable_allocation_row_count/splice_location_count/splice_core_count 拆分；
    - FIB-05：required_cores 必须正整数，空光缆返回 NOT_APPLICABLE；
    - RAG-01：retrieval_status 显式输出，不参与确定性计算。
    """
    retrieval_status = "unused"
    if kb_result is not None:
        try:
            if isinstance(kb_result, (list, dict, str)) and str(kb_result).strip():
                retrieval_status = "available"
        except Exception:
            retrieval_status = "unavailable"

    try:
        data = engineering_data or {}

        if isinstance(data, str):
            text = data.strip()
            if not text:
                raise ValueError("engineering_data 为空，请绑定上游 engineering_data_text")
            data = json.loads(text)

        if isinstance(data, dict) and "engineering_data" in data and "objects" not in data:
            data = data.get("engineering_data") or {}

        if not isinstance(data, dict):
            raise ValueError("engineering_data 顶层必须是 JSON 对象")

        objects = data.get("objects") or {}
        cables = objects.get("cable") or data.get("cables") or []
        assignments_data = data.get("fiber_assignments") or []

        def to_int(value, default=0):
            try:
                if value is None:
                    return default
                if isinstance(value, bool):
                    return int(value)
                if isinstance(value, (int, float)):
                    return int(value)
                text_v = str(value).upper().replace("FO", "").strip()
                return int(float(text_v)) if text_v else default
            except Exception:
                return default

        def get_existing(cable_code):
            """返回同一光缆的全部逐芯占用；重复 cable_code 记录合并检查。"""
            rows = []
            for item in assignments_data:
                if not isinstance(item, dict):
                    continue
                if str(item.get("cable_code") or "") == cable_code:
                    assigned = item.get("assigned") or []
                    if isinstance(assigned, list):
                        rows.extend(assigned)
            return rows

        if isinstance(required_cores, bool) or required_cores is None:
            raise ValueError("required_cores 必须为正整数")
        try:
            requested_cores = int(required_cores)
        except (TypeError, ValueError):
            raise ValueError("required_cores 必须为正整数")
        if requested_cores < 1:
            raise ValueError("required_cores 必须为正整数")

        fiber_table = []
        splice_table = []
        conflicts = []

        target_cables = [c for c in cables if isinstance(c, dict) and c.get("code")]

        # 空光缆：明确 NOT_APPLICABLE，不伪装“正常”
        if not target_cables:
            empty_report = (
                "# 纤芯分配结果\n\n"
                "- 状态：NOT_APPLICABLE\n"
                "- 原因：无光缆对象或未提供纤芯业务，不执行分配\n"
            )
            empty_compact = {
                "status": "NOT_APPLICABLE",
                "required_cores": requested_cores,
                "fiber_count": 0,
                "cable_allocation_row_count": 0,
                "splice_location_count": 0,
                "splice_core_count": 0,
                "conflict_count": 0,
                "splice_table": [],
                "conflicts": [],
                "conflict_summary": "",
                "retrieval_status": retrieval_status,
            }
            return {
                "fiber_report": empty_report,
                "fiber_status": "NOT_APPLICABLE",
                "fiber_count": 0,
                "splice_count": 0,
                "conflict_count": 0,
                "fiber_result_json": json.dumps(empty_compact, ensure_ascii=False, separators=(",", ":")),
                "cable_allocation_row_count": 0,
                "splice_location_count": 0,
                "splice_core_count": 0,
                "retrieval_status": retrieval_status,
            }

        ALLOCATION_POLICY = "contiguous"  # 可改为 "smallest_free"

        for cable in target_cables:
            code = str(cable.get("code"))
            capacity = to_int(cable.get("capacite"), 0)
            modulo = max(1, to_int(cable.get("modulo"), 1))

            upstream = str(
                cable.get("origine")
                or cable.get("start_device")
                or cable.get("upstream_device")
                or ""
            )
            downstream = str(
                cable.get("extremite")
                or cable.get("end_device")
                or cable.get("downstream_device")
                or ""
            )

            if capacity <= 0:
                conflicts.append({
                    "冲突类型": "容量缺失或无效",
                    "光缆": code,
                    "详情": f"光缆容量为 {capacity}，无法执行纤芯分配",
                    "严重程度": "ERROR",
                })
                continue

            existing = get_existing(code)

            # 重复逐芯占用检测
            seen_pos = {}
            duplicate_found = False
            for item in existing:
                pos = (
                    to_int(item.get("tube"), 0),
                    to_int(item.get("fiber"), 0),
                    to_int(item.get("core"), 0),
                )
                if pos in seen_pos:
                    duplicate_found = True
                    conflicts.append({
                        "冲突类型": "重复占用记录",
                        "光缆": code,
                        "详情": f"同一光缆存在重复逐芯占用 {pos}",
                        "严重程度": "ERROR",
                    })
                seen_pos[pos] = True

            occupied = set(seen_pos.keys())
            if duplicate_found:
                continue  # 数据不一致，不做新增分配

            # 聚合占用与逐芯表一致性
            agg_used = to_int(cable.get("nb_fibre_util"), -1)
            if agg_used >= 0 and existing:
                if len(existing) != agg_used:
                    conflicts.append({
                        "冲突类型": "聚合与逐芯占用不一致",
                        "光缆": code,
                        "详情": f"聚合已用 {agg_used} 芯，逐芯表 {len(existing)} 条",
                        "严重程度": "ERROR",
                    })
            if agg_used > 0 and not existing:
                conflicts.append({
                    "冲突类型": "仅聚合占用无逐芯表",
                    "光缆": code,
                    "详情": f"聚合已用 {agg_used} 芯但没有逐芯占用表，禁止猜测空闲",
                    "严重程度": "ERROR",
                })
                continue
            if len(occupied) >= capacity:
                conflicts.append({
                    "冲突类型": "满占用/超容量",
                    "光缆": code,
                    "详情": f"已占用 {len(occupied)} 芯，容量仅 {capacity} 芯，禁止新增分配",
                    "严重程度": "ERROR",
                })
                continue

            cores_per_tube = max(1, capacity // modulo)
            total_slots = modulo * cores_per_tube
            occupied_nums = set()
            for (tube, fiber_no, core) in occupied:
                occupied_nums.add((tube - 1) * cores_per_tube + core)

            free_nums = [n for n in range(1, total_slots + 1) if n not in occupied_nums]
            new_assignments = []
            chosen_nums = []

            if ALLOCATION_POLICY == "contiguous":
                for i in range(0, len(free_nums) - requested_cores + 1):
                    window = free_nums[i:i + requested_cores]
                    if window[-1] - window[0] == requested_cores - 1:
                        chosen_nums = window
                        break
            else:
                chosen_nums = free_nums[:requested_cores]

            if len(chosen_nums) >= requested_cores:
                for n in chosen_nums:
                    tube = (n - 1) // cores_per_tube + 1
                    core = (n - 1) % cores_per_tube + 1
                    position = (tube, 1, core)
                    row = {
                        "光缆编码": code,
                        "上游设备": upstream,
                        "下游设备": downstream,
                        "管号": tube,
                        "纤号": 1,
                        "芯号": core,
                        "状态": "occupied",
                    }
                    new_assignments.append(row)
                    fiber_table.append(row)
                    occupied.add(position)
            else:
                conflicts.append({
                    "冲突类型": "可用连续纤芯不足",
                    "光缆": code,
                    "详情": f"需要连续 {requested_cores} 芯，实际无连续空闲区间",
                    "严重程度": "ERROR",
                })

            total_used = len(occupied)
            if total_used > capacity:
                conflicts.append({
                    "冲突类型": "超容量",
                    "光缆": code,
                    "详情": f"已分配 {total_used} 芯，容量仅 {capacity} 芯",
                    "严重程度": "ERROR",
                })

            assigned_positions = [
                f"{item['管号']}-{item['纤号']}-{item['芯号']}"
                for item in new_assignments
            ]

            splice_table.append({
                "光缆编码": code,
                "上游设备": upstream,
                "下游设备": downstream,
                "纤芯分配": ",".join(assigned_positions),
                "纤芯数": len(new_assignments),
            })

        status = "待确认" if conflicts else "正常"

        conflict_summary = "；".join(
            f"{item.get('光缆', '')} {item.get('冲突类型', '')}: {item.get('详情', '')}"
            for item in conflicts
        )

        lines = [
            "# 纤芯分配结果",
            "",
            f"- 状态：{status}",
            f"- 光缆数量：{len(splice_table)} 条",
            f"- 分配纤芯：{len(fiber_table)} 芯",
            f"- 冲突记录：{len(conflicts)} 条",
            "",
            "## 一、按光缆汇总的接续表",
            "",
            "| 光缆编码 | 上游设备 | 下游设备 | 纤芯分配 | 纤芯数 |",
            "|---|---|---|---|---:|",
        ]
        for item in splice_table:
            lines.append(
                f"| {item['光缆编码']} | {item['上游设备']} | {item['下游设备']} | "
                f"{item['纤芯分配']} | {item['纤芯数']} |"
            )
        if conflicts:
            lines.extend(["", "## 二、冲突检查", "", "| 光缆 | 冲突类型 | 详情 | 严重程度 |", "|---|---|---|---|"])
            for c in conflicts:
                lines.append(
                    f"| {c.get('光缆', '')} | {c.get('冲突类型', '')} | "
                    f"{c.get('详情', '')} | {c.get('严重程度', '')} |"
                )
        fiber_report = "\n".join(lines) + "\n\n---\n"

        splice_location_count = 0  # 无真实接头/逐芯熔接输入时不虚报
        splice_core_count = 0

        compact_result = {
            "status": status,
            "required_cores": requested_cores,
            "fiber_count": len(fiber_table),
            "cable_allocation_row_count": len(splice_table),
            "splice_location_count": splice_location_count,
            "splice_core_count": splice_core_count,
            "splice_count": len(splice_table),
            "conflict_count": len(conflicts),
            "splice_table": splice_table,
            "conflicts": conflicts,
            "conflict_summary": conflict_summary,
            "retrieval_status": retrieval_status,
        }

        return {
            "fiber_report": fiber_report,
            "fiber_status": status,
            "fiber_count": len(fiber_table),
            "splice_count": len(splice_table),
            "conflict_count": len(conflicts),
            "fiber_result_json": json.dumps(compact_result, ensure_ascii=False, separators=(",", ":")),
            "cable_allocation_row_count": len(splice_table),
            "splice_location_count": splice_location_count,
            "splice_core_count": splice_core_count,
            "retrieval_status": retrieval_status,
        }

    except Exception as exc:
        error_text = str(exc)
        try:
            if isinstance(required_cores, bool) or required_cores is None:
                cores_out = 0
            else:
                cores_out = max(0, int(required_cores))
        except Exception:
            cores_out = 0

        fail_compact = {
            "status": "失败",
            "required_cores": cores_out,
            "fiber_count": 0,
            "cable_allocation_row_count": 0,
            "splice_location_count": 0,
            "splice_core_count": 0,
            "conflict_count": 1,
            "splice_table": [],
            "conflicts": [{
                "冲突类型": "运行异常",
                "光缆": "",
                "详情": error_text,
                "严重程度": "ERROR",
            }],
            "conflict_summary": error_text,
            "retrieval_status": retrieval_status,
        }
        return {
            "fiber_report": f"# 纤芯分配失败\n\n错误：{error_text}\n",
            "fiber_status": "失败",
            "fiber_count": 0,
            "splice_count": 0,
            "conflict_count": 1,
            "fiber_result_json": json.dumps(fail_compact, ensure_ascii=False, separators=(",", ":")),
            "cable_allocation_row_count": 0,
            "splice_location_count": 0,
            "splice_core_count": 0,
            "retrieval_status": retrieval_status,
        }
