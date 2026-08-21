# 后续工作实施计划（2026-08-22）

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 subagent-driven-development（推荐）或 inline 逐任务执行；步骤用 `- [ ]` 复选框跟踪。

**Goal:** 在 9-15 提交前，把「官方口径催办、标准答案案例、后端规则收尾、评测材料、交付收尾」全部闭环，保持 64 条规则全自动执行、回归门全绿。

**Architecture:** 后端是确定性 FastAPI 规则层（64 条规则全路由），本轮不引入新架构，只做「决策门 → 小代码改动（TDD）→ 文档/数据任务 → 收尾」四段。每个代码任务独立可测、单独提交；所有提交先本地（分支 codex/business-params），推送须用户批准。

**Tech Stack:** Python 3.13（`D:\python\python.exe`）、FastAPI、pytest（当前 136 passed）、回归门 14 项（基线 287/57/230）、openpyxl、Git。

## Global Constraints

- 分支 `codex/business-params`；提交信息沿用 `feat:/fix:/docs:` 前缀；**不推送**（推送需用户批准）。
- 代码改动一律 TDD：先写失败测试，再实现，再全量验证。
- 每次改动必须过：`pytest tests/ -q`（≥136 passed）+ 回归门 14 项 ALL PASS；回归门跑真实大包需 `$env:DESIGN_PARSER_DATA_DIR='D:\通信建筑工程全流程 Agent 项目\01_官方赛题资料'`。
- 基线变更（total/passed/failed/warning 或规则分布）必须同步 `tools/regression_check.py` 与 docs/17 等文档，并注明口径依据。
- CABLE_AMONT 长度固定 30（官方已确认；v2.0 表 20 不采用，属覆盖项）。
- 每次改动后向 `DEVELOPMENT_MEMORY.md` 末尾追加记录（沙箱内 ACL 异常时用 escalated 写）。
- 对外材料（D01-D07 清单、官方案例索取）不经用户确认不发送。

---

## Phase 0：决策门（先收齐，再动代码）

| 门 | 选项 | 影响 | 证据/依据 |
|---|---|---|---|
| D0.1 推送 GitHub | 批准 / 不批准 | 22 个本地提交是否上线 | 交接摘要「待用户批准」 |
| D0.2 /tf 端点去留 | 保留（建议）/ 交付前删 | 保留则 docs/06 加临时标注；删除则移除端点+测试 | docs/15 第 4 项 |
| D0.3 R-BOM-001 等级 | 升 error / 保持 warning | 升则 TC-01 基线 109/8/98(w=3)→109/8/101(w=0) | docs/10 小待办 |
| D0.4 字段长度 v2.0 对齐 | 执行 / 搁置 | 执行则 R032 口径按官方 v2.0，需回归对比 | docs/15 A1 |

---

### Task 1: R-BOM-001 严重等级升 error（仅当 D0.3=升 error）

**Files:**
- Modify: `design_parser/rule_engine.py`（SEVERITY_MAP，约 103 行 `"R-FIBER-001": "error",` 之后）
- Test: `tests/test_review_severity_stats.py`（新增 1 条）
- Modify: `tools/regression_check.py`（TC-01 断言 (109,8,98,3) → (109,8,101,0)）
- Docs: `docs/17_规则可用性验证_Dify实测.md`（自制 BOM 包 63/57/3 → 63/57/6）

**Interfaces:**
- Consumes: `api.py` 的 `_normalize_severities`（按 SEVERITY_MAP 归一化等级）
- Produces: SEVERITY_MAP 含 `"R-BOM-001": "error"`；review.failed_rules 计 R-BOM-001

- [ ] **Step 1: 写失败测试**（tests/test_review_severity_stats.py 追加）

```python
def test_r_bom_001_maps_to_error():
    from design_parser.rule_engine import SEVERITY_MAP
    assert SEVERITY_MAP.get("R-BOM-001") == "error"
```

- [ ] **Step 2: 运行确认失败**

```powershell
D:\python\python.exe -m pytest tests/test_review_severity_stats.py::test_r_bom_001_maps_to_error -q
```
Expected: FAIL（KeyError/断言失败）

- [ ] **Step 3: 实现**

```python
    "R-FIBER-001": "error",
    "R-BOM-001": "error",  # 2026-08-22 用户决策：附表2 物料匹配按 error（Dify 报告不再显示 warning）
```

