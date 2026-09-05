# -*- coding: utf-8 -*-
"""
施工指令工具（PROD）1785839947624「代码执行」完整可粘贴修复片段
=============================================================
用法：在 Dify 网页端代码编辑器中，按下方标注“替换位置”逐段替换。
整节点替换文件过大，这里给每个修复点提供【完整函数/完整代码块】，不含省略号。
另：代码节点右侧“输出变量”需手动新增：
  environment_pending_count(number)
  manual_package_count(number)
  pending_review_items_json(string)
"""

# ============================================================
# 替换位置 1（CON-06）：fiber_pending 赋值
# 原代码：
#   fiber_pending = bool(
#       fiber_conflicts
#       or fiber_status == "待确认"
#   )
# 替换为：
# ============================================================
fiber_pending = bool(
    fiber_conflicts
    or fiber_status in ("待确认", "失败", "FAILED", "解析失败")
)

# ============================================================
# 替换位置 2（CON-02）：object_records 构建段
# 原代码从 “object_records = []” 到 cables 循环结束；整体替换为：
# ============================================================
object_records = []


def _record(source_kind, item, obj_type, raw_type, code, location, environment):
    return {
        "object_type": obj_type,
        "raw_type": raw_type,
        "object_code": code,
        "object_id": str(item.get("id") or f"{source_kind}:{code}"),
        "location": location,
        "environment": environment,
        "source_kind": source_kind,
    }


for item in boites:
    if not isinstance(item, dict):
        continue
    raw_type = str(item.get("type") or "")
    code = str(item.get("code") or item.get("id") or "")
    object_records.append(_record(
        "boite", item,
        normalize_type(raw_type, "boite"),
        raw_type, code,
        boite_location(item),
        detect_environment(item),
    ))

for item in cables:
    if not isinstance(item, dict):
        continue
    code = str(item.get("code") or item.get("id") or "")
    raw_type = str(item.get("type") or "CABLE")
    object_records.append(_record(
        "cable", item,
        "CABLE",
        raw_type, code,
        cable_location(item),
        detect_environment(item),
    ))

for item in ptechs:
    if not isinstance(item, dict):
        continue
    raw_type = str(item.get("type") or "PTECH")
    code = str(item.get("code") or item.get("id") or "")
    object_records.append(_record(
        "ptech", item,
        normalize_type(raw_type, "ptech"),
        raw_type, code,
        str(item.get("location") or "坐标未提供"),
        detect_environment(item),
    ))

for source_kind in ("site", "infrastructure"):
    for item in objects.get(source_kind) or []:
        if not isinstance(item, dict):
            continue
        raw_type = str(item.get("type") or source_kind.upper())
        code = str(item.get("code") or item.get("id") or "")
        object_records.append(_record(
            source_kind, item,
            normalize_type(raw_type, source_kind),
            raw_type, code,
            str(item.get("location") or "坐标未提供"),
            detect_environment(item),
        ))

# ============================================================
# 替换位置 3（CON-03/CON-04）：material_for_codes 完整函数
# 原函数从 “def material_for_codes(codes):” 到 “return list(grouped.values())[:30]”
# 整体替换为（不截断，数量取 quantity/最终数量，单位取 unit/单位）：
# ============================================================
def material_for_codes(codes, source_ids):
    matched = []
    for item in bom_items:
        if not isinstance(item, dict):
            continue
        item_ids = item.get("source_object_ids") or []
        if item_ids and source_ids:
            hit = bool(set(item_ids) & set(source_ids))
        else:
            hit = bool(set(str(c) for c in codes) & set(str(i) for i in item_ids))
        if not hit:
            continue

        material_code = item.get("material_code") or item.get("物料编码") or ""
        material_name = item.get("material_name") or item.get("物料名称") or ""
        unit = item.get("unit") or item.get("单位") or ""
        confidence = item.get("confidence_status") or item.get("置信状态") or ""
        evidence_status = item.get("evidence_status") or item.get("证据状态") or ""
        qty = item.get("quantity")
        if qty is None:
            qty = item.get("最终数量")

        key = (material_code, material_name, unit, confidence, evidence_status)
        matched.append({
            "物料编码": material_code,
            "物料名称": material_name,
            "单位": unit,
            "数量": qty,
            "置信状态": confidence,
            "证据状态": evidence_status,
            "_key": key,
        })

    grouped = {}
    for row in matched:
        key = row.pop("_key")
        if key not in grouped:
            grouped[key] = {
                "物料编码": row["物料编码"],
                "物料名称": row["物料名称"],
                "单位": row["单位"],
                "数量": row["数量"] if isinstance(row["数量"], (int, float)) else (0 if row["数量"] is not None else ""),
                "置信状态": row["置信状态"],
                "证据状态": row["证据状态"],
            }
        else:
            g = grouped[key]
            if isinstance(row["数量"], (int, float)) and isinstance(g["数量"], (int, float)):
                g["数量"] += row["数量"]
    # 完整返回；页面展示截断在输出端另用 displayed_materials[:30] + total/displayed
    return list(grouped.values())


