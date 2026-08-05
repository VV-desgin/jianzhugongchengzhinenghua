# design_parser V0.3 — Dify 接入前交付说明

## 〇、V0.3 版本说明

- 本版本在 V0.2 稳定化基础上完成：
  ① 补齐统一 engineering_data 输出（objects.cable/boite/ptech，字段覆盖 code/longueur/capacite/type/nb_fibre_util/hauteur_appui，新增 GET /project/{id}/engineering-data，/agent/data-pipeline 同步返回）；
  ② 纤芯表真实表头自动识别（摘要带 headers，兼容 SRO TOPO 多级合并表头）；
  ③ R-FIBER-001 兼容真实 SRO TOPO（ODF 输入端口 / Entrée 输入纤芯查重）；
  ④ CABLE_AMONT 长度口径方案 1 定稿（前缀 + 端口不计入，编号主体最长 17 ≤ 20，真实数据 0 误报）。
- V0.2 交付包保留（design_parser_v0.2_delivery.zip），本包为 V0.3（design_parser_v0.3_delivery.zip）。

## 一、本轮修改文件清单

| 文件 | 修复点 | 关键变更 |
|------|--------|----------|
| `requirements.txt` | 修复点1 | 核心依赖全部固定版本；fiona 限定 Python 3.10~3.13，新增 pyshp 纯 Python 回退（3.14+ 可用） |
| `api.py` | 修复点2/3/6/7 | 文件分类优先级、SHP 大小写匹配、data-pipeline 输出契约、LLM 环境变量、解析进度日志 |
| `design_parser/package.py` | 修复点3 | 嵌套压缩包递归解压、统一日志输出（loguru） |
| `design_parser/project_data.py` | 修复点4/5 | 空图层保留、统一图层命名映射、fiona/pyshp 双后端 |
| `design_parser/layer_reader.py` | 修复点1/4 | fiona 缺失时回退 pyshp，缺依赖时给出修复指引 |
| `setup.py` | 修复点1 | `python_requires=">=3.10,<3.15"` |
| `tests/` | 四 | 0.2 要求 7 项测试 + 4 项 pyshp 回退测试（共 11 项） |
| `DELIVERY_README.md` | 五 | 精简安装/启动/测试/验收说明 |
| `design_parser/bom_fiber_reader.py` | 纤芯解析 | 自动识别真实表头行（兼容 SRO TOPO 多级合并表头），摘要输出 headers |
| `design_parser/case_checks.py` | 纤芯审查 | R-FIBER-001 兼容真实 SRO TOPO（ODF 输入端口、Entrée 输入纤芯重复检查） |
| `design_parser/rule_engine.py` | 纤芯审查 | 纤芯页签筛选增加 SRO/BPE/PBO 设备页 |
| `design_parser/mappings/length_rules.json` | 字段长度 | CABLE_AMONT 方案1（前缀+端口不计入，编号主体最长 17 ≤ 20，真实数据 0 误报） |
| `tests/` | 回归 | 新增 4 项纤芯/表头测试，全量 pytest 93 passed |
| `API_SAMPLES.md` | 文档 | bom/fiber 示例同步为最新返回结构（sheets 含 headers/rows） |

## 二、关键变更说明

### 修复点1：补全并固定运行依赖
- 核心依赖全部固定版本：fiona、shapely、pyproj、pandas、openpyxl、dbfread、xlrd、fastapi、uvicorn、python-multipart、pydantic、httpx、rarfile、py7zr、pdfplumber、pyyaml、pytest、loguru。
- **Python 3.10 ~ 3.13**：fiona（首选矢量后端）+ pyshp 同时安装。
- **Python 3.14+**：fiona 无预编译 wheel，pip 自动跳过并安装 pyshp，代码自动回退读取 SHP。安装时看到 `Ignoring fiona ...` 是预期行为，不是错误。
- 安装方式统一为 `pip install -r requirements.txt`，不再依赖任何自动安装脚本。