- [ ] **Step 4: 验证**

```powershell
D:\python\python.exe -m pytest tests/ -q
$env:DESIGN_PARSER_DATA_DIR='D:\通信建筑工程全流程 Agent 项目\01_官方赛题资料'
D:\python\python.exe tools/regression_check.py
```
Expected: pytest ≥136 passed；回归门 TC-01 断言先按 (109,8,101,0) 更新后再跑，14 项 ALL PASS（赛题一/四 287/57/230 不变，R-BOM-001 在赛题包不触发）。

- [ ] **Step 5: 提交**

```bash
git add design_parser/rule_engine.py tests/test_review_severity_stats.py tools/regression_check.py docs/17_规则可用性验证_Dify实测.md
git commit -m "feat(rules): promote R-BOM-001 to error severity per decision"
```

---

### Task 2: R005_2 启用评估与路由（R-REL-002）

**Files:**
- Modify: `api.py`（RULE_ROUTING 四个 GIS 类目列表，与 R005_1/R005_3 同组，约 98-134 行）
- Test: `tests/test_rule_routing_extra.py`（ACTIVE 加 `"R005_2"`）
- Test: `tests/test_rule_r005_2.py`（新建，引擎级用例）
- Docs: `docs/20_官方口径催办清单.md` 或独立评估记录（依结论）

**Interfaces:**
- Consumes: `design_parser/rule_engine.py:2221` `check_site_pm_boite_pbo_bidirectional(ctx)`（已注册，key `"R005_2"`，severity error）
- Produces: 四个 GIS 类目路由含 `"R005_2"`

- [ ] **Step 1: 口径评估（只读）**

```powershell
Select-String -Path "design_parser\rule_engine.py" -Pattern "R005_2" -Context 3,12
```
核对 `check_site_pm_boite_pbo_bidirectional` 语义 = BOITE(TYPE=PBO).REF_PM ↔ SITE(TYPE=PM).CODE 双向引用（官方 R-REL-002 主从孤立性）。
同时打开 `docs/官方固定数据/官方审查规则库v2.0.xlsx` 核对 R-REL-002 行。

- [ ] **Step 2: 决策 gate**
  - 口径一致 → 继续 Step 3；
  - 不一致 → 输出评估记录（差异/依据/建议），本任务结束，等官方确认。

- [ ] **Step 3: 写失败测试**（tests/test_rule_r005_2.py 新建；tests/test_rule_routing_extra.py ACTIVE 加 R005_2）

```python
"""R005_2 路由 + 引擎级行为测试（官方 R-REL-002 PBO↔PM 主从孤立性）。"""
from api import RULE_ROUTING
from design_parser.rule_engine import ALL_RULES


def test_r005_2_routed_in_gis_categories():
    for cat in ["完整设计图", "竣工图", "竣工图（含BOM）", "设计图（含纤芯）"]:
        assert "R005_2" in RULE_ROUTING[cat]


def test_r005_2_registered():
    assert "R005_2" in ALL_RULES  # 键存在即注册（引擎实现已在 rule_engine.py:2221）
```

- [ ] **Step 4: 运行确认失败**（预期：R005_2 不在路由 → AssertionError）

- [ ] **Step 5: 实现**：api.py 四个 GIS 类目列表 `"R005_1","R005_3",` 后追加 `"R005_2",`；tests/test_rule_routing_extra.py `ACTIVE = {"R005_1","R005_2","R005_3","R027","R028","R033"}`。

- [ ] **Step 6: 基线核验**

```powershell
D:\python\python.exe -m pytest tests/ -q
$env:DESIGN_PARSER_DATA_DIR='D:\通信建筑工程全流程 Agent 项目\01_官方赛题资料'
D:\python\python.exe tools/regression_check.py
```
- 若赛题一/四 R005_2=0（REF_PM 引用均存在或模型不触发）→ 基线 287/57/230 不变，直接过；
- 若新增问题 → 逐条核对是否为真实 PBO.REF_PM 缺失引用；真实则更新 `tools/regression_check.py` 规则分布与 docs/17，并在提交信息注明口径。

- [ ] **Step 7: 提交**

```bash
git add api.py tests/test_rule_routing_extra.py tests/test_rule_r005_2.py tools/regression_check.py docs/17_规则可用性验证_Dify实测.md
git commit -m "feat(routing): enable R005_2 per official R-REL-002 (PBO-PM bidirectional)"
```