# 原调用点：materials = material_for_codes(codes)
# 改为：
# materials = material_for_codes(
#     codes,
#     [r["object_id"] for r in records if r.get("object_id")],
# )

# ============================================================
# 替换位置 4（CON-05）：PCP_OFFICIAL_EVIDENCE 完整替换
# 原 PCP_OFFICIAL_EVIDENCE = [...] 整体替换为版本化静态证据：
# ============================================================
PCP_OFFICIAL_EVIDENCE = [
    {
        "category": "optical_testing",
        "text": "PCP光学测试包含数据准备、现场测试、测试评价及故障排查等阶段",
        "evidence_type": "versioned_static",
        "source": "Operational Procedure PCP Installation",
        "source_version": "v3.9",
        "section": "4.1-4.4 / Pages 40-44",
        "note": "版本化静态摘录；不等于本次动态检索已命中",
        "retrieval_status": "static_versioned",
    },
    {
        "category": "attenuation",
        "text": "Fiber-Fiber splice: Expected 0.1 dB, Maximum 0.2 dB",
        "evidence_type": "versioned_static",
        "source": "Operational Procedure PCP Installation",
        "source_version": "v3.9",
        "section": "Table 5 / Page 43",
        "note": "版本化静态摘录；不等于本次动态检索已命中",
        "retrieval_status": "static_versioned",
    },
    {
        "category": "attenuation",
        "text": "Fiber-SC/APC connector splice: Expected 0.3 dB, Maximum 0.5 dB",
        "evidence_type": "versioned_static",
        "source": "Operational Procedure PCP Installation",
        "source_version": "v3.9",
        "section": "Table 5 / Page 43",
        "note": "版本化静态摘录；不等于本次动态检索已命中",
        "retrieval_status": "static_versioned",
    },
]

# ============================================================
# 替换位置 5：procedure_ref 中“已验证参数”整段
# 只有当 procedure_hit 为 True 时才写入 verified_this_retrieval；
# 替换 procedure_ref 字典中固定写死“已验证参数”的部分：
# ============================================================
procedure_ref = {
    "规程名称": "Operational Procedure PCP Installation",
    "章节": "4.1-4.4；Table 5" if procedure_hit else "待确认",
    "版本": "v3.9" if version_verified else "待确认",
    "校验状态": "本次检索命中" if procedure_hit else "待人工确认-规程检索未命中",
    "适用范围": "仅用于PCP规程覆盖的光学接续/测试场景；不得直接作为PBO/BPE/CABLE全部安装步骤的官方依据",
    "证据来源": "versioned_static",
    "retrieval_status": "hit" if procedure_hit else "miss",
    "已验证参数": (
        {
            "Fiber-Fiber splice": {"expected": "0.1 dB", "maximum": "0.2 dB",
                                   "source": "PCP Table 5 / Page 43（版本化静态库）"},
            "Fiber-SC/APC connector splice": {"expected": "0.3 dB", "maximum": "0.5 dB",
                                              "source": "PCP Table 5 / Page 43（版本化静态库）"},
        }
        if procedure_hit
        else {}
    ),
}

# ============================================================
# 替换位置 6：最外层 return 增加三个字段
# 在 return 字典中（status/construction_status/.../work_packages 同级）追加：
# ============================================================
    "environment_pending_count": environment_pending_count,
    "manual_package_count": manual_package_count,
    "pending_review_items_json": json.dumps(pending_review_items, ensure_ascii=False),