### 修复点2：工程文件分类优先级
- `_guess_file_category()` 四级判定：文件名/路径关键词 → 工程目录和业务特征 → QGIS 工程文件存在性 → unknown + warning。
- 文件名含"场勘"/"SURVEY"/"FIELD"时优先识别为 `survey_design`；不再仅因包内存在 .qgs/.qgz 就判定为完整设计图。

### 修复点3：嵌套目录扫描与文件完整性检查
- 对解压后的外层根目录执行递归扫描（`Path.rglob`），不只检查被选中的内部 QGIS 目录。
- SHP 配套文件按基础文件名匹配并统一大小写，IMB.shp/IMB.dbf 等不会误报缺失。
- 缺失项返回结构化对象（layer_name、relative_path、missing_extensions、rule_id）。

### 修复点4：空图层必须进入接口结果
- `get_layer_info()` 保留空图层：`exists=true, feature_count=0` 表示图层存在但为空，与"图层不存在"（exists=false）明确区分。

### 修复点5：统一图层命名和映射
- 返回统一标准名 `name`，原始名保留在 `source_layer_name`；INFRA → INFRASTRUCTURE 等别名统一，无法映射时返回 warning，不静默猜测。

### 修复点6：固定 /agent/data-pipeline 输出契约
- 固定字段：success、project_id、project_name、project_type、layers、summary、review、warnings、errors（并保留旧字段兼容）。
- `success=true` 仅表示流水线执行成功，不代表工程无问题；`review.issues` 每项固定包含 rule_id、object_type、object_id、field、severity、message、source。
- 异常时返回结构化 errors，不输出未捕获 Traceback。
- 新增 `engineering_data`：统一工程对象输出（{project_id, project_type, objects}，objects 包含 cable/boite/ptech/site/infrastructure，每项含唯一 id，字段覆盖 code/longueur/capacite/type/nb_fibre_util/hauteur_appui），供 BOM / 纤芯分配工作流使用；新增 `GET /project/{id}/engineering-data` 接口。
- 新增 `POST /agent/inspect-file` 单文件识别；`/table-data` 支持 filter/page/page_size；错误响应统一为 {success:false, data:null, error:{code,message}}；`/device/{code}` 支持 crs 参数坐标转换；解析结果按文件+修改时间缓存。
- 新增 `API_SAMPLES.md`：10 个新接口的真实返回 JSON 样例（由赛题一/赛题四数据生成）。
- 新增 `design_parser/mappings/length_rules.json`：R032 字段长度检查可配置。CABLE_AMONT 采用方案1（已确认）：自动识别两段式前缀与末尾 -NNN（纤芯号/端口号）不计入，编号主体最长 17 位 ≤ 官方 20，两套赛题实测 0 误报；官方若改全串口径，`enabled:false` 一键恢复。
- 新增 BOM/纤芯数据接口：`GET /project/{id}/bom-tables`、`GET /project/{id}/fiber-tables`、`GET /project/{id}/table-data`，支持解析 BOM_LIST/物料编码库/纤芯 TOPO 表格与 BOX/CABLE/SRO GPKG 层；`/agent/data-pipeline` 可传 `include_tables=true` 一并返回表格清单。
- 新增 Excel 规则解析器：`GET /project/{id}/rule-library` 解析官方《图层表字段说明和数据校验规则.xlsx》，输出校验规则、字段说明与可执行条件（含字段类型/长度，共约 400 条）。
- 新增上下游关系建模：`GET /project/{id}/relations` 返回 CABLE 端点→设备对象边、未解析引用、BOITE/SITE 引用字段、端点距离统计（单位米）。
- 新增 GIS 空间审查：`GET /project/{id}/gis-check`（R-GIS-001~006，端点容差 0.5m）。
- 新增规程知识库解析器：`GET /project/{id}/procedure-kb` 检索施工规程（施工对象/工序/步骤/材料/工艺/测试/安全/验收/常见错误/页码来源）。
- 新增安全距离审查：`GET /project/{id}/safety-check`（R-SAFE-001~009，阈值来自施工安全材料：离地高度 4.5/7m、电力线交越 2/4/3/5m、管线平行/交叉净距表）。