---

### Task 3: 字段长度按 v2.0 对齐（仅当 D0.4=执行）

**Files:**
- Modify: `design_parser/mappings/layer_mapping.yaml`（各图层 `field_lengths`）
- Test: `tests/test_length_rules_v2.py`（新建）
- Modify: `tools/regression_check.py`（若 R032 基线变）

**Interfaces:**
- Consumes: `docs/官方固定数据/字段口径配置_v2.0.json`（`length_rules`，权威值）；现有 yaml 键名为 DBF 截断名（如 NB_FIBRE_U/NB_CASSETT/CODE_POSTA），**键名保持不变，只改值**
- Produces: yaml 各图层 field_lengths 与 v2.0 对齐（CABLE_AMON 保持 30 覆盖；v2.0 未列字段如 X/Y 保持现值并注记）

- [ ] **Step 1: 生成差异表（脚本）**

```powershell
@'
import io, json, yaml
layers = yaml.safe_load(io.open("design_parser/mappings/layer_mapping.yaml", encoding="utf-8"))["layers"]
cfg = json.load(io.open("docs/官方固定数据/字段口径配置_v2.0.json", encoding="utf-8-sig"))
v2 = cfg["length_rules"]
for layer, spec in layers.items():
    cur = spec.get("field_lengths") or {}
    new = v2.get(layer) or {}
    diffs = {k: (cur.get(k), v) for k, v in new.items() if cur.get(k) != v}
    if diffs:
        print(layer, diffs)
'@ | D:\python\python.exe -
```
Expected 输出（已知差异示例）：
- BOITE: TYPE_STRUC 30→50、CAPACITE 10→3、NB_SPLICES 10→5、NB_FIBRE_U 10→3、NB_CASSETT 10→3、CODE_POSTA 10→5
- CABLE: DIAMETRE 10→2、CAPACITE 10→3、MODULO 10→2、NB_FIBRE_U 10→3、NB_FIBRE_D 10→3、LONGUEUR 24→10
- INFRASTRUCTURE: LONGUEUR 24→10
- 其余图层以脚本输出为准；`CABLE_AMON` 若显示 20→30 属覆盖项，保持 30 并忽略差异。

- [ ] **Step 2: 写失败测试**（tests/test_length_rules_v2.py）

```python
"""字段长度 v2.0 对齐测试（官方字段口径配置 v2.0；CABLE_AMON 按已确认 30 覆盖）。"""
import io
import yaml

LAYERS = yaml.safe_load(io.open("design_parser/mappings/layer_mapping.yaml", encoding="utf-8"))["layers"]


def _fl(layer, key):
    return LAYERS[layer]["field_lengths"].get(key)


def test_cable_lengths_v2():
    assert _fl("CABLE", "CAPACITE") == 3
    assert _fl("CABLE", "DIAMETRE") == 2
    assert _fl("CABLE", "MODULO") == 2
    assert _fl("CABLE", "LONGUEUR") == 10
    assert _fl("CABLE", "NB_FIBRE_U") == 3


def test_boite_lengths_v2():
    assert _fl("BOITE", "CAPACITE") == 3
    assert _fl("BOITE", "NB_FIBRE_U") == 3
    assert _fl("BOITE", "NB_CASSETT") == 3
    assert _fl("BOITE", "CODE_POSTA") == 5


def test_cable_amont_override_kept():
    assert _fl("BOITE", "CABLE_AMON") == 30  # 官方已确认 Longueur=30，覆盖 v2.0 表 20
```

- [ ] **Step 3: 运行确认失败**

- [ ] **Step 4: 更新 layer_mapping.yaml**（按 Step 1 差异表逐层改值；键名不动）

- [ ] **Step 5: 真实数据回归对比**

```powershell
D:\python\python.exe -m pytest tests/ -q
$env:DESIGN_PARSER_DATA_DIR='D:\通信建筑工程全流程 Agent 项目\01_官方赛题资料'
D:\python\python.exe tools/regression_check.py
```
Expected：赛题一/四 `R008/R012/R021/R032=0` 保持（CAPACITE 3 位/DIAMETRE 2 位/LONGUEUR 10 位均覆盖真实数据）；TC-01 不变。
若出现新 R032 失败：逐条核对其是否为真实超长（如 LONGUEUR 超过 10 位小数位），真实则按「v2.0 口径」更新基线并记录。

