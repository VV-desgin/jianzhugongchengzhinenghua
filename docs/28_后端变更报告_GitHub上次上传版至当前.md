# 28 后端变更报告：GitHub 上次上传版 → 当前版（2026-08-22）

> 对比基准：**之前后端 = GitHub `origin/main`（`fb22feb`，仓库 VV-desgin/jianzhugongchengzhinenghua，最后上传版本）**
> 当前后端 = 本地分支 `codex/business-params` HEAD（**47 个提交领先 origin/main，尚未上传**，含 2026-08-22 全部改动）
> 部署状态：云服务器 118.31.127.213:8001 已运行当前代码（uvicorn PID 51337），Dify 实测通过。

## 一、总体统计

| 指标 | 值 |
|---|---|
| 提交数 | 47（fb22feb..HEAD） |
| 变更文件 | 64 个（源码+测试+文档+配置） |
| 代码量 | +4181 / −432 行 |
| 新增源码文件 | bom_builder.py、bom_formula.py、business_params.py、construction_kb.py、business_params.json |
| 测试 | 156 passed（原 93） |

## 二、功能与代码变更（按模块）

### 1. 业务参数体系（新增）
- `business_params.json` + 加载器：损耗率/预留长度/包装取整/利旧/纤芯策略，参数来源标注 YD/T 5102-2024、GB 51158-2015、GB 50373-2019；
- 新端点 `GET /agent/business-params`；`data-pipeline` 响应顶层新增 `business_params`（供 Dify 总控透传）；
- 2026-08-22：D01~D07 官方口径全部落定（`_meta.official_decisions`），`official_pending` 清空。

### 2. BOM 后端权威计算（新增）
- `design_parser/bom_builder.py` + `GET /agent/bom`：设计对象→物料（官方 29 码 + 4 全局工程项）→损耗/预留/取整→利旧冲减（reuse 只减新购、不删对象/工序）；
- 输出列：设计数量/损耗数量/预留数量/最终数量 + 对应工序/使用位置 + 待人工确认标记；
- 替换 Dify 侧 BOM V0.6 手改方案（Dify 零改动）。

### 3. 纤芯
- `fiber_tables` 注入 `engineering_data`（纤芯工具 V0.5 直接消费）；
- 新增 R-FIBER-002（无纤芯表时按光缆属性推断同路由重复，warning）；
- `fiber_assignments` 注入：分配从 1-1-1 改为跳过已占芯（TC-09 从 1-1-7 起，冲突 0→3）；
- 性能：`read_sheet_rows_multi` 一次打开工作簿读全部页签（SRO TOPO 120 页签），服务器延迟 −29%、Dify 总控全流程 89s→64.4s。

### 4. 审查规则（路由/等级/口径）
- R005_1 按官方 R-REL-001 启用（8-16 用户决策）；R005_3/R027/R028/R033 路由；
- **R005_2 按官方 R-REL-002 路由（2026-08-22）**：PBO↔PM 双向主从孤立，赛题包 0 命中、黎包真实检出（TC-04 +1、TC-10 +2）；
- **R-GIS-001~006 + R-SAFE-001~012 并入 data-pipeline 主流程**（has_gis 自动附加）→ 64 条规则全自动执行（赛题四 287/57/230）；
- 新增 R-SAFE-010（直埋）/011（杆路）/012（防雷接地），电力线交越 5 档、公路离地 5.5m、墙壁净距按 GB 51158 表7.6.3；
- **R-BOM-001 升 error（2026-08-22）**：TC-01 基线 109/8/98(w=3)→109/8/101(w=0)；
- 必填字段按 v2.0 补齐（IMB QUARTIER/NOM_VOIE/NOM_BATIMENT、PTECH NOM）+ BOM 全局工程项；
- 字段长度按 v2.0 对齐（CAPACITE 3、DIAMETRE 2、MODULO 2、LONGUEUR 10 等 17 处）；R032 数值列按列宽语义跳过串长比较（修复 314 条 float 精度误报）。

### 5. 安全与接口
- CORS 白名单（localhost/118.31.127.213/43.138.167.41）；`file_url` SSRF 防护（协议/内网 IP/200MB 上限）；
- `compact` 参数：赛题四响应 2.34MB→168KB（−93%）；`excel_limit` 默认 500→0；
- 新端点：`/agent/bom`、`/agent/business-params`、`GET /project/{id}/construction-kb`（施工素材，10 条 PCP 工序+物料-工序映射）、`GET /tf/{filename}`（Dify remote_url 测试桥接，临时）；
- 既有修复（本区间内）：orchestrate request_id、review_results severity 归一化、include_tables 崩溃、R021 排除参考表、R016 仅查官方 8 图层、SRO TOPO 真实表头识别。

