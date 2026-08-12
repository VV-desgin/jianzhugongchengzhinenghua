---
name: project-agent-guardrails
description: 通信建筑工程全流程 Agent 项目（design_parser_v0.3_delivery）的 Agent 工作守则。约束 Codex 在本项目内的一切操作：职责边界、项目知识、结构化模板、严格测试验证、版本化管理与常见误区规避。在修改代码、运行测试、部署线上、整理目录、撰写文档之前必须先阅读本守则及 DEVELOPMENT_MEMORY.md 文档索引。
---

# Agent 工作守则（通信建筑工程全流程 Agent 项目）

> 本守则约束 Codex 在本项目内的所有操作。优先级：用户显式指令 > 本守则 > 通用惯例。
> 每次操作前：先读本守则 + DEVELOPMENT_MEMORY.md 的文档索引；操作后：按模板追加记忆。

## 1. 明确职责边界

- 只做被要求的事。测试任务不等于改代码：2026-08-10 曾因"上传测试时顺手改分类代码"被用户批评，此类越权行为禁止。
- 发现 Bug 时：先给出证据与根因，报告后等待授权；只有用户明确批准（如"先把 bug 修复吧""执行 B"）才动手。
- 禁止事项：
  - 不擅自部署/重启生产服务器（118.31.127.213），部署必须经用户授权；
  - 不删除用户文件；清理仅限自己创建的临时目录/可再生缓存；
  - 不把测试/规划/部署产物塞进交付目录（design_parser_v0.3_delivery 只放交付物）；
  - 不把敏感信息（服务器密码、Dify API Key）写入任何文件或代码仓库；
  - 不回复"正在路由…"之类元话术。
- 允许事项：读日志/读文件诊断；工作区内整理与移动（先验证路径）；被授权后的修复、部署、归档。

## 2. 注入项目知识（关键事实）

### 架构

- 工具服务：118.31.127.213:8001，代码在 /root，Python 环境 `/root/miniconda3/envs/py310`，启动 `uvicorn api:app --host 0.0.0.0 --port 8001`（nohup/setsid 脱离会话），日志 /root/app.log 与 api.log。
- Dify：43.138.167.41（/v1），与工具服务分离，经 HTTP 调用工具服务；评测截图/报告与我们的日志对不上时，先查 Dify 工作流节点指向的 URL，勿直接归咎代码。
- 关键接口：`/health`、`/agent/data-pipeline`（确定性、0 LLM token、含 request_id 对账字段）、`/agent/full-pipeline`、`/agent/auto-review`；响应契约 `DataPipelineResponse`。

### 规则与数据

- RULE_ROUTING 按文件类别路由；附表关键词（BOM/纤芯/图层/规程）不得覆盖 GIS 工程类别（inside_gis 保护，2026-08-10 修复，勿回退）。
- R-BOM-001 目前仅在"Excel 工程包"路由；R005_1~3、R027、R028、R033 已实现未路由（见覆盖矩阵）。
- 审查结果统一字段：check_object / passed / problem_location / actual_value / expected_value / rule_id / error_description（+severity）。
- 测试基线：pytest 93 passed；回归门 `tools/regression_check.py` 14 项 ALL PASS；场勘 43/43、赛题一/四 277/49/228、TC-01 xlsx 106/8/98。
- 评测基线：TC-01 2.6 = 49/49/0、11 对象；测试集 zip 文件名编号与评测表编号不一致（需按"测试包文件名"映射）；TC-02（BOM）/TC-09（纤芯）缺违规数据，待决策补包或扩规则。

### 文档地图

交付文档：DELIVERY_README.md、api_docs.md、docs/01~06、EVALUATION_REPORT.md；过程文件在项目根目录 05_测试记录 / 06_规划与想法 / 07_部署更新包。完整清单见 DEVELOPMENT_MEMORY.md 文档索引。

## 3. 套用结构化模板

- 记忆条目：`## YYYY-MM-DD 主题（root）`，内容含 问题/修复/验证/产物/坑 五要素；追加不改写历史。
- 测试记录：案例编号、测试包文件名、期望、实际（规则分布）、截图、结论、时间戳。
- 部署记录：版本 md5、备份名（.bak.日期）、重启方式、复验命令、健康检查结果。
- 评测对照：表编号↔包文件名映射、检出结果、规则明细、耗时、备注。
- 新增文档/目录后必须同步登记到 DEVELOPMENT_MEMORY.md 文档索引。

## 4. 严格测试验证

- 任何代码改动后按序执行：`py_compile` → `pytest tests -q`（93 项）→ `python tools/regression_check.py`（14 项）→ 涉及接口用 TestClient 本地复测 → 涉及线上经授权部署后云测。
- 部署流程：备份（cp -a .bak.YYYYMMDD）→ api.py 与 schemas.py 必须同步上传（曾因只传 api.py 导致 ImportError）→ 按 PID kill + nohup/setsid 重启 → `/health` → 上传案例复验。
- 验证产物留痕：结果 JSON/日志存入 05_测试记录 对应子目录（质检测试集/评测跟踪表/结果JSON/日志/回归记录）。

## 5. 版本化管理

- 文件：修改前备份 `.bak.YYYYMMDD`；部署记录 md5。
- 目录：项目根 01~07 编号体系；交付目录只放交付物；过程文件进 05/06/07。
- 文档：表格/文档升版（如 1.0→1.1）保留原件；记忆文档时间戳追加。
- 回归：任何改动以回归门 ALL PASS 为交付门槛。

## 6. 规避常见误区

1. 文件名关键词分类：GIS 包优先，附表关键词不覆盖（已修复，勿回退）。
2. 中文管道编码：stdin heredoc 中文字面量会被转码成 ????；脚本用 ASCII 定位或把内容写文件再读；PowerShell 命令里的中文正常。
3. CRLF 行尾：远程文件是 CRLF 时 sed `$` 锚点失效，用行号删除或先转行尾。
4. `pkill -f 'uvicorn...'` 会匹配到自身命令行而自杀；用 pgrep 解析 PID 后 kill。
5. apply_patch 对含反斜杠的行匹配失败：改用 PowerShell 精确替换（UTF-8 无 BOM 写回）。
6. openpyxl 读完必须 `wb.close()`，否则文件句柄占用无法移动。
7. Dify 报告与引擎日志不符：先确认 Dify 调用的是哪个后端（曾出现 Dify 跑旧副本，43.138.167.41 从未调用过我们的日志）。
8. 严重等级：缺必要条件的案例不应统一为 warning（待确认口径）。
9. 评测表编号错位：对账必须带"测试包文件名"，7 个案例编号与 zip 文件名不一致。
10. 乱塞文件：测试/规划/部署产物一律进 05/06/07，交付目录只留交付物。
11. 本地测试服务不常驻：用 TestClient 或临时启动、测完即停，日志归 05_测试记录/日志。

## 7. 收尾检查清单

- [ ] 只做了被要求的事，未越权改代码/部署？
- [ ] 涉及代码改动：pytest 93 项 + 回归门 14 项通过？
- [ ] 测试/部署产物归档到正确目录？
- [ ] DEVELOPMENT_MEMORY.md 已追加记录、文档索引已登记？
- [ ] 无敏感信息落盘？
