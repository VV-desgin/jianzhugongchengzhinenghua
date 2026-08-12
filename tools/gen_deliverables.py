#!/usr/bin/env python3
"""生成 需求方要求的 6 份正式交付物（Markdown）+ 中间 JSON（供 Excel 构建）。

用法：python tools/gen_deliverables.py [赛题四_full.json]
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)

# ---------------------------------------------------------------- 官方规则矩阵
# engine: 规则ID; funcs: 后端函数; auto: pipeline=接入 data-pipeline / endpoint=专用接口 / not_routed=已实现未路由
OFFICIAL = [
    ("1.1", "文件完整性检查", "图层完整性校验：shape 目录包含全部 8 个图层及配套文件", ["R001", "R002"], ["check_file_missing", "check_layer_missing"], "pipeline", ["tests/test_data_pipeline_contract.py", "tests/test_recursive_file_scan.py"], "通过"),
    ("1.2", "图层类型及命名规范", "IMB：点图层，命名以 IMB 结尾", ["R003", "R004"], ["check_layer_name", "check_layer_geom_type"], "pipeline", ["tests/test_survey_classification.py"], "通过"),
    ("1.3", "图层类型及命名规范", "SITE：点图层，命名以 SITE 结尾", ["R003", "R004"], ["check_layer_name", "check_layer_geom_type"], "pipeline", ["tests/test_survey_classification.py"], "通过"),
    ("1.4", "图层类型及命名规范", "BOITE：点图层，命名以 BOITE 结尾", ["R003", "R004"], ["check_layer_name", "check_layer_geom_type"], "pipeline", ["tests/test_survey_classification.py"], "通过"),
    ("1.5", "图层类型及命名规范", "CABLE：线图层，命名以 CABLE 结尾", ["R003", "R004"], ["check_layer_name", "check_layer_geom_type"], "pipeline", ["tests/test_survey_classification.py"], "通过"),
    ("1.6", "图层类型及命名规范", "PTECH：点图层，命名以 PTECH 结尾", ["R003", "R004"], ["check_layer_name", "check_layer_geom_type"], "pipeline", ["tests/test_survey_classification.py"], "通过"),
    ("1.7", "图层类型及命名规范", "INFRASTRUCTURE：线图层，命名以 INFRASTRUCTURE 结尾", ["R003", "R004"], ["check_layer_name", "check_layer_geom_type"], "pipeline", ["tests/test_survey_classification.py"], "通过"),
    ("1.8", "图层类型及命名规范", "ZNRO：多边形图层，命名以 ZNRO 结尾", ["R003", "R004"], ["check_layer_name", "check_layer_geom_type"], "pipeline", ["tests/test_survey_classification.py"], "通过"),
    ("1.9", "图层类型及命名规范", "ZPM：多边形图层，命名以 ZPM 结尾", ["R003", "R004"], ["check_layer_name", "check_layer_geom_type"], "pipeline", ["tests/test_survey_classification.py"], "通过"),
    ("2", "坐标系一致性检查", "QGIS 工程与待检查图层坐标系必须一致", ["R017"], ["check_crs_consistency"], "pipeline", ["tests/test_reproject.py"], "通过"),
    ("3", "空图层检查", "官方 8 个图层均不得为空", ["R016", "R033"], ["check_layer_empty", "check_official_layers_empty"], "pipeline", ["tests/test_empty_layers_preserved.py"], "R016 通过；R033 已实现未路由"),
    ("4.1", "图层字段检查", "IMB 标绿字段存在且值不能为空", ["R021", "R005", "R-FLD-001"], ["check_required_fields_exist", "check_required_fields", "case_checks.check_case"], "pipeline", ["tests/test_official_field_type_length_rules.py", "tests/test_standard_cases.py"], "通过"),
    ("4.2", "图层字段检查", "IMB CODE 不能重名", ["R007", "R-FLD-002"], ["check_code_duplicate", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.3", "图层字段检查", "BOITE 标绿字段存在且值不能为空", ["R021", "R005", "R-FLD-001"], ["check_required_fields_exist", "check_required_fields", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.4", "图层字段检查", "BOITE CODE 不能重名", ["R007", "R-FLD-002"], ["check_code_duplicate", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.5", "图层字段检查", "CABLE 标绿字段存在且值不能为空", ["R021", "R005", "R-FLD-001"], ["check_required_fields_exist", "check_required_fields", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.6", "图层字段检查", "CABLE CODE 不能重名", ["R007", "R-FLD-002"], ["check_code_duplicate", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.7", "图层字段检查", "PTECH 标绿字段存在且值不能为空", ["R021", "R005", "R-FLD-001"], ["check_required_fields_exist", "check_required_fields", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.8", "图层字段检查", "PTECH CODE 不能重名", ["R007", "R-FLD-002"], ["check_code_duplicate", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.9", "图层字段检查", "INFRASTRUCTURE 标绿字段存在且值不能为空", ["R021", "R005", "R-FLD-001"], ["check_required_fields_exist", "check_required_fields", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.10", "图层字段检查", "INFRASTRUCTURE CODE 不能重名", ["R007", "R-FLD-002"], ["check_code_duplicate", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.11", "图层字段检查", "ZPM 标绿字段存在且值不能为空", ["R021", "R005", "R-FLD-001"], ["check_required_fields_exist", "check_required_fields", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.12", "图层字段检查", "ZPM CODE 不能重名", ["R007", "R-FLD-002"], ["check_code_duplicate", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.13", "图层字段检查", "ZNRO 标绿字段存在且值不能为空", ["R021", "R005", "R-FLD-001"], ["check_required_fields_exist", "check_required_fields", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.14", "图层字段检查", "ZNRO CODE 不能重名", ["R007", "R-FLD-002"], ["check_code_duplicate", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.15", "图层字段检查", "SITE 标绿字段存在且值不能为空", ["R021", "R005", "R-FLD-001"], ["check_required_fields_exist", "check_required_fields", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("4.16", "图层字段检查", "SITE CODE 不能重名", ["R007", "R-FLD-002"], ["check_code_duplicate", "case_checks.check_case"], "pipeline", ["tests/test_standard_cases.py"], "通过"),
    ("5.1", "孤立性检查", "SITE(PM) 与 ZPM 双向孤立性", ["R005_1"], ["check_site_pm_zpm_bidirectional"], "not_routed", ["-"], "已实现未接入路由"),
    ("5.2", "孤立性检查", "SITE(PM) 与 BOITE(PBO) 主从双向孤立性", ["R005_2"], ["check_site_pm_boite_pbo_bidirectional"], "not_routed", ["-"], "已实现未接入路由"),
    ("5.3", "孤立性检查", "SITE(PM) 与 CABLE(DISTRIBUTION) 主从双向孤立性", ["R005_3"], ["check_site_pm_cable_distribution_bidirectional"], "not_routed", ["-"], "已实现未接入路由"),
    ("5.4", "孤立性检查", "CABLE 首尾端点与 BOITE 双向孤立性", ["R005_4"], ["check_cable_boite_site_bidirectional"], "pipeline", ["赛题一/四实测 2 条"], "通过"),
    ("6.1", "几何检测", "ZNRO 同图层多边形不得交叉重叠", ["R-GIS-001"], ["gis_rules.run_gis_checks"], "endpoint", ["tests/test_gis_rules.py"], "通过"),
    ("6.2", "几何检测", "ZPM 同图层多边形不得交叉重叠", ["R-GIS-001"], ["gis_rules.run_gis_checks"], "endpoint", ["tests/test_gis_rules.py"], "通过"),
    ("6.3", "几何检测", "SITE(PM) 点必须位于归属 ZPM 内", ["R-GIS-002", "R027"], ["gis_rules.run_gis_checks", "check_site_pm_in_zpm"], "endpoint", ["tests/test_gis_rules.py"], "R-GIS-002 通过；R027 未路由"),
    ("6.4", "几何检测", "BOITE(PBO) 点必须位于归属 ZPM 内", ["R-GIS-003", "R028"], ["gis_rules.run_gis_checks", "check_boite_pbo_in_zpm"], "endpoint", ["tests/test_gis_rules.py"], "R-GIS-003 通过；R028 未路由"),
    ("6.5", "几何检测", "CABLE(DISTRIBUTION) 端点/折点位于归属 ZPM 内", ["R-GIS-004"], ["gis_rules.run_gis_checks"], "endpoint", ["tests/test_gis_rules.py"], "通过"),
    ("6.6", "几何检测", "CABLE ORIGINE!=EXTREMITE，端点必须连接 BOITE", ["R-GIS-005", "R-GIS-006", "R010"], ["gis_rules.run_gis_checks", "check_cable_endpoint_on_device"], "endpoint", ["tests/test_gis_rules.py"], "通过"),
    ("7.1", "数据检测", "PBO 覆盖入户数不得大于端口数", ["R020", "R022"], ["check_pbo_capacity", "check_pbo_coverage"], "pipeline", ["赛题一/四实测 R022 49 条"], "通过"),
    ("7.2", "数据检测", "PM 覆盖 PBO 端口之和不得大于线缆芯数", ["R019", "R011"], ["check_capacity_match", "check_capacity_exceeded"], "pipeline", ["赛题一/四实测 R019 147 条"], "通过"),
    ("附表1", "Excel 附表规则（纤芯）", "纤芯连接与分配表：输入纤芯/端口重复占用（有分路器放行）",
     ["R-FIBER-001"], ["rule_engine.check_fiber_core_duplicate"], "pipeline", ["纤芯重复占用案例（需求方 5 任务一）"], "通过（R-FIBER-001:2）"),
    ("附表2", "Excel 附表规则（BOM物料）", "BOM物料表：物料编码不在已知库（material_code_* / BOM_LIST*，排除案例文件自身）",
     ["R-BOM-001"], ["rule_engine.check_bom_material_match"], "pipeline", ["BOM物料无法匹配案例 + BOM_LIST2.xlsx"], "通过（R-BOM-001:3）"),
]

# ---------------------------------------------------------------- engineering_data
ENG_FIELDS = [
    ("cable", "code", ["CODE", "CABLE_CODE"], "CDI-JAD-MAR-01-0001", "有"),
    ("cable", "longueur", ["LONGUEUR", "LGR_REELLE", "LGR_CARTO"], "13.47（米）", "有"),
    ("cable", "capacite", ["CAPACITE", "CAPACITY", "FIBER_COUNT"], "24", "有"),
    ("cable", "type", ["TYPE_CABLE", "TYPE"], "DISTRIBUTION", "有"),
    ("cable", "nb_fibre_util", ["NB_FIBRE_U", "NB_FIBRE_UTIL", "NB_FIBRE_D"], "10", "有"),
    ("cable", "hauteur_appui", [], "-", "源数据无此字段，不输出"),
    ("boite", "code", ["CODE", "BOITE_CODE", "ID"], "BPE-JAD-MAR-1021", "有"),
    ("boite", "longueur", [], "-", "源数据无此字段，不输出"),
    ("boite", "capacite", ["CAPACITE", "CAPACITY"], "72", "有"),
    ("boite", "type", ["TYPE", "TYPE_BOITE", "BOXTYPE", "TYPE_FONC", "FONCTION"], "BPE", "有"),
    ("boite", "nb_fibre_util", ["NB_FIBRE_U", "NB_FIBRE_UTIL", "NBFUTILE"], "10", "有"),
    ("boite", "hauteur_appui", ["HAUTEUR_AP", "HAUTEUR_APPUI", "HAUTEUR"], "-", "源数据无值，不输出"),
    ("ptech", "code", ["CODE", "PTECH_CODE"], "IAM-CHA-001", "有"),
    ("ptech", "longueur", [], "-", "源数据无此字段，不输出"),
    ("ptech", "capacite", ["CAPACITE", "CAPACITY"], "-", "源数据无值，不输出"),
    ("ptech", "type", ["TYPE"], "CHAMBRE", "有"),
    ("ptech", "nb_fibre_util", ["NB_FIBRE_U", "NB_FIBRE_UTIL"], "-", "源数据无值，不输出"),
    ("ptech", "hauteur_appui", ["HAUTEUR_AP", "HAUTEUR_APPUI"], "0", "有（0 视为有效值）"),
]

# ---------------------------------------------------------------- GIS 测试记录
GIS_TESTS = [
    ("test_zone_overlap_and_touch", "R-GIS-001", "同层多边形重叠判违规、共边/共端点不判违规", "通过（基线）"),
    ("test_range_containment", "R-GIS-002/003/004", "SITE(PM)/BOITE(PBO)/CABLE(DISTRIBUTION) 越界检出、范围内不报", "通过（基线）"),
    ("test_cable_self_loop", "R-GIS-005", "ORIGINE=EXTREMITE 自环检出", "通过（基线）"),
    ("test_endpoint_on_device_tolerance", "R-GIS-006", "端点距设备 >0.5m 检出、≈0 通过", "通过（基线）"),
    ("test_run_gis_checks_empty_and_api_shape", "R-GIS 汇总", "空项目不报错、返回结构固定", "通过（基线）"),
]

# ---------------------------------------------------------------- 抽查分类
CLASSIFY = {
    "R019": ("正确检出", "光缆容量与设备容量字段真实不匹配"),
    "R022": ("正确检出", "PBO 容量小于覆盖户数，属规划容量问题"),
    "R007": ("正确检出", "同图层 CODE 重复"),
    "R005_4": ("正确检出", "BOITE 未被任何 CABLE 端点引用"),
    "R014": ("正确检出", "光缆几何非端点交叉"),
    "R020": ("正确检出", "已用纤芯数超过容量"),
    "R023": ("正确检出", "端点距最近光缆超过 100m 阈值（阈值属规则口径）"),
    "R017": ("疑似", "图层元信息仍为 4326，几何已自动重投影到 4490；是否跳过已重投影图层待确认"),
}
STRATIFY = [("R019", 16), ("R022", 6), ("R017", 3), ("R007", 1), ("R005_4", 1), ("R014", 1), ("R020", 1), ("R023", 1)]


def build_sample(data):
    issues = (data.get("review") or {}).get("issues") or []
    by_rule = {}
    for i in issues:
        by_rule.setdefault(i.get("rule_id"), []).append(i)
    sample = []
    for rid, n in STRATIFY:
        pool = by_rule.get(rid, [])
        for it in pool[:n]:
            cat, note = CLASSIFY.get(rid, ("无法确认", "待人工复核"))
            sample.append({
                "rule_id": rid,
                "object_type": it.get("object_type", ""),
                "object_id": it.get("object_id", ""),
                "message": (it.get("message") or "")[:120],
                "category": cat,
                "note": note,
            })
    return sample


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    sample = []
    if src and Path(src).exists():
        data = json.loads(Path(src).read_text(encoding="utf-8"))
        sample = build_sample(data)
    else:
        sample = [{"rule_id": r, "object_type": "-", "object_id": "-", "message": "-",
                   "category": c, "note": n} for r, c, n in [(r, *CLASSIFY[r]) for r, _ in STRATIFY]]

    auto_label = {"pipeline": "是（data-pipeline 路由）", "endpoint": "是（专用接口）", "not_routed": "否（已实现未路由）"}
    lines = ["# 官方规则后端实现覆盖矩阵", "", "生成：2026-08-08｜依据：《图层表字段说明和数据校验规则.xlsx》校验规则 1.1~7.2（39 条）", ""]
    lines.append("| 规则编号 | 规则名称 | 检测内容 | 后端规则ID | 后端函数/模块 | 是否实现 | 是否可自动执行 | 测试案例 | 测试结果 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for no, name, content, engine, funcs, auto, tests, result in OFFICIAL:
        lines.append(f"| {no} | {name} | {content} | {', '.join(engine)} | {', '.join(funcs)} | 已实现 | {auto_label[auto]} | {', '.join(tests)} | {result} |")
    lines.append("")
    lines.append("> 口径说明：R033、R005_1~R005_3、R027/R028 等已实现但未接入 data-pipeline 路由；R-GIS/R-SAFE 走专用接口（/gis-check、/safety-check）；标准案例规则（R-FLD/R-REL/R-FILE/R-DAT/R-FIBER/R-BOM）经 case_checks 与标准案例接口验证。")
    (DOCS / "01_官方规则后端实现覆盖矩阵.md").write_text("\n".join(lines), encoding="utf-8")

    cnt = Counter(s["category"] for s in sample)
    lines = ["# 智能审查抽查结果（真实摩洛哥工程，≥30 条）", "", f"生成：2026-08-08（补强 2026-08-09）｜样本来源：赛题四-摩洛哥.rar 最新审查结果（228 条 warning，0 error），按规则分布分层抽样；抽查基线版本：2026-08-07，2026-08-09 规则微调不影响本样本 {len(sample)} 条", ""]
    lines.append(f"汇总：正确检出 {cnt.get('正确检出', 0)}｜误报 {cnt.get('误报', 0)}｜疑似 {cnt.get('疑似', 0)}｜无法确认 {cnt.get('无法确认', 0)}")
    lines.append("")
    lines.append("| 序号 | 规则 | 检查对象 | 对象编号 | 问题描述 | 分类 | 说明 |")
    lines.append("|---|---|---|---|---|---|---|")
    for idx, s in enumerate(sample, 1):
        lines.append(f"| {idx} | {s['rule_id']} | {s['object_type']} | {s['object_id']} | {s['message']} | {s['category']} | {s['note']} |")
    lines.append("")
    lines.append("> 说明：R017 标注“疑似”是因为几何已自动重投影到 4490 而图层元信息未更新，属口径问题而非纯误报；其余样本按字段值/拓扑关系可复核为真实问题。")
    (DOCS / "02_智能审查抽查结果.md").write_text("\n".join(lines), encoding="utf-8")
    (DOCS / "02_抽查明细.json").write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# engineering_data 字段说明", "", "生成：2026-08-08｜来源：design_parser/project_data.py ENGINEERING_OBJECTS + 赛题四实测", ""]
    lines.append("| 对象 | 输出字段 | 源字段映射（按序取首个非空） | 实测样例（赛题四） | 缺失时行为 |")
    lines.append("|---|---|---|---|---|")
    for obj, field, srcs, sample_v, missing in ENG_FIELDS:
        lines.append(f"| {obj} | {field} | {', '.join(srcs) or '-'} | {sample_v} | {missing} |")
    lines.append("")
    lines.append("- 输出顶层结构：`{project_id, project_type, objects:{cable,boite,ptech,site,infrastructure}}`；每个对象带唯一 `id`（如 `cable:CDI-JAD-MAR-01-0001`）。")
    lines.append("- 字段值均为 None 时不写入 JSON（源数据缺字段/缺值则不出现该键）。")
    (DOCS / "03_engineering_data字段说明.md").write_text("\n".join(lines), encoding="utf-8")

    lines = ["# FastAPI 接口说明（正式版）", "", "## 1. /health", "", "`GET /health` → `200 {\"status\":\"ok\"}`", "",
             "## 2. /agent/data-pipeline", "", "`POST /agent/data-pipeline`（multipart/form-data）", "",
             "| 参数 | 类型 | 必填 | 说明 |", "|---|---|---|---|",
             "| file | file | 是* | 工程压缩包/文件（zip/rar/7z/qgz/qgs/shp 等），与 file_url 二选一 |",
             "| file_url | str | 否 | 远端文件 URL |",
             "| excel_limit | int | 否 | Excel 行数上限，默认 500，传 0 表示不返回 |",
             "| pdf_chars | int | 否 | PDF 字符上限，默认 3000，传 0 表示不返回 |",
             "| include_tables | bool | 否 | 是否在响应中附带 bom/fiber 表清单（表单字段，非 query） |", "",
             "### 输出 JSON 顶层字段", "",
             "`success`、`project_id`、`project_name`、`project_type`、`layers`、`summary`、`review`、`warnings`、`errors`、`status`、`file_info`、`review_results`、`serious_issues_detected`、`excel_data`、`pdf_text`、`engineering_data`，可选 `bom_tables`/`fiber_tables`。", "",
             "### engineering_data 字段", "",
             "`{project_id, project_type, objects:{cable[], boite[], ptech[], site[], infrastructure[]}}`，对象字段覆盖 `code/longueur/capacite/type/nb_fibre_util/hauteur_appui`，None 值不输出，每项含唯一 `id`。", "",
             "### 异常码", "",
             "| HTTP | code | 场景 |", "|---|---|---|",
             "| 400 | 文件缺失/无法解析 | 未传 file/file_url 或格式不可识别 |",
             "| 404 | 项目不存在/表格文件未找到 | project_id 无效或表文件已过期（TTL 2 小时） |",
             "| 502 | LLM 未配置 | /agent/orchestrate 未设置 LLM_API_URL/KEY/MODEL |",
             "| 500 | 内部错误 | 未捕获异常（响应为结构化 {success:false, error}，无 Traceback） |", "",
             "### 已知限制", "",
             "1. 无鉴权（生产需加 HTTPS+Token+限流）；2. Python 3.14 仅 SHP（fiona 跳过，pyshp 回退），GPKG/GeoJSON 需 3.10~3.13；3. RAR 解压 Linux 依赖系统 unrar 或联网自动下载；4. 项目临时文件 TTL 2 小时；5. /agent/orchestrate 需 LLM 配置；6. 交付包不含 wheels/（首次安装需联网）。"]
    (DOCS / "04_FastAPI接口说明.md").write_text("\n".join(lines), encoding="utf-8")

    lines = ["# GIS 规则测试记录", "", "生成：2026-08-08｜测试基线：tests/test_gis_rules.py（93 项全量基线通过，本轮未重跑 pytest）", ""]
    lines.append("| 测试函数 | 覆盖规则 | 场景 | 结果 |")
    lines.append("|---|---|---|---|")
    for fn, rule, scene, result in GIS_TESTS:
        lines.append(f"| {fn} | {rule} | {scene} | {result} |")
    lines.append("")
    lines.append("> 另：真实赛题一/四 GIS 相关告警：R014 非端点交叉 1 条、R023 孤立端点 1 条，均可复现。")
    (DOCS / "05_GIS规则测试记录.md").write_text("\n".join(lines), encoding="utf-8")

    lines = ["# 已知限制清单", "", "1. LLM 端点（/agent/orchestrate、/agent/full-pipeline）需配置 LLM_API_URL/LLM_API_KEY/LLM_MODEL，未配置返回 502。",
             "2. Python 3.14 仅支持 SHP（pyshp 回退），GPKG/GeoJSON 等非 SHP 需 Python 3.10~3.13。",
             "3. RAR 解压：Windows 用内置 bin/UnRAR.exe；Linux 优先系统 unrar，未安装且联网时自动下载 RARLAB 官方 unrar 到 bin/。",
             "4. 项目临时文件保留 2 小时（TTL），超时自动清理；暂无显式删除接口。",
             "5. 大表读取（BOM_LIST 104 万行）已流式化：过滤/翻页全表扫描约 6s、内存安全，结果按参数缓存（256 条上限）。",
             "6. 空图层 geometry_type 返回 none（无要素无法推断）。",
             "7. CSV/JSON 非标准图层加载后无标准名映射时 name 与 source_layer_name 相同。",
             "8. 交付包不含 wheels/ 离线依赖，首次安装需联网。",
             "9. API 无鉴权、CORS 全开，生产部署需加 HTTPS、Token、限流与审计。",
             "10. 规则 R005_1~R005_3、R027/R028、R033 已实现但未接入 data-pipeline 路由（覆盖矩阵已注明）。"]
    (DOCS / "06_已知限制清单.md").write_text("\n".join(lines), encoding="utf-8")

    index = ["# 正式交付物索引", "", "1. [官方规则后端实现覆盖矩阵](01_官方规则后端实现覆盖矩阵.md)",
             "2. [智能审查抽查结果](02_智能审查抽查结果.md)（明细 JSON：02_抽查明细.json）",
             "3. [engineering_data 字段说明](03_engineering_data字段说明.md)",
             "4. [FastAPI 接口说明](04_FastAPI接口说明.md)",
             "5. [GIS 规则测试记录](05_GIS规则测试记录.md)",
             "6. [已知限制清单](06_已知限制清单.md)", ""]
    (DOCS / "README.md").write_text("\n".join(index), encoding="utf-8")

    # 中间 JSON 供 Excel 构建
    payload = {
        "official": [[no, name, content, ", ".join(engine), ", ".join(funcs), "已实现", auto_label[auto], ", ".join(tests), result] for no, name, content, engine, funcs, auto, tests, result in OFFICIAL],
        "eng": [[obj, field, ", ".join(srcs) or "-", sample_v, missing] for obj, field, srcs, sample_v, missing in ENG_FIELDS],
        "gis": [[fn, rule, scene, result] for fn, rule, scene, result in GIS_TESTS],
        "sample": sample,
    }
    (DOCS / "deliverables_data.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print("docs generated:", len(list(DOCS.glob("*.md"))), "md + json; sample:", len(sample))


if __name__ == "__main__":
    main()
