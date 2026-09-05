import json


def main(
    engineering_data: str,
    bom_result: str = "",
    fiber_result: str = "",
    kb_result=None,
) -> dict:

    # =========================================================
    # 1. 基础工具
    # =========================================================
    def parse(value, default):
        if value is None or value == "":
            return default

        if isinstance(value, (dict, list)):
            return value

        try:
            result = json.loads(value)

            # 兼容 JSON 字符串再次包 JSON
            if isinstance(result, str):
                try:
                    return json.loads(result)
                except Exception:
                    return result

            return result

        except Exception:
            return default

    def to_number(value):
        try:
            if value is None or value == "":
                return None
            return float(value)
        except Exception:
            return None

    def flatten_text(value):
        parts = []

        if isinstance(value, dict):
            for v in value.values():
                parts.extend(flatten_text(v))

        elif isinstance(value, list):
            for v in value:
                parts.extend(flatten_text(v))

        elif value is not None:
            parts.append(str(value))

        return parts

    def evidence(
        category,
        text,
        evidence_type,
        source="",
        section="",
        note="",
    ):
        return {
            "category": str(category),
            "text": str(text),
            "evidence_type": str(evidence_type),
            "source": str(source),
            "section": str(section),
            "note": str(note),
        }

    # =========================================================
    # 2. engineering_data 解析
    # =========================================================
    eng = parse(
        engineering_data,
        {
            "objects": {
                "boite": [],
                "cable": [],
                "ptech": [],
            }
        },
    )

    # 兼容外层 engineering_data
    if (
        isinstance(eng, dict)
        and "engineering_data" in eng
        and "objects" not in eng
    ):
        eng = parse(
            eng.get("engineering_data"),
            {
                "objects": {
                    "boite": [],
                    "cable": [],
                    "ptech": [],
                }
            },
        )

    if not isinstance(eng, dict):
        eng = {
            "objects": {
                "boite": [],
                "cable": [],
                "ptech": [],
            }
        }

    objects = eng.get("objects") or {}

    boites = objects.get("boite") or []
    cables = objects.get("cable") or []
    ptechs = objects.get("ptech") or []

    # =========================================================
    # 3. BOM 解析
    # =========================================================
    bom_raw = parse(bom_result, [])

    def extract_bom_items(value):

        if isinstance(value, list):
            return value

        if not isinstance(value, dict):
            return []

        for key in (
            "bom_items",
            "items",
            "bom",
            "result",
            "data",
            "standard_bom_table",
        ):
            candidate = value.get(key)

            if isinstance(candidate, list):
                return candidate

            if isinstance(candidate, str):
                parsed = parse(candidate, [])

                if isinstance(parsed, list):
                    return parsed

                if isinstance(parsed, dict):
                    nested = extract_bom_items(parsed)
                    if nested:
                        return nested

            if isinstance(candidate, dict):
                nested = extract_bom_items(candidate)
                if nested:
                    return nested

        return []

    bom_items = extract_bom_items(bom_raw)

    # =========================================================
    # 4. Fiber 结果解析
    # =========================================================
    fiber_parse_failed = False
    if isinstance(fiber_result, str) and str(fiber_result).strip():
        try:
            json.loads(fiber_result)
        except Exception:
            fiber_parse_failed = True
    fiber_data = parse(fiber_result, {})

    if isinstance(fiber_data, dict):

        nested_fiber_json = fiber_data.get(
            "fiber_result_json"
        )

        if nested_fiber_json:
            parsed_nested = parse(
                nested_fiber_json,
                {},
            )

            if isinstance(parsed_nested, dict):
                fiber_data = parsed_nested

    if not isinstance(fiber_data, dict):
        fiber_data = {}

    fiber_table = (
        fiber_data.get("fiber_table")
        or fiber_data.get("fiber_assignments")
        or []
    )

    splice_table = (
        fiber_data.get("splice_table")
        or fiber_data.get("splices")
        or []
    )

    fiber_conflicts = (
        fiber_data.get("conflicts")
        or []
    )

    fiber_status = str(
        fiber_data.get("status")
        or fiber_data.get("fiber_status")
        or ""
    ).strip()
    if fiber_parse_failed:
        fiber_status = "解析失败"

    fiber_pending = bool(
        fiber_conflicts
        or fiber_status in ("待确认", "失败", "FAILED", "解析失败")
    )

    # =========================================================
    # 5. 知识库证据识别
    # =========================================================
    kb_text = " ".join(
        flatten_text(kb_result)
    )

    kb_text_lower = kb_text.lower()

    procedure_hit = bool(
        kb_text
        and (
            "operational procedure" in kb_text_lower
            or "pcp installation" in kb_text_lower
            or "pcp" in kb_text_lower
            or "table 5" in kb_text_lower
        )
    )

    version_verified = bool(
        "v3.9" in kb_text_lower
    )

    table5_hit = bool(
        "table 5" in kb_text_lower
        or (
            "fiber-fiber splice" in kb_text_lower
            and "0.1" in kb_text_lower
            and "0.2" in kb_text_lower
        )
    )

    optical_test_hit = bool(
        (
            "4.1" in kb_text
            and "4.2" in kb_text
            and "4.3" in kb_text
        )
        or "on-field testing" in kb_text_lower
        or "testing evaluation" in kb_text_lower
    )

    # =========================================================
    # 6. 施工对象类型标准化
    # =========================================================
    def normalize_type(raw_type, source_kind):

        text = str(
            raw_type or ""
        ).strip().upper()

        if source_kind == "cable":
            return "CABLE"

        if "PBO" in text:
            return "PBO"

        if "BPE" in text:
            return "BPE"

        return "UNKNOWN"

    # =========================================================
    # 7. 施工环境识别
    # =========================================================
    # 核心原则：
    # 只根据工程数据明确字段判断。
    # 不再：
    # PBO → 默认架空
    # BPE → 默认地下
    # =========================================================
    def detect_environment(obj):

        mode = str(
            obj.get("mode_pose")
            or obj.get("installation_mode")
            or obj.get("pose_mode")
            or obj.get("mode")
            or ""
        ).strip().upper()

        if mode in (
            "AERIEN",
            "AÉRIEN",
            "POLE",
            "AERIAL",
            "OVERHEAD",
        ):
            return "架空"

        if mode in (
            "CHAMBRE",
            "SOUTERRAIN",
            "UNDERGROUND",
            "MANHOLE",
        ):
            return "地下"

        if mode in (
            "CONDUIT",
            "DUCT",
            "FOURREAU",
            "PIPE",
        ):
            return "管道"

        if mode in (
            "INTERIEUR",
            "INTÉRIEUR",
            "INDOOR",
        ):
            return "室内"

        if mode in (
            "FACADE",
            "FAÇADE",
            "WALL",
        ):
            return "墙面/立面"

        return "待确认"

    # =========================================================
    # 8. 位置信息
    # =========================================================
    def boite_location(item):

        x = item.get("x")
        y = item.get("y")

        if (
            x is not None
            and x != ""
            and y is not None
            and y != ""
        ):
            return f"X={x}, Y={y}"

        return "坐标未提供"

    def cable_location(item):

        origin = str(
            item.get("origine")
            or item.get("origin")
            or ""
        ).strip()

        end = str(
            item.get("extremite")
            or item.get("destination")
            or ""
        ).strip()

        if origin or end:
            return (
                f"{origin or '起点未提供'}"
                f" → "
                f"{end or '终点未提供'}"
            )

        return "起止点未提供"

    # =========================================================
    # 9. 生成对象记录
    # =========================================================
    object_records = []

    def _record(source_kind, item, obj_type, raw_type, code_value, location, environment):
        return {
            "object_type": obj_type,
            "raw_type": raw_type,
            "object_code": code_value,
            "object_id": str(item.get("id") or f"{source_kind}:{code_value}"),
            "location": location,
            "environment": environment,
            "source_kind": source_kind,
        }

    for item in boites:
        if not isinstance(item, dict):
            continue
        raw_type = str(item.get("type") or "")
        code_value = str(item.get("code") or item.get("id") or "")
        object_records.append(_record(
            "boite", item,
            normalize_type(raw_type, "boite"),
            raw_type, code_value,
            boite_location(item),
            detect_environment(item),
        ))

    for item in cables:
        if not isinstance(item, dict):
            continue
        raw_type = str(item.get("type") or "CABLE")
        code_value = str(item.get("code") or item.get("id") or "")
        object_records.append(_record(
            "cable", item,
            "CABLE",
            raw_type, code_value,
            cable_location(item),
            detect_environment(item),
        ))

    for item in ptechs:
        if not isinstance(item, dict):
            continue
        raw_type = str(item.get("type") or "PTECH")
        code_value = str(item.get("code") or item.get("id") or "")
        object_records.append(_record(
            "ptech", item,
            normalize_type(raw_type, "ptech"),
            raw_type, code_value,
            str(item.get("location") or "坐标未提供"),
            detect_environment(item),
        ))

    for source_kind in ("site", "infrastructure"):
        for item in objects.get(source_kind) or []:
            if not isinstance(item, dict):
                continue
            raw_type = str(item.get("type") or source_kind.upper())
            code_value = str(item.get("code") or item.get("id") or "")
            object_records.append(_record(
                source_kind, item,
                normalize_type(raw_type, source_kind),
                raw_type, code_value,
                str(item.get("location") or "坐标未提供"),
                detect_environment(item),
            ))

    # =========================================================
    # 10. 工序候选模板
    # =========================================================
    # 注意：
    # 这些是系统根据工程对象形成的施工工序候选。
    # 不是直接摘录 PCP，因此统一标记：
    # engineering_inference / internal_process
    # =========================================================
    PROCESS_TEMPLATES = {

        "PBO": {
            "name": "PBO / FAT类箱体施工",
            "materials": "箱体、固定件、光缆附件、标签等，最终以BOM为准",

            "preconditions": [
                "核对设计对象编码及安装位置",
                "核对BOM物料及待确认项",
                "核对施工环境和安装方式",
                "核对相关光缆及纤芯接续数据",
            ],

            "steps": [
                {
                    "step": 1,
                    "action": "对象与位置核对",
                    "detail": "核实施工对象、设计位置及现场条件",
                },
                {
                    "step": 2,
                    "action": "安装条件确认",
                    "detail": "确认固定方式、安装环境及配套材料后实施安装",
                },
                {
                    "step": 3,
                    "action": "箱体安装",
                    "detail": "按审定设计完成箱体固定与安装",
                },
                {
                    "step": 4,
                    "action": "光缆引入与固定",
                    "detail": "按审定路由完成相关光缆引入、固定和保护",
                },
                {
                    "step": 5,
                    "action": "纤芯接续",
                    "detail": "按确定性纤芯分配结果执行接续；存在待确认项时不得直接施工",
                },
                {
                    "step": 6,
                    "action": "标签与记录",
                    "detail": "完成设备、光缆标识并保存施工记录",
                },
            ],

            "quality": [
                "安装位置、对象编码和设计成果保持一致",
                "相关材料以已确认BOM为准",
                "纤芯接续以确定性Fiber结果为准",
            ],

            "safety": [
                "施工前完成现场风险确认和安全交底",
                "根据实际施工环境执行对应防护措施",
            ],

            "tests": [
                "完成施工后应按项目适用测试要求形成测试记录",
            ],

            "acceptance": [
                "安装对象、位置和标识应与审定设计一致",
                "存在待确认物料、环境或纤芯冲突时不得判定正式验收通过",
            ],
        },

        "BPE": {
            "name": "BPE / FDT类箱体施工",
            "materials": "箱体、固定件、光缆附件、标签等，最终以BOM为准",

            "preconditions": [
                "核对设计对象编码及安装位置",
                "核对BOM物料及待确认项",
                "确认实际安装方式和现场环境",
                "核对相关光缆及纤芯接续数据",
            ],

            "steps": [
                {
                    "step": 1,
                    "action": "对象与位置核对",
                    "detail": "核实施工对象、设计位置及现场安装条件",
                },
                {
                    "step": 2,
                    "action": "安装方式确认",
                    "detail": "根据现场及审定设计确认杆装、壁挂或其他安装方式",
                },
                {
                    "step": 3,
                    "action": "箱体安装",
                    "detail": "按确认后的安装方式完成箱体固定",
                },
                {
                    "step": 4,
                    "action": "光缆引入与固定",
                    "detail": "按审定路由完成光缆引入、固定和必要保护",
                },
                {
                    "step": 5,
                    "action": "纤芯接续",
                    "detail": "按确定性Fiber结果执行接续，不得由生成模型重新分配纤芯",
                },
                {
                    "step": 6,
                    "action": "标签与记录",
                    "detail": "完成设备及相关光缆标识并记录施工结果",
                },
            ],

            "quality": [
                "安装位置、类型及对象编码应与设计数据一致",
                "材料使用必须与确认后的BOM一致",
                "纤芯接续必须与确定性Fiber结果一致",
            ],

            "safety": [
                "施工前完成现场风险确认和安全交底",
                "根据实际施工环境执行对应防护措施",
            ],

            "tests": [
                "完成施工后应按项目适用测试要求形成测试记录",
            ],

            "acceptance": [
                "设备安装、材料、标签及纤芯接续应与审定成果一致",
                "存在任何待确认条件时不得自动输出正式验收通过",
            ],
        },

        "CABLE": {
            "name": "光缆敷设施工",
            "materials": "光缆、固定及保护材料、标签等，最终以BOM为准",

            "preconditions": [
                "核对光缆编码、路由及起止关系",
                "核对施工环境和敷设方式",
                "核对BOM及相关施工材料",
            ],

            "steps": [
                {
                    "step": 1,
                    "action": "施工路由核对",
                    "detail": "核对审定设计中的光缆路由、对象编码和起止关系",
                },
                {
                    "step": 2,
                    "action": "施工环境确认",
                    "detail": "确认架空、地下、管道、室内或其他实际施工环境",
                },
                {
                    "step": 3,
                    "action": "光缆敷设",
                    "detail": "按审定路由和确认后的施工方式实施光缆敷设",
                },
                {
                    "step": 4,
                    "action": "固定与保护",
                    "detail": "完成必要固定、保护和现场整理",
                },
                {
                    "step": 5,
                    "action": "标签与记录",
                    "detail": "完成光缆标识并保存施工记录",
                },
            ],

            "quality": [
                "光缆编码、路由和设计对象应保持可追溯",
                "材料及数量以已确认BOM为准",
            ],

            "safety": [
                "施工前完成现场风险确认和安全交底",
                "根据实际敷设环境采用对应安全措施",
            ],

            "tests": [
                "根据项目适用范围执行光学测试或通断检查，并保存真实测试结果",
            ],

            "acceptance": [
                "光缆路由、标签和施工记录应与审定设计一致",
                "没有真实测试数据时不得输出“测试已通过”",
            ],
        },
    }

    # =========================================================
    # 11. 环境附加要求
    # =========================================================
    # 这些内容属于工程安全推演，
    # 不是 PCP 原文，因此证据类型为 engineering_inference。
    # =========================================================
    ENV_REQUIREMENTS = {

        "架空": {
            "safety": [
                "核实施工高度及高处作业风险",
                "根据现场安全管理要求采取防坠落措施",
                "施工前确认天气及杆路状态",
            ],
            "quality": [
                "检查固定件和支撑条件",
            ],
            "tools": [
                "根据现场条件配置高处作业防护及施工工具",
            ],
        },

        "地下": {
            "safety": [
                "施工前检查地下空间通风、积水及其他现场风险",
                "按现场安全管理要求配置照明和防护",
            ],
            "quality": [
                "检查防水、封堵及现场恢复条件",
            ],
            "tools": [
                "根据现场条件配置地下施工工具和防护设施",
            ],
        },

        "管道": {
            "safety": [
                "核查管道、人孔或管井施工环境",
                "按现场安全要求设置防护",
            ],
            "quality": [
                "施工前核实管道路由及可用性",
            ],
            "tools": [
                "根据施工方案配置穿管及牵引工具",
            ],
        },

        "室内": {
            "safety": [
                "核实施工区域消防、用电及人员作业条件",
            ],
            "quality": [
                "施工完成后检查现场恢复及封堵",
            ],
            "tools": [
                "根据现场条件配置室内安装工具",
            ],
        },

        "墙面/立面": {
            "safety": [
                "确认墙面、立面施工高度及现场安全条件",
            ],
            "quality": [
                "确认固定位置和建筑表面恢复要求",
            ],
            "tools": [
                "根据实际安装方案配置固定和防护工具",
            ],
        },

        "待确认": {
            "safety": [],
            "quality": [],
            "tools": [],
        },
    }

    # =========================================================
    # 12. BOM匹配
    # =========================================================
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
        return list(grouped.values())

    def material_needs_review(materials):

        blocking_states = {
            "EVIDENCE_BLOCKED",
            "NO_RULE_MATCH",
            "CONDITION_NOT_VERIFIED",
            "SEPARATE_EVIDENCE_REQUIRED",
        }

        for item in materials:

            confidence = str(
                item.get("置信状态")
                or ""
            ).strip()

            evidence_status = str(
                item.get("证据状态")
                or ""
            ).strip()

            material_code = str(
                item.get("物料编码")
                or ""
            ).strip()

            if confidence == "待人工确认":
                return True

            if evidence_status in blocking_states:
                return True

            if material_code in (
                "",
                "【待确认】",
            ):
                return True

        return False

    # =========================================================
    # 13. Fiber 接续摘要
    # =========================================================
    splice_by_cable = {}

    for item in splice_table:

        if not isinstance(item, dict):
            continue

        cable_code = str(
            item.get("光缆编码")
            or item.get("cable_code")
            or ""
        )

        if not cable_code:
            continue

        splice_by_cable[cable_code] = {
            "纤芯数": (
                item.get("纤芯数")
                or item.get("fiber_count")
                or 0
            ),
            "纤芯分配": str(
                item.get("纤芯分配")
                or item.get("allocation")
                or ""
            ),
        }

    # =========================================================
    # 14. 按 对象类型 + 明确环境 分组
    # =========================================================
    groups = {}

    for item in object_records:

        obj_type = item["object_type"]
        env = item["environment"]

        group_type = (
            "UNKNOWN"
            if obj_type == "UNKNOWN"
            else obj_type
        )

        key = (
            group_type,
            env,
        )

        if key not in groups:
            groups[key] = []

        groups[key].append(item)

    # =========================================================
    # 15. PCP官方证据
    # =========================================================
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

    # =========================================================
    # 16. 生成工作包
    # =========================================================
    full_packages = []
    compact_packages = []

    pending_review_items = []

    sorted_groups = sorted(
        groups.items(),
        key=lambda x: (
            x[0][0],
            x[0][1],
        ),
    )

    for index, (
        (obj_type, env),
        records,
    ) in enumerate(
        sorted_groups,
        start=1,
    ):

        package_id = f"WP-{index:02d}"

        codes = [
            item["object_code"]
            for item in records
            if item["object_code"]
        ]

        raw_types = sorted(
            set(
                item["raw_type"]
                for item in records
                if item["raw_type"]
            )
        )

        locations = [
            item["location"]
            for item in records
        ]

        materials = material_for_codes(
            codes,
            [r["object_id"] for r in records if r.get("object_id")]
        )

        template = PROCESS_TEMPLATES.get(
            obj_type
        )

        evidence_details = []

        # -----------------------------------------------------
        # 未知对象
        # -----------------------------------------------------
        if template is None:

            package = {
                "工作包编号": package_id,
                "对象类型": "UNKNOWN",
                "对象名称": "未知施工对象",
                "施工环境": env,
                "对象数量": len(records),
                "对象编码": codes,
                "施工地点": locations,
                "涉及原始类型": raw_types,

                "所需材料": materials,

                "前置条件": [
                    "待人工确认"
                ],

                "施工步骤": [],

                "工艺要求": [
                    "待人工确认"
                ],

                "安全要求": [
                    "待人工确认"
                ],

                "测试要求": [
                    "待人工确认"
                ],

                "验收标准": [
                    "待人工确认"
                ],

                "工序候选": [],

                "证据明细": [
                    evidence(
                        "object_mapping",
                        "当前对象类型无法匹配确定性施工模板",
                        "pending_confirmation",
                        "engineering_data",
                        "",
                        "需人工确认对象类型及适用工序",
                    )
                ],

                "规程引用": {
                    "规程名称": "未匹配",
                    "章节": "待确认",
                    "版本": "待确认",
                    "校验状态": "待人工确认",
                    "适用范围": "待确认",
                },

                "环境附加要求": {
                    "额外工具": [],
                    "环境类型": env,
                },

                "需要人工确认": True,
                "待确认原因": [
                    "对象类型无法匹配确定性施工规则"
                ],
            }

        # -----------------------------------------------------
        # 已知对象
        # -----------------------------------------------------
        else:

            env_req = ENV_REQUIREMENTS.get(
                env,
                ENV_REQUIREMENTS["待确认"],
            )

            if not materials:
                materials = [
                    {
                        "物料编码": "",
                        "物料名称": template["materials"],
                        "单位": "",
                        "数量": "详见BOM",
                        "置信状态": "待人工确认",
                        "证据状态": "NO_BOM_MATCH",
                    }
                ]

            material_pending = material_needs_review(
                materials
            )

            environment_pending = (
                env == "待确认"
            )

            # 基础工程流程属于工程推演/内部流程
            for step in template["steps"]:
                evidence_details.append(
                    evidence(
                        "construction_step",
                        (
                            f"{step['action']}："
                            f"{step['detail']}"
                        ),
                        "engineering_inference",
                        "内部施工工作包模板",
                        "",
                        "不是PCP原文直接摘录",
                    )
                )

            for item in template["safety"]:
                evidence_details.append(
                    evidence(
                        "safety",
                        item,
                        "engineering_inference",
                        "内部工程安全模板",
                        "",
                        "需结合现场安全管理制度确认",
                    )
                )

            for item in env_req.get(
                "safety",
                [],
            ):
                evidence_details.append(
                    evidence(
                        "environment_safety",
                        f"[{env}] {item}",
                        "engineering_inference",
                        "环境施工条件推演",
                        "",
                        "不是PCP原文直接摘录",
                    )
                )

            # PCP证据仅作为明确注明适用范围的官方参考
            evidence_details.extend(
                PCP_OFFICIAL_EVIDENCE
            )

            safety = list(
                template["safety"]
            ) + [
                f"[{env}] {item}"
                for item in env_req.get(
                    "safety",
                    [],
                )
            ]

            quality = list(
                template["quality"]
            ) + [
                f"[{env}] {item}"
                for item in env_req.get(
                    "quality",
                    [],
                )
            ]

            pending_reasons = []

            if environment_pending:
                pending_reasons.append(
                    "施工环境未由工程数据明确提供"
                )

            if material_pending:
                pending_reasons.append(
                    "BOM存在候选物料或证据未闭环项"
                )

            if fiber_pending:
                pending_reasons.append(
                    "Fiber结果存在待确认状态或冲突"
                )

            # PCP KB没有命中不代表对象施工不能生成，
            # 但官方规程证据不可标记为已验证。
            if not procedure_hit:
                pending_reasons.append(
                    "PCP规程知识库本次检索未命中"
                )

            package_need_review = bool(
                pending_reasons
            )

            procedure_ref = {
                "规程名称": "Operational Procedure PCP Installation",
                "章节": (
                    "4.1-4.4；Table 5"
                    if procedure_hit
                    else "待确认"
                ),
                "版本": (
                    "v3.9"
                    if version_verified
                    else "待确认"
                ),
                "校验状态": (
                    "本次检索命中"
                    if procedure_hit
                    else "待人工确认-规程检索未命中"
                ),
                "适用范围": (
                    "仅用于PCP规程覆盖的光学接续/测试场景；"
                    "不得直接作为PBO/BPE/CABLE全部安装步骤的官方依据"
                ),
                "证据来源": "versioned_static",
                "retrieval_status": (
                    "hit"
                    if procedure_hit
                    else "miss"
                ),
                "已验证参数": (
                    {
                        "Fiber-Fiber splice": {
                            "expected": "0.1 dB",
                            "maximum": "0.2 dB",
                            "source": "PCP Table 5 / Page 43（版本化静态库）",
                        },
                        "Fiber-SC/APC connector splice": {
                            "expected": "0.3 dB",
                            "maximum": "0.5 dB",
                            "source": "PCP Table 5 / Page 43（版本化静态库）",
                        },
                    }
                    if procedure_hit
                    else {}
                ),
            }

            package = {
                "工作包编号": package_id,
                "对象类型": obj_type,
                "对象名称": template["name"],
                "施工环境": env,
                "对象数量": len(records),
                "对象编码": codes,
                "施工地点": locations,
                "涉及原始类型": raw_types,

                "所需材料": materials,

                "前置条件": template[
                    "preconditions"
                ],

                "施工步骤": template[
                    "steps"
                ],

                "工艺要求": quality,

                "安全要求": safety,

                "测试要求": template[
                    "tests"
                ],

                "验收标准": template[
                    "acceptance"
                ],

                # 不再：对象类型 → PCP固定章节
                "工序候选": [
                    {
                        "工序": step["action"],
                        "来源类型": "engineering_inference",
                        "PCP章节": "不直接硬映射",
                    }
                    for step in template["steps"]
                ],

                "证据明细": evidence_details,

                "规程引用": procedure_ref,

                "环境附加要求": {
                    "额外工具": env_req.get(
                        "tools",
                        [],
                    ),
                    "环境类型": env,
                    "证据类型": (
                        "engineering_inference"
                    ),
                },

                "需要人工确认": package_need_review,

                "待确认原因": pending_reasons,
            }

        # =====================================================
        # CABLE 纤芯摘要
        # =====================================================
        if obj_type == "CABLE":

            matched_fibers = []

            for code in codes:

                if code in splice_by_cable:

                    matched_fibers.append(
                        {
                            "光缆编码": code,
                            **splice_by_cable[
                                code
                            ],
                        }
                    )

            package[
                "纤芯接续摘要"
            ] = matched_fibers[:30]

        # =====================================================
        # 汇总待确认项目
        # =====================================================
        if package.get(
            "需要人工确认"
        ):

            reasons = (
                package.get(
                    "待确认原因"
                )
                or [
                    "需要人工确认"
                ]
            )

            pending_review_items.append(
                {
                    "工作包编号": package_id,
                    "对象类型": obj_type,
                    "对象编码": codes[:20],
                    "施工环境": env,
                    "问题": "；".join(
                        reasons
                    ),
                }
            )

        full_packages.append(
            package
        )

        compact_packages.append(
            {
                "工作包编号": package_id,
                "对象类型": obj_type,
                "对象名称": package[
                    "对象名称"
                ],
                "施工环境": env,
                "对象数量": len(records),
                "对象编码示例": codes[:10],

                "施工步骤数": len(
                    package.get(
                        "施工步骤"
                    )
                    or []
                ),

                "物料种类数": len(
                    package.get(
                        "所需材料"
                    )
                    or []
                ),

                "规程状态": (
                    package.get(
                        "规程引用",
                        {},
                    ).get(
                        "校验状态",
                        "待确认",
                    )
                ),

                "需要人工确认": bool(
                    package.get(
                        "需要人工确认"
                    )
                ),
            }
        )

    # =========================================================
    # 17. 未知对象
    # =========================================================
    unknown_objects = [
        {
            "对象编码": item[
                "object_code"
            ],
            "原始类型": item[
                "raw_type"
            ],
            "施工地点": item[
                "location"
            ],
            "施工环境": item[
                "environment"
            ],
            "问题": (
                "当前对象类型无法匹配"
                "确定性施工规则"
            ),
        }
        for item in object_records
        if (
            item["object_type"]
            == "UNKNOWN"
        )
    ]

    # =========================================================
    # 18. 总状态
    # =========================================================
    instruction_count = len(
        object_records
    )

    work_package_count = len(
        full_packages
    )

    unknown_count = len(
        unknown_objects
    )

    environment_pending_count = sum(
        1
        for item in object_records
        if item["environment"]
        == "待确认"
    )

    manual_package_count = sum(
        1
        for item in full_packages
        if item.get(
            "需要人工确认"
        )
    )

    # 只有所有关键条件都清楚，
    # 才允许输出“正常”
    if fiber_status in ("失败", "FAILED", "解析失败"):
        status = "失败"
    else:
        status = (
            "待确认"
            if (
                unknown_count > 0
                or environment_pending_count > 0
                or manual_package_count > 0
                or fiber_pending
            )
            else "正常"
        )

    summary = (
        f"共识别施工对象 {instruction_count} 个，"
        f"按对象类型和明确施工环境压缩为 "
        f"{work_package_count} 个施工工作包；"
        f"未知对象 {unknown_count} 个，"
        f"施工环境待确认对象 {environment_pending_count} 个，"
        f"需人工确认工作包 {manual_package_count} 个。"
    )

    # =========================================================
    # 19. Markdown报告
    # =========================================================
    lines = [
        "# 施工指令工作包汇总",
        "",
        f"- 施工对象：{instruction_count} 个",
        f"- 施工工作包：{work_package_count} 个",
        f"- 未知对象：{unknown_count} 个",
        (
            f"- 施工环境待确认："
            f"{environment_pending_count} 个"
        ),
        (
            f"- 需人工确认工作包："
            f"{manual_package_count} 个"
        ),
        (
            f"- Fiber冲突："
            f"{len(fiber_conflicts)} 条"
        ),
        f"- 当前状态：**{status}**",
        "",
        (
            "> 本施工指令区分“官方摘录、工程推演、内部流程、待确认”四类证据。"
        ),
        (
            "> 对象类型不得直接硬映射PCP章节；施工环境未由工程数据明确提供时，不进行自动猜测。"
        ),
        (
            "> 系统未接入真实OTDR/光功率测试结果时，只能生成“应执行测试”要求，不得输出“测试已通过”。"
        ),
    ]

    for package in full_packages:

        lines.extend(
            [
                "",
                "---",
                "",
                (
                    f"## {package['工作包编号']}｜"
                    f"{package['对象名称']}｜"
                    f"{package['施工环境']}"
                ),
                "",
                (
                    f"- **对象数量**："
                    f"{package['对象数量']}"
                ),
                (
                    "- **对象示例**："
                    + (
                        "、".join(
                            package[
                                "对象编码"
                            ][:10]
                        )
                        or "未提供"
                    )
                ),
                (
                    "- **需要人工确认**："
                    + (
                        "是"
                        if package.get(
                            "需要人工确认"
                        )
                        else "否"
                    )
                ),
            ]
        )

        reasons = package.get(
            "待确认原因"
        ) or []

        if reasons:
            lines.append(
                "- **待确认原因**："
                + "；".join(reasons)
            )

        # -----------------------------------------------------
        # 材料
        # -----------------------------------------------------
        lines.extend(
            [
                "",
                "### 所需材料",
            ]
        )

        materials = (
            package.get(
                "所需材料"
            )
            or []
        )

        if materials:

            for material in materials:

                code = material.get(
                    "物料编码",
                    ""
                )

                name = material.get(
                    "物料名称",
                    ""
                )

                qty = material.get(
                    "数量",
                    ""
                )

                unit = material.get(
                    "单位",
                    ""
                )

                confidence = material.get(
                    "置信状态",
                    ""
                )

                evidence_status = (
                    material.get(
                        "证据状态",
                        ""
                    )
                )

                lines.append(
                    f"- {name}"
                    f"（{code or '编码待确认'}，"
                    f"数量：{qty}{unit}，"
                    f"置信状态：{confidence or '未提供'}，"
                    f"证据状态：{evidence_status or '未提供'}）"
                )

        else:
            lines.append(
                "- 待确认"
            )

        # -----------------------------------------------------
        # 前置条件
        # -----------------------------------------------------
        lines.extend(
            [
                "",
                "### 前置条件",
            ]
        )

        for item in (
            package.get(
                "前置条件"
            )
            or []
        ):
            lines.append(
                f"- {item} "
                "`[internal_process]`"
            )

        # -----------------------------------------------------
        # 施工步骤
        # -----------------------------------------------------
        lines.extend(
            [
                "",
                "### 施工步骤",
            ]
        )

        steps = (
            package.get(
                "施工步骤"
            )
            or []
        )

        if steps:

            for step in steps:
                lines.append(
                    f"{step['step']}. "
                    f"**{step['action']}** — "
                    f"{step['detail']} "
                    "`[engineering_inference]`"
                )

        else:
            lines.append(
                "- 待人工确认"
            )

        # -----------------------------------------------------
        # 工艺
        # -----------------------------------------------------
        lines.extend(
            [
                "",
                "### 工艺要求",
            ]
        )

        for item in (
            package.get(
                "工艺要求"
            )
            or []
        ):
            lines.append(
                f"- {item} "
                "`[engineering_inference]`"
            )

        # -----------------------------------------------------
        # 安全
        # -----------------------------------------------------
        lines.extend(
            [
                "",
                "### 安全要求",
            ]
        )

        for item in (
            package.get(
                "安全要求"
            )
            or []
        ):
            lines.append(
                f"- {item} "
                "`[engineering_inference]`"
            )

        # -----------------------------------------------------
        # 测试与验收
        # -----------------------------------------------------
        lines.extend(
            [
                "",
                "### 测试与验收",
            ]
        )

        for item in (
            package.get(
                "测试要求"
            )
            or []
        ):
            lines.append(
                f"- {item} "
                "`[internal_process]`"
            )

        for item in (
            package.get(
                "验收标准"
            )
            or []
        ):
            lines.append(
                f"- {item} "
                "`[internal_process]`"
            )

        # -----------------------------------------------------
        # PCP官方证据
        # -----------------------------------------------------
        ref = (
            package.get(
                "规程引用"
            )
            or {}
        )

        lines.extend(
            [
                "",
                "### 规程证据",
                (
                    f"- 规程："
                    f"{ref.get('规程名称', '待确认')}"
                ),
                (
                    f"- 章节："
                    f"{ref.get('章节', '待确认')}"
                ),
                (
                    f"- 版本："
                    f"{ref.get('版本', '待确认')}"
                ),
                (
                    f"- 证据状态："
                    f"{ref.get('校验状态', '待确认')}"
                ),
                (
                    f"- 适用范围："
                    f"{ref.get('适用范围', '待确认')}"
                ),
            ]
        )

        verified = ref.get(
            "已验证参数"
        ) or {}

        if verified:

            lines.extend(
                [
                    "",
                    "#### 已验证PCP参数",
                ]
            )

            for param_name, param in (
                verified.items()
            ):

                lines.append(
                    f"- {param_name}："
                    f"Expected {param.get('expected', '')}，"
                    f"Maximum {param.get('maximum', '')}，"
                    f"来源 {param.get('source', '')} "
                    "`[official_extract]`"
                )

    normal_report = "\n".join(
        lines
    )

    # =========================================================
    # 20. 机器结果
    # =========================================================
    construction_result = {

        "status": status,

        "instruction_count": (
            instruction_count
        ),

        "work_package_count": (
            work_package_count
        ),

        "unknown_count": (
            unknown_count
        ),

        "environment_pending_count": (
            environment_pending_count
        ),

        "manual_package_count": (
            manual_package_count
        ),

        "work_packages": (
            full_packages
        ),

        "unknown_objects": (
            unknown_objects
        ),

        "pending_review_items": (
            pending_review_items
        ),

        "fiber_summary": {
            "fiber_status": (
                fiber_status
            ),
            "fiber_record_count": len(
                fiber_table
            ),
            "splice_record_count": len(
                splice_table
            ),
            "conflict_count": len(
                fiber_conflicts
            ),
        },

        "audit": {
            "aggregation_key": (
                "对象类型 + 明确施工环境"
            ),

            "raw_object_count": (
                instruction_count
            ),

            "compact_package_count": (
                work_package_count
            ),

            "unknown_object_count": (
                unknown_count
            ),

            "environment_pending_count": (
                environment_pending_count
            ),

            "manual_package_count": (
                manual_package_count
            ),

            "pcp_document_retrieved": (
                procedure_hit
            ),

            "pcp_version_verified": (
                version_verified
            ),

            "pcp_table5_retrieved": (
                table5_hit
            ),

            "pcp_optical_test_retrieved": (
                optical_test_hit
            ),

            "verified_attenuation_source": (
                "Operational Procedure "
                "PCP Installation / "
                "Table 5 / Page 43"
            ),

            "evidence_types": [
                "official_extract",
                "engineering_inference",
                "internal_process",
                "project_data",
                "pending_confirmation",
            ],

            "prohibited_claim": (
                "无真实测试数据时禁止输出"
                "“OTDR/光学测试已通过”"
            ),
        },
    }

    result_json = json.dumps(
        construction_result,
        ensure_ascii=False,
    )

    # =========================================================
    # 21. 返回 Dify
    # =========================================================
    return {

        # 条件分支继续使用
        "status": status,

        # PROD兼容
        "construction_status": (
            status
        ),

        "instruction_count": (
            instruction_count
        ),

        "work_package_count": (
            work_package_count
        ),

        "unknown_count": (
            unknown_count
        ),

        # 正常展示
        "normal_report": (
            normal_report
        ),

        "summary": (
            summary
        ),

        # 为兼容当前LLM异常分支：
        # 此字段现在不仅包含未知对象，
        # 还包含环境/BOM/Fiber/证据待确认原因。
        "unknown_objects_json": json.dumps(
            pending_review_items,
            ensure_ascii=False,
        ),

        # 对外机器接口
        "construction_result_json": (
            result_json
        ),

        # 过渡期旧名称
        "instructions_json": (
            result_json
        ),

        # Compact输出
        "work_packages": (
            compact_packages
        ),

        "environment_pending_count": (
            environment_pending_count
        ),

        "manual_package_count": (
            manual_package_count
        ),

        "pending_review_items_json": json.dumps(
            pending_review_items,
            ensure_ascii=False,
        ),
    }