# 通信设计审查 Agent — API 接口说明（V0.3）

## 一、安装与启动

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python api.py
```

支持纯 Excel 工程包（含官方图层 Sheet 的 xlsx/xls，非空间审查）。
支持 Python 3.10 ~ 3.14（3.14 自动使用 pyshp 读取 SHP）。启动后监听 `http://0.0.0.0:8000`。 Linux 环境使用 python3 api.py 启动；RAR 解压优先使用系统 unrar，未安装且联网时自动下载 RARLAB 官方 unrar 到 bin/。

## 二、接口列表

### 基础

#### GET /health

```json
{"status": "ok"}
```

### 工程管理

#### POST /project/load — 上传压缩包（zip/rar）

```json
{"success": true, "data": {"project_id": "abc12345"}}
```

#### GET /project/{id}/layers — 图层列表

```json
{"success": true, "data": [{"layer_name": "IMB", "name": "IMB", "source_layer_name": "IMB", "exists": true, "geometry_type": "Point", "fields": [["CODE", "str"]], "feature_count": 51}]}
```

说明：`name` 为标准名、`source_layer_name` 为原始名；空图层保留（exists=true, feature_count=0）；`exists=false` 表示图层不存在或配套文件不完整。

#### GET /project/{id}/device/{code}?crs=EPSG:4490 — 查询设备（支持 crs 参数坐标转换，默认原始坐标系）

返回设备所在图层、属性与坐标。

#### GET /project/{id}/trace/{code} — 光缆追踪

返回与该设备关联的光缆起止关系。

### 规则审查

#### GET /project/{id}/rules — 列出可用规则

#### POST /project/{id}/rules/run — 执行指定规则

请求体：`{"rule_ids": ["R001", ...]}` 或 `{"all": true}`。

#### POST /project/{id}/rules/run-all-and-cache — 全量审查并缓存

#### GET /project/{id}/export — 导出缓存结果（需先调用上面接口）

### 查询

- `GET /project/{id}/cable/{code}/length` — 光缆长度
- `GET /project/{id}/stats/devices` — 设备统计（仅 point 图层）
- `GET /project/{id}/excel?filename=xxx` — Excel 数据
- `GET /project/{id}/pdf?filename=xxx` — PDF 文本
- `GET /project/{id}/engineering-data` — 统一工程对象数据
- `GET /project/{id}/bom-tables` — BOM 物料表清单（Excel，含前 50 行样例）
- `GET /project/{id}/fiber-tables` — 纤芯数据清单（SRO-TOPO 纤芯表 + BOX/CABLE/SRO GPKG 矢量层）
- `GET /project/{id}/table-data?file=xxx&sheet=yyy&limit=100&filter=关键词&page=1&page_size=100` — 读取指定表格/层的数据（首行为表头；支持筛选与分页，返回 total/page/page_size）；流式单遍扫描（超大表内存安全），结果按参数缓存
- `POST /agent/inspect-file` — 单文件识别（Excel/PDF/CSV/SHP/DBF/压缩包），返回分类与解析建议，不建项目
- `GET /project/{id}/rule-library` — 解析官方规则库
- `GET /project/{id}/gis-check?tolerance=0.5` — GIS 空间检查（R-GIS-001~006：范围重叠/包含/自环/端点重合，端点容差默认 0.5 米）
- `GET /project/{id}/safety-check` — 安全距离检查（R-SAFE-001~009：离地高度 4.5m/7m、电力线交越垂直净距 2/4/3/5m、管线平行/交叉净距；二维数据无 Z 时跳过并返回说明）
- `GET /project/{id}/procedure-kb?keyword=xxx` — 施工规程知识库检索（施工对象/工序/步骤/材料/工艺/测试/安全/验收/常见错误/来源）
- `GET /project/{id}/relations?include_distances=true` — 上下游关系建模：CABLE.ORIGINE/EXTREMITE → 设备对象、BOITE/SITE 引用字段、端点距离统计（单位米）（校验规则 + 图层字段说明 + 可执行条件），返回 {project_id, project_type, objects} ，objects 包含 cable/boite/ptech（字段覆盖 code/longueur/capacite/type/nb_fibre_util/hauteur_appui），供 BOM / 纤芯分配工作流使用

### Agent 接口（支持文件上传或 file_url）

#### POST /agent/data-pipeline — 纯数据流水线（Dify 主接口）

上传工程包后返回固定结构 JSON：`success`、`project_id`、`project_name`、`project_type`、`layers`、`summary`、`review`、`warnings`、`errors`、`status`，可选参数 `include_tables=true` 时额外返回 `bom_tables`/`fiber_tables`（BOM 表与纤芯表清单，含前 50 行）；并保留 `file_info`、`review_results`、`serious_issues_detected`、`excel_data`、`pdf_text` 旧字段；新增 `engineering_data`（{project_id, project_type, objects} ，objects 包含 cable/boite/ptech）统一工程对象输出。

- `success=true` 表示流水线执行成功，不代表工程无问题。
- `review.issues[]` 每项固定包含 `rule_id`、`object_type`、`object_id`、`field`、`severity`、`message`、`source`。
- `review.issues[]` 每项包含 `rule_id`、`object_type`、`object_id`、`object_ref`（可关联 `engineering_data.id`）、`passed`、`actual_value`、`expected_value`、`field`、`severity`、`message`、`source`、`problem_category`（官方五大类 key）、`problem_category_label`（中文标签）。
- `review.categories`：按官方五大问题分类（数据完整性/空间与安全/资源/逻辑一致性/工程合理性）汇总告警数。
- R021 必填字段检查不作用于 CSV 参考表（l_/Type 前缀）；R016 空图层检查仅针对官方 8 个标准图层。
- 异常时返回结构化 `errors`，不输出 Traceback。

```bash
curl -X POST http://127.0.0.1:8000/agent/data-pipeline -F "file=@场勘设计图.zip"
```

#### POST /agent/orchestrate — 总控编排（含 LLM 报告）

需要环境变量 `LLM_API_URL`、`LLM_API_KEY`、`LLM_MODEL`；未配置时返回 502 `LLM 未配置`，不影响 data-pipeline 与 health。

#### POST /agent/full-pipeline — 全流程（含 LLM，阻断时返回结构化状态）

#### POST /agent/auto-review — 自动识别文件类型并审查（不生成 LLM 报告）

## 三、接口选择速查

| 场景 | 推荐接口 |
|------|----------|
| Dify 主链路 / 数据消费 | `/agent/data-pipeline` |
| 健康检查 | `/health` |
| 需要 LLM 综合报告 | `/agent/orchestrate`（需配置 LLM） |
| 上传后逐步查询 | `/project/load` + `/project/{id}/...` |

## 四、常见问题

1. **Python 3.14 安装提示 `Ignoring fiona`**：预期行为，pyshp 会自动安装并回退读取 SHP。
2. **RAR 无法解压**：确认包内 `bin/UnRAR.exe` 存在。
3. **端口 8000 被占用**：先关闭旧服务进程再启动。
4. **orchestrate 返回 502**：LLM 未配置，设置环境变量即可。
