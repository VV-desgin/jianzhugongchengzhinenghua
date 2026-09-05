import json


def default_engineering_data(project_id="", project_type=""):
    return {
        "project_id": project_id,
        "project_type": project_type,
        "objects": {
            "cable": [],
            "boite": [],
            "ptech": [],
            "site": [],
            "infrastructure": [],
        },
    }


def main(body: str = "", **kwargs) -> dict:
    try:
        data = json.loads(body) if isinstance(body, str) else body

        if not isinstance(data, dict):
            raise ValueError("接口返回的 JSON 顶层不是对象")

    except Exception as exc:
        engineering_data = default_engineering_data()
        review_state = "error"
        review_reason = "接口返回不是有效 JSON"
        review_error = str(exc)

        return {
            "api_success": False,

            "project_id": "",
            "project_name": "",
            "project_type": "",

            "layer_count": 0,
            "object_count": 0,

            "total_rules": 0,
            "passed_rules": 0,
            "warning_rules": 0,
            "failed_rules": 0,

            "issues_text": "",

            "error_message": f"接口返回不是有效 JSON：{exc}",

            "review_state": review_state,
            "review_reason": review_reason,
            "review_error": review_error,
            "engineering_data": engineering_data,

            "engineering_data_text": json.dumps(
                engineering_data,
                ensure_ascii=False,
            ),
        }

    # =========================================================
    # 1. 基础信息
    # =========================================================
    project_id = str(
        data.get("project_id") or ""
    )

    project_name = str(
        data.get("project_name") or ""
    )

    project_type = str(
        data.get("project_type") or ""
    )

    summary = (
        data.get("summary")
        if isinstance(data.get("summary"), dict)
        else {}
    )

    review = data.get("review") if isinstance(data.get("review"), dict) else None
    review_state = "executed"
    review_reason = ""
    review_error = ""
    if review is None:
        review_state = "missing"
        review_reason = "接口未返回 review 结构，不得视为零风险"
    elif review.get("status") in ("skipped", "not_run", "error"):
        review_state = str(review.get("status"))
        review_reason = str(review.get("reason") or "")
        review_error = str(review.get("error") or "")

    issues = ((review or {}).get("issues") if isinstance((review or {}).get("issues"), list) else [])

    # =========================================================
    # 2. Engineering Data
    # =========================================================
    engineering_data = data.get(
        "engineering_data"
    )

    if not isinstance(
        engineering_data,
        dict,
    ):
        engineering_data = default_engineering_data(
            project_id=project_id,
            project_type=project_type,
        )

    engineering_data.setdefault(
        "project_id",
        project_id,
    )

    engineering_data.setdefault(
        "project_type",
        project_type,
    )

    objects = engineering_data.get(
        "objects"
    )

    if not isinstance(objects, dict):
        objects = {}
        engineering_data["objects"] = objects

    for object_type in [
        "cable",
        "boite",
        "ptech",
        "site",
        "infrastructure",
    ]:
        if not isinstance(
            objects.get(object_type),
            list,
        ):
            objects[object_type] = []

    # =========================================================
    # 3. 审查问题摘要
    # =========================================================
    issue_lines = []

    for issue in issues[:10]:

        severity = str(
            issue.get("severity")
            or "warning"
        )

        issue_lines.append(
            "\n".join(
                [
                    f"规则编号：{issue.get('rule_id', '未提供')}",
                    f"问题对象：{issue.get('object_type', '未提供')}",
                    f"对象编号：{issue.get('object_id', '未提供')}",
                    f"严重等级：{severity}",
                    f"问题描述：{issue.get('message', '未提供')}",
                ]
            )
        )

    if issue_lines:
        issues_text = (
            "\n\n".join(issue_lines)
            + (
                f"\n\n> 当前共发现 {len(issues)} 项问题/警告，"
                "以上仅展示前10项，完整结果保留在结构化审查数据中。"
                if len(issues) > 10
                else ""
            )
        )
    elif review_state == "executed":
        issues_text = "未发现审查问题或警告。"
    else:
        issues_text = f"审查未执行/异常（{review_state}）：{review_reason} {review_error}".strip()

    # =========================================================
    # 4. 严重等级统计
    # =========================================================
    total_rules = int(
        review.get("total_rules", 0)
        or 0
    )

    passed_rules = int(
        review.get("passed_rules", 0)
        or 0
    )

    warning_rules = int(
        review.get("warning_rules", 0)
        or 0
    )

    failed_rules = int(
        review.get("failed_rules", 0)
        or 0
    )

    # =========================================================
    # 5. 返回
    # =========================================================
    return {
        "api_success": bool(
            data.get("success", False)
        ),

        "project_id": project_id,
        "project_name": project_name,
        "project_type": project_type,

        "layer_count": int(
            summary.get("layer_count", 0)
            or 0
        ),

        "object_count": int(
            summary.get("object_count", 0)
            or 0
        ),

        "total_rules": total_rules,
        "passed_rules": passed_rules,
        "warning_rules": warning_rules,
        "failed_rules": failed_rules,

        "issues_text": issues_text,

        "error_message": "；".join(
            str(x)
            for x in (
                data.get("errors")
                or []
            )
        ),

        "review_state": review_state,
        "review_reason": review_reason,
        "review_error": review_error,

        "engineering_data": engineering_data,

        "engineering_data_text": json.dumps(
            engineering_data,
            ensure_ascii=False,
        ),
    }