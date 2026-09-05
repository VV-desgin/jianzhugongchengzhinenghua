import json


def main(
    engineering_data: str = "",
    bom_result: str = "",
    fiber_result: str = "",
) -> dict:

    def parse(value, default):
        if value is None or value == "":
            return default

        if isinstance(value, (dict, list)):
            return value

        try:
            result = json.loads(value)

            if isinstance(result, str):
                try:
                    return json.loads(result)
                except Exception:
                    return result

            return result

        except Exception:
            return default

    # =========================================================
    # 1. 解析工程数据
    # =========================================================
    eng = parse(
        engineering_data,
        {},
    )

    if (
        isinstance(eng, dict)
        and "engineering_data" in eng
        and "objects" not in eng
    ):
        eng = parse(
            eng.get("engineering_data"),
            {},
        )

    if not isinstance(eng, dict):
        eng = {}

    objects = (
        eng.get("objects")
        or {}
    )

    boites = (
        objects.get("boite")
        or []
    )

    cables = (
        objects.get("cable")
        or []
    )

    # =========================================================
    # 2. 对象类型
    # =========================================================
    object_types = set()

    for item in boites:

        if not isinstance(item, dict):
            continue

        raw_type = str(
            item.get("type")
            or ""
        ).upper()

        if "BPE" in raw_type:
            object_types.add("BPE")
            object_types.add("FDT")

        elif "PBO" in raw_type:
            object_types.add("PBO")
            object_types.add("FAT")

    if cables:
        object_types.add("CABLE")
        object_types.add(
            "Fiber Optic Cable"
        )

    # =========================================================
    # 3. 明确施工环境
    # =========================================================
    environments = set()

    all_objects = []

    all_objects.extend(
        item
        for item in boites
        if isinstance(item, dict)
    )

    all_objects.extend(
        item
        for item in cables
        if isinstance(item, dict)
    )

    for item in all_objects:

        mode = str(
            item.get("mode_pose")
            or item.get("installation_mode")
            or item.get("pose_mode")
            or item.get("mode")
            or ""
        ).strip().upper()

        if mode in (
            "AERIEN",
            "AÉRIEN",
            "POLE",
            "AERIAL",
            "OVERHEAD",
        ):
            environments.add("Aerial")
            environments.add(
                "Pole Mounted"
            )

        elif mode in (
            "CHAMBRE",
            "SOUTERRAIN",
            "UNDERGROUND",
            "MANHOLE",
        ):
            environments.add(
                "Underground"
            )
            environments.add(
                "Manhole"
            )

        elif mode in (
            "CONDUIT",
            "DUCT",
            "FOURREAU",
            "PIPE",
        ):
            environments.add("Duct")
            environments.add(
                "Conduit"
            )

        elif mode in (
            "INTERIEUR",
            "INTÉRIEUR",
            "INDOOR",
        ):
            environments.add("Indoor")

        elif mode in (
            "FACADE",
            "FAÇADE",
            "WALL",
        ):
            environments.add("Facade")

    # =========================================================
    # 4. BOM专业词
    # =========================================================
    bom_data = parse(
        bom_result,
        {},
    )

    bom_items = []

    if isinstance(
        bom_data,
        list,
    ):
        bom_items = bom_data

    elif isinstance(
        bom_data,
        dict,
    ):
        bom_items = (
            bom_data.get("bom_items")
            or bom_data.get(
                "standard_bom_table"
            )
            or bom_data.get("items")
            or []
        )

    material_terms = set()

    for item in bom_items:

        if not isinstance(item, dict):
            continue

        name = str(
            item.get("物料名称")
            or item.get(
                "material_name"
            )
            or ""
        )

        upper_name = name.upper()

        for keyword in (
            "FDT",
            "FAT",
            "SPLICING",
            "光纤熔接",
            "光缆",
            "ADSS",
            "LABEL",
            "标签",
        ):
            if (
                keyword.upper()
                in upper_name
            ):
                material_terms.add(
                    keyword
                )

    # =========================================================
    # 5. Fiber专业词
    # =========================================================
    fiber_data = parse(
        fiber_result,
        {},
    )

    fiber_terms = set()

    if isinstance(
        fiber_data,
        dict,
    ):

        if (
            fiber_data.get(
                "splice_table"
            )
            or fiber_data.get(
                "splices"
            )
        ):
            fiber_terms.update(
                [
                    "Fiber-Fiber splice",
                    "Optical Splicing",
                ]
            )

        if (
            fiber_data.get(
                "fiber_table"
            )
            or fiber_data.get(
                "fiber_assignments"
            )
        ):
            fiber_terms.add(
                "Fiber Allocation"
            )

    # =========================================================
    # 6. 可选测试检索提示
    # =========================================================
    retrieval_hint = str(
        eng.get(
            "_retrieval_hint"
        )
        or ""
    ).strip()

    # =========================================================
    # 7. 构造规程检索词
    # =========================================================
    query_parts = [
        "Operational Procedure PCP Installation",
        "PCP Installation",
        "Optical Testing",
        "On-field Testing",
        "Testing Evaluation",
        "Troubleshooting",
        "Table 5",
        "Fiber-Fiber splice",
        "Fiber-SC/APC connector splice",
    ]

    query_parts.extend(
        sorted(object_types)
    )

    query_parts.extend(
        sorted(environments)
    )

    query_parts.extend(
        sorted(material_terms)
    )

    query_parts.extend(
        sorted(fiber_terms)
    )

    if retrieval_hint:
        query_parts.append(
            retrieval_hint
        )

    # 去重并保持顺序
    final_parts = []
    seen = set()

    for item in query_parts:

        text = str(
            item or ""
        ).strip()

        if not text:
            continue

        key = text.lower()

        if key in seen:
            continue

        seen.add(key)
        final_parts.append(text)

    retrieval_query = "\n".join(
        final_parts
    )

    return {
        "retrieval_query":
            retrieval_query
    }