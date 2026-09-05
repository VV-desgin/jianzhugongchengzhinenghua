import json


def main(bom_result_json: str = "", api_success=None, api_error: str = "", api_status: str = "", **kwargs) -> dict:
    if api_success is False:
        return {
            "bom_success": False,
            "bom_error": str(api_error or "BOM API 失败"),
            "final_bom": [], "standard_bom_table": [], "need_confirm_list": [],
            "bom_count": 0, "confirm_count": 0,
        }
    try:
        # 兼容字符串 JSON
        if isinstance(bom_result_json, str):
            text = bom_result_json.strip()

            if not text:
                raise ValueError("BOM结果为空")

            data = json.loads(text)

        # 兼容偶尔直接传入 Object 的情况
        elif isinstance(bom_result_json, dict):
            data = bom_result_json

        else:
            raise ValueError(
                f"不支持的BOM结果类型: {type(bom_result_json).__name__}"
            )

        final_bom = data.get("final_bom") or []
        standard_bom_table = data.get("standard_bom_table") or []
        need_confirm_list = data.get("need_confirm_list") or []

        # 若没有 standard_bom_table，则使用 final_bom 兜底
        if not standard_bom_table and final_bom:
            standard_bom_table = final_bom

        if not standard_bom_table and not final_bom:
            raise ValueError("BOM结果为空：无任何物料行")
        bom_count = len(standard_bom_table)
        confirm_count = len(need_confirm_list)

        return {
            "bom_success": True,
            "bom_error": "",
            "final_bom": final_bom,
            "standard_bom_table": standard_bom_table,
            "need_confirm_list": need_confirm_list,
            "bom_count": bom_count,
            "confirm_count": confirm_count,
        }

    except Exception as e:
        return {
            "bom_success": False,
            "bom_error": str(e),
            "final_bom": [],
            "standard_bom_table": [],
            "need_confirm_list": [],
            "bom_count": 0,
            "confirm_count": 0,
        }