- [ ] **Step 6: 提交**

```bash
git add design_parser/mappings/layer_mapping.yaml tests/test_length_rules_v2.py tools/regression_check.py
git commit -m "feat(fields): align field lengths with official v2.0 config (CAPACITE/DIAMETRE/MODULO/LONGUEUR)"
```

---

### Task 4: D01-D07 官方口径催办清单（文档，用户确认后发送）

**Files:**
- Create: `docs/20_官方口径催办清单.md`

**Interfaces:**
- Consumes: `docs/15_未做项报告与规则对照.md` 第一节、`design_parser/mappings/business_params.json` 当前值
- Produces: 一页可直接发送的文本（D01~D07 每项：待确认内容/当前默认值/影响/问题表述/期望答复）

- [ ] **Step 1: 从 business_params.json 提取当前默认值**（损耗率、预留、盘长、包装、纤芯策略）
- [ ] **Step 2: 写 docs/20**（表格 + 末尾「请组委会确认」段落；含 D06 对 B6 的阻塞说明、D04/D05 对 BOM/纤芯终值的影响）
- [ ] **Step 3: 提交** `git add docs/20_官方口径催办清单.md && git commit -m "docs: D01-D07 official confirmation checklist ready to send"`
- [ ] **Step 4: 用户确认后发送**（发送动作=用户，文件提供全文）

---

### Task 5: 标准答案案例包（自建 10 案例 + 核对表）

**Files:**
- Create: `tests/data/standard_cases/标准答案核对表.xlsx`（或 docs/ 下）
- Modify: `docs/19_标准答案案例整理.md`（核对结果列回填）

**Interfaces:**
- Consumes: tests/test_standard_cases.py 的 EXPECTED_RULES、docs/19 表格、docs/17 实测数字
- Produces: 标准答案核对表（案例ID/文件/场景/预期规则/等级/依据/本地实测/说明）

- [ ] **Step 1: 生成核对表（openpyxl 脚本）**：按 docs/19 第二节 10 行数据生成 xlsx，字段含「本地 pytest 结果」列
- [ ] **Step 2: 复核**：`D:\python\python.exe -m pytest tests/test_standard_cases.py -q` 全过，回填结果列
- [ ] **Step 3: 提交** `git add tests/data/standard_cases/标准答案核对表.xlsx docs/19_标准答案案例整理.md && git commit -m "docs: standard-answer checklist workbook (10 self-built cases)"`

---

### Task 6: 量化对比实验方案（评测材料，支撑「时间缩短≥50%」）

**Files:**
- Create: `docs/21_量化对比实验方案.md`
- Create（本地）: `05_测试记录/量化对比/记录模板.xlsx`

**Interfaces:**
- Consumes: 赛题方案指标（子赛题4：BOM/工艺/纤芯自动生成且时间缩短≥50%）、docs/08 评测记录
- Produces: 实验协议 + 记录模板 + 最终对比报告结构

- [ ] **Step 1: 写方案**：样本集（N 包，建议复用评测表 2.1 的 11 包）、人工审查计时表、自动端到端时间取数口径（Dify run 耗时 vs data-pipeline 耗时）、指标（时间缩短%、检出一致率）、分工与归档位置
- [ ] **Step 2: 生成记录模板 xlsx**（人工耗时/检出问题数/自动耗时/检出问题数/差异说明 五列）
- [ ] **Step 3: 提交方案文档**；数据采集需团队人工执行（human time），完成后并入 EVALUATION_REPORT

---

### Task 7: B6 施工指令后端素材版（gate：D06 答复或用户拍板「先做简化版」）

**Files:**
- Create: `design_parser/construction_kb.py`
- Modify: `api.py`（新增 `GET /project/{id}/construction-kb`）
- Test: `tests/test_construction_kb.py`
- Docs: `api_docs.md`、`docs/04_FastAPI接口说明.md`

**Interfaces:**
- Consumes: `docs/官方固定数据/施工规程知识库v2.0.xlsx`（10 条 PCP 工序）、`docs/官方固定数据/设计对象-物料-工序映射表.xlsx`（官方 29 物料码→设计对象/工序）、`ProjectData.get_engineering_data()`
- Produces: `GET /project/{id}/construction-kb?object_type=BOITE` → `{object_type, procedures:[{pcp_ref, name, steps, materials, acceptance_points, source_page}]}`

