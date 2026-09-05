import json


def main(construction_result_json: str = "") -> dict:
    """解析施工工具结果：输出浅层 work_packages（防 Dify depth limit），完整结果保留为 JSON 字符串。"""
    try:
        data = json.loads(construction_result_json or "{}")
        raw = data.get("work_packages") or []
    except Exception as e:
        return {
            "construction_work_packages": [],
            "construction_result": {"parse_error": str(e)},
            "construction_parse_success": False,
            "construction_parse_error": str(e),
        }

    shallow = []
    for wp in raw:
        if not isinstance(wp, dict):
            continue
        shallow.append({
            "工作包编号": str(wp.get("工作包编号") or ""),
            "对象类型": str(wp.get("对象类型") or ""),
            "对象名称": str(wp.get("对象名称") or ""),
            "施工环境": str(wp.get("施工环境") or ""),
            "对象数量": int(wp.get("对象数量") or 0),
            "对象编码示例": [
                str(x) for x in (wp.get("对象编码") or wp.get("对象编码示例") or [])[:10]
            ],
            "物料种类数": int(wp.get("物料种类数") or len(wp.get("所需材料") or [])),
            "规程状态": str(
                (wp.get("规程引用") or {}).get("校验状态")
                or (wp.get("规程引用") or {}).get("retrieval_status")
                or wp.get("规程状态")
                or "待确认"
            ),
            "需要人工确认": bool(wp.get("需要人工确认") or wp.get("需要人工确认") is True),
            "待确认原因": [str(x) for x in (wp.get("待确认原因") or [])][:20],
        })

    return {
        "construction_work_packages": shallow,
        "construction_result": {
            "shallow_count": len(shallow),
            "full_json": construction_result_json,
        },
        "construction_parse_success": True,
        "construction_parse_error": "",
    }