### 修复点7：LLM 接口边界
- LLM_API_URL/LLM_API_KEY/LLM_MODEL 从环境变量读取；缺少配置时 `/agent/orchestrate` 返回 502 "LLM 未配置"，不影响 `/agent/data-pipeline`、`/health` 和基础解析接口。

### 修复点8：纤芯表解析与审查增强
- 表头自动识别：`read_sheet_rows`/`workbook_summary` 自动定位真实表头行（兼容 SRO TOPO 前几行元信息 + 多级合并表头），摘要新增 `headers` 字段，下游无需再调接口猜列名。
- R-FIBER-001 兼容真实纤芯拓扑表：SRO 页按 SRO Port/ODF Code/ODF Port 检查输入端口重复，单箱页按 Entrée/N°/T/F 检查输入纤芯重复；规则引擎自动纳入 SRO/BPE/PBO 设备页签。
- 真实数据验证：赛题一 SRO TOPO 共 120 个设备页签被扫描，SRO 页 721 行 ODF 端口无重复，无漏扫、无误报。

### 解析进度日志（新增）
- 终端会打印完整解析链路：收到文件 → 解压完成 → 文件分类 → 图层清单（含要素数）→ 规则审查结果 → 流水线完成，便于确认读取过程。

## 三、环境要求与启动命令

### 环境要求
- Python **3.10 ~ 3.14**（推荐 3.12；3.14 自动使用 pyshp 回退）。
- 需要联网执行 pip 安装。

### 启动命令（全新虚拟环境）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python api.py
```

服务启动后监听 `http://0.0.0.0:8000`。

## 四、测试命令

```powershell
python -m pytest tests -q
```

预期结果：93 passed（含 10 个标准测试案例的自动化验证与纤芯表头/真实 TOPO 冲突检查用例）。

## 五、API 调用示例

### 健康检查

```powershell
curl.exe http://127.0.0.1:8000/health
```

### data-pipeline 接口

```bash
curl -X POST http://127.0.0.1:8000/agent/data-pipeline \
  -F "file=@场勘设计图.zip"
```

## 六、官方场勘包真实返回 JSON 样例

见同目录下 `场勘设计图_返回样例.json`。

关键指标：
- project_type: survey_design
- layer_count: 23，object_count: 244
- IMB: exists=true, feature_count=51
- SITE: exists=true, feature_count=1
- BOITE/CABLE/PTECH: exists=true, feature_count=0
- 连续运行 3 次，状态码与核心计数一致

## 七、已知限制和未解决问题

1. **LLM 端点未测试**：`/agent/orchestrate` 和 `/agent/full-pipeline` 需要配置环境变量 `LLM_API_URL`、`LLM_API_KEY`、`LLM_MODEL` 后才能使用。
2. **三个 ghost 文件**：`bom_fiber_parser.py`、`procedure_kb.py`、`rules_parser.py` 因文件系统损坏被排除在 setup.py 之外，不影响核心功能。
3. **空图层 geometry_type**：空图层的 geometry_type 返回 "none"，因为无要素可读取几何信息。
4. **CSV/JSON 图层**：非 QGS 定义的 CSV/JSON 表格数据也会加载到 layers 中，无标准图层名映射时 source_layer_name 与 name 相同。
5. **Python 3.14 格式限制**：3.14 上 SHP 走 pyshp 可正常读取；GPKG/GeoJSON 等非 SHP 格式暂不可读（官方验收包仅含 SHP，不受影响）。如需完整能力请使用 Python 3.12。
6. **RAR 解压**：依赖包内 `bin/UnRAR.exe`（RARLAB 官方控制台版 freeware），请勿删除。
7. **交付包为精简版**：不含 wheels/ 离线依赖目录，首次安装需联网；安装只需 `pip install -r requirements.txt`。

## 八、环境变量配置（可选）

如需启用 LLM 报告生成功能，设置以下环境变量：

```powershell
$env:LLM_API_URL = "https://api.siliconflow.cn/v1/chat/completions"
$env:LLM_API_KEY = "your-api-key-here"
$env:LLM_MODEL = "deepseek-ai/DeepSeek-V4-Flash"
```