### 6. 回归门
- `tools/regression_check.py` 基线同步：场勘 43/43/0、赛题一/四 287/57/230（+R-GIS-004×2）、TC-01 109/8/101；14 项 ALL PASS（exit=0）。

## 三、测试与 Dify 实测（2026-08-22）

### 本地/云服务器
- pytest 156 passed；回归门 14 项 ALL PASS；云服务器直测赛题四 review 287/57/230/0、R032=0、construction-kb 正常。

### Dify PROD 全流程（黎俊杰 10 包，部署后实测，10/10 succeeded）

| 包 | review(总/过/败) | 说明 |
|---|---|---|
| TC-02 BOM 无法匹配 | 60/57/3 | 初版无违规数据（与 docs/17 一致） |
| TC-03 编码重复 | 61/57/4 | R007 fatal 检出 |
| TC-04 孤立设备 | **64/57/7** | 较部署前 +1 = R005_2 新路由真实检出 |
| TC-05 光缆未连接 | 62/57/5 | R008/R005_4 检出 |
| TC-06 缺少图层 | 60/51/9 | R001/R016/R033 fatal |
| TC-07 缺少文件 | 62/56/6 | 新基线（R001+R017 族） |
| TC-08 容量超限 | 61/57/4 | R019 检出 |
| TC-09 纤芯重复 | 61/57/3 | R-FIBER-002 warning |
| TC-10 字段为空 | **65/57/8** | 较部署前 +2 = R005_2×2 真实检出 |
| TC-01 2.6 基线 | 60/57/3 | R005_1×2 + R021（PTECH.NOM，8-20 必填改动） |

> TC-02 首跑失败为 Dify 外部通义 embedding 插件连接中断（非后端），重试即 succeeded。结果 JSON：`dify_lx_*_20260822.json`（可视化目录存档）。

### 与之前版本的行为差异（Dify 可见）
1. R-BOM-001 由 warning 升 error（自制 BOM 包 63/57/3→63/57/6）；
2. R005_2 新增检出（孤立/字段为空类案例 +1~2 条）；
3. 赛题一/四 review 285/57/228→287/57/230（R-GIS-004×2，8-20 已上线）；
4. TC-01 2.6 60/57/3（含 8-20 必填改动带来的 R021 PTECH.NOM）。

## 四、交付文档（本区间新增/更新）

docs/10~18（待办/进度/规则总表/Dify 实测）、docs/19 标准答案案例 v1、docs/20 D01-D07 催办清单+答复记录、docs/21+25 量化对比方案与模板、docs/22 安全加固建议、docs/23 必填字段试跑分析、docs/24 标准答案核对表、docs/26 外部表格比对、docs/27 表格更新依据、docs/28 本报告；EVALUATION_REPORT 基线刷新（可追溯 207/230=90.0%）；api_docs 补 construction-kb。

## 五、包内文件最新性检查（2026-08-22）

- 交付目录已清理：记忆文档（DEVELOPMENT_MEMORY.md）与执行台账（.superpowers/）已移至 `../06_规划与想法/开发记忆/`；api.log→`../05_测试记录/日志/`；测试遗留（tc01bom_tmp、local_spot_checks）→`../05_测试记录/` 对应子目录；夹具备份→`../05_测试记录/工程包/`；缓存已删。
- 跟踪文件：git status 仅剩 `docs/06、docs/09 更新版` 的重命名（用户已去掉日期后缀，待用户确认后提交），其余 145 个跟踪文件全部为最新；api.py/rule_engine.py/layer_mapping.yaml/construction_kb.py 已与云服务器一致并验证。

## 六、未上传/待办

- **47 个提交未推送 GitHub**（推送待用户批准）；
- docs/06、09 更新版重命名待确认；
- /tf 桥接端点交付前删除、安全加固（鉴权/限流）生产前实施；
- 量化对比实验人工侧、官方标准答案案例（外部）；
- 可选机制：BOM 审批白名单、issue 级 Evidence、D04 三级利旧分级（团队决策）。