- [ ] **Step 1: 写失败测试**（固定知识库读取 + 按 object_type 过滤 + 返回结构断言）
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 construction_kb.py + api.py 端点**（复用 bom_fiber_reader 的 Excel 读取模式；无固定库时返回空结构 + warnings 提示）
- [ ] **Step 4: pytest 全量 + 回归门 + 真实包（赛题四）接口实测**
- [ ] **Step 5: 文档同步 + 提交**（`feat(construction): backend PCP/process material endpoint`）
- [ ] 说明：若 D06 要求五级颗粒度全量版 → 走 Dify 施工主节点改造（+200~350 行），本任务暂停，另行计划

---

### Task 8: 交付前收尾

- [ ] **8.1 /tf 端点执行 D0.2**：保留 → docs/06 加「临时桥接，交付前评估」标注；删除 → api.py 移除 `/tf/{filename}` + 相关测试 + api_docs 同步，提交 `chore: remove /tf bridge endpoint`
- [ ] **8.2 安全加固评估**：产出 `docs/22_生产安全加固建议.md`（鉴权/限流/密钥管理，仅设计不实现），提交 docs
- [ ] **8.3 文档同步**：docs/17 数字（Task 1/2 若改基线）、DELIVERY_README、api_docs、EVALUATION_REPORT
- [ ] **8.4 推送 GitHub**（D0.1 批准后）：`git push -u origin codex/business-params`，ls-remote 验证
- [ ] **8.5 DEVELOPMENT_MEMORY.md 收尾记录**

---

## 时间估算（preflight，模型 20-40 tokens/s）

| 阶段 | Tokens | Model time | Tool time | Human time | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Phase 0 决策门 | 300 | 8s-15s | 1-5m | 5-30m | 6m-35m |
| Task 1 R-BOM-001 | 1200 | 30s-1m | 5-15m | 0 | 6m-16m |
| Task 2 R005_2 | 1800 | 45s-1m30s | 7-25m | 0 | 7m-27m |
| Task 3 字段长度 v2.0 | 1500 | 38s-1m15s | 7-20m | 0 | 7m-21m |
| Task 4 D01-D07 清单 | 900 | 22s-45s | 2-10m | 0 | 2m-11m |
| Task 5 标准答案核对表 | 800 | 20s-40s | 3-15m | 0 | 3m-16m |
| Task 6 量化对比方案 | 1000 | 25s-50s | 2-10m | 0-30m | 2m-41m |
| Task 7 B6 后端素材版 | 2200 | 55s-1m50s | 10-40m | 0-1h | 11m-1h42m |
| Task 8 收尾 | 1000 | 25s-50s | 5-20m | 10m-1h | 15m-1h20m |
| **合计** | 10700 | 4m28s-8m55s | 41m-2h40m | 15m-3h | **1h-5h48m** |

## Risks

- **基线变化风险**（Task 2/3）：R005_2 或字段长度可能让赛题一/四新增问题。缓解：先对比后更新基线，每条新问题核对该口径真实性，需用户认可。
- **官方答复不确定**（D01-D07/D06）：BOM 终值、B6 全量版延后。缓解：先做无阻塞任务，B6 走后端简化版兜底。
- **推送未批准**：所有提交本地化，最终一次推送；推送前做敏感信息扫描（Key/人名）。
- **沙箱 ACL**：DEVELOPMENT_MEMORY.md 沙箱内写可能失败，用 escalated 写入（历史已验证）。
- **自建案例权威性**：标准答案仅作过渡，官方 5~10 案例到达后按 docs/19 第五节替换。

## Self-Review（writing-plans）

- 覆盖核对：D01-D07（Task 4）、官方案例（Task 5 + docs/19）、B6（Task 7，gate）、/tf（Task 8.1）、安全（8.2）、推送（8.3-8.4）、R005_2（Task 2）、R-BOM-001（Task 1）、字段长度（Task 3）、量化对比（Task 6）——docs/10/14/15/18 待办全部有落点。
- 无占位符：代码步骤均含实际测试/实现/命令；Task 2 Step 2 的「不一致」分支为决策 gate（评估类任务，结论记录为交付物）。
- 类型一致性：R005_2 键与注册名一致（rule_engine.py:2959）；SEVERITY_MAP 键名与 issues.rule_id 一致；yaml 键名保持 DBF 截断名。
