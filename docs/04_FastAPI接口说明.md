# FastAPI 接口说明（正式版）

## 1. /health

`GET /health` → `200 {"status":"ok"}`

## 2. /agent/data-pipeline

`POST /agent/data-pipeline`（multipart/form-data）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| file | file | 是* | 工程压缩包/文件（zip/rar/7z/qgz/qgs/shp 等），与 file_url 二选一 |
| file_url | str | 否 | 远端文件 URL |
| excel_limit | int | 否 | Excel 行数上限，默认 500，传 0 表示不返回 |
| pdf_chars | int | 否 | PDF 字符上限，默认 3000，传 0 表示不返回 |
| include_tables | bool | 否 | 是否在响应中附带 bom/fiber 表清单（表单字段，非 query） |

### 输出 JSON 顶层字段

`success`、`project_id`、`project_name`、`project_type`、`layers`、`summary`、`review`、`warnings`、`errors`、`status`、`file_info`、`review_results`、`serious_issues_detected`、`excel_data`、`pdf_text`、`engineering_data`，可选 `bom_tables`/`fiber_tables`。review.issues 每条含 rule_id/object_type/object_id/object_ref/passed/actual_value/expected_value/field/severity/message/source/problem_category/problem_category_label。

### engineering_data 字段

`{project_id, project_type, objects:{cable[], boite[], ptech[], site[], infrastructure[]}}`，对象字段覆盖 `code/longueur/capacite/type/nb_fibre_util/hauteur_appui`，None 值不输出，每项含唯一 `id`。

### 异常码

| HTTP | code | 场景 |
|---|---|---|
| 400 | 文件缺失/无法解析 | 未传 file/file_url 或格式不可识别 |
| 404 | 项目不存在/表格文件未找到 | project_id 无效或表文件已过期（TTL 2 小时） |
| 502 | LLM 未配置 | /agent/orchestrate 未设置 LLM_API_URL/KEY/MODEL |
| 500 | 内部错误 | 未捕获异常（响应为结构化 {success:false, error}，无 Traceback） |

### 已知限制

1. 无鉴权（生产需加 HTTPS+Token+限流）；2. Python 3.14 仅 SHP（fiona 跳过，pyshp 回退），GPKG/GeoJSON 需 3.10~3.13；3. RAR 解压 Linux 依赖系统 unrar 或联网自动下载；4. 项目临时文件 TTL 2 小时；5. /agent/orchestrate 需 LLM 配置；6. 交付包不含 wheels/（首次安装需联网）。