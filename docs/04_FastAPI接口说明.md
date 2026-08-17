# FastAPI 接口说明（正式版）

## 1. /health

`GET /health` → `200 {"status":"ok"}`（响应模型：HealthResponse）
已挂载 FastAPI response_model，/docs 自动生成契约

## 2. /agent/data-pipeline

`POST /agent/data-pipeline`（multipart/form-data）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| file | file | 是* | 工程压缩包/文件（zip/rar/7z/qgz/qgs/shp 等），与 file_url 二选一 |
| file_url | str | 否 | 远端文件 URL |
| excel_limit | int | 否 | Excel 行数上限，默认 0（不返回 excel_data），需要时传具体行数 |
| pdf_chars | int | 否 | PDF 字符上限，默认 3000，传 0 表示不返回 |
| include_tables | bool | 否 | 是否在响应中附带 bom/fiber 表清单（表单字段，非 query） |
| compact | bool | 否 | 精简响应（总控已发 compact=true）：excel_data/review_results 置空、engineering_data 不嵌 fiber_tables、保留 objects/fiber_assignments/business_params |

### 输出 JSON 顶层字段

`request_id`（请求对账 ID）、`success`、`project_id`、`project_name`、`project_type`、`layers`、`summary`、`review`、`warnings`、`errors`、`status`、`file_info`、`review_results`、`serious_issues_detected`、`excel_data`、`pdf_text`、`engineering_data`，可选 `bom_tables`/`fiber_tables`、`review_scope`/`skipped_gis_rules`。
`review` 内含 `total_rules`/`passed_rules`/`failed_rules`/`warning_rules`/`issues`/`categories`；P0-01 起 `failed_rules` 只统计 severity 为 `error`/`fatal` 的未通过项，`warning_rules` 统计 severity=warning 的未通过项（仍保留在 `issues`，不阻断流程）。
响应模型：`DataPipelineResponse`（response_model 已挂载，/docs 自动生成完整契约）

### engineering_data 字段

`{project_id, project_type, objects:{cable[], boite[], ptech[], site[], infrastructure[]}}`，对象字段覆盖 `code/longueur/capacite/type/nb_fibre_util/hauteur_appui`，None 值不输出，每项含唯一 `id`。
`engineering_data.fiber_assignments`（可选）：按已用芯数生成的预置占用（`[{cable_code, assigned:[{tube,fiber,core}]}]`），供 Dify 纤芯分配工具读取——新分配自动跳过已占芯，冲突可直接体现（2026-08-17 后端注入）。

### 审查问题统一字段（中文 ↔ JSON）

`review.issues[]` 全部问题统一按以下字段输出，缺失时填空串/0，结构固定：

| PO 统一字段 | JSON 字段 | 说明/示例 |
|---|---|---|
| 检查对象 | `object_type` | 如 `光缆 CDI-JAD-MAR-01-0001` |
| 问题位置/对象编号 | `object_id` | 后端 problem_location，如 `终点设备 PBO-JAD-MAR-0001`、`CODE` |
| 是否通过 | `passed` | `true`/`false` |
| 实际值 | `actual_value` | 实际检测到的值 |
| 标准值 | `expected_value` | 合格标准/期望值 |
| 规则编号 | `rule_id` | 如 `R019`、`R-BOM-001` |
| 错误说明 | `message` | 问题描述（error_description） |
| 严重等级 | `severity` | `fatal`/`error`/`warning` |
| 关联工程对象 | `object_ref` | 对应 `engineering_data` 对象 id，可空 |
| 问题分类 | `problem_category` / `problem_category_label` | 官方五大类 key + 中文标签 |

### 异常码

| HTTP | code | 场景 |
|---|---|---|
| 400 | 文件缺失/无法解析 | 未传 file/file_url 或格式不可识别 |
| 404 | 项目不存在/表格文件未找到 | project_id 无效或表文件已过期（TTL 2 小时） |
| 502 | LLM 未配置 | /agent/orchestrate 未设置 LLM_API_URL/KEY/MODEL |
| 500 | 内部错误 | 未捕获异常（响应为结构化 {success:false, error}，无 Traceback） |

### 已知限制

1. 无鉴权（生产需加 HTTPS+Token+限流）；2. Python 3.14 仅 SHP（fiona 跳过，pyshp 回退），GPKG/GeoJSON 需 3.10~3.13；3. RAR 解压 Linux 依赖系统 unrar 或联网自动下载；4. 项目临时文件 TTL 2 小时；5. /agent/orchestrate 需 LLM 配置；6. 交付包不含 wheels/（首次安装需联网）。
