# 通信设计审查 Agent — API 接口说明（V0.2）

## 一、安装与启动

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python api.py
```

支持 Python 3.10 ~ 3.14（3.14 自动使用 pyshp 读取 SHP）。启动后监听 `http://0.0.0.0:8000`。

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

#### GET /project/{id}/device/{code} — 查询设备

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

### Agent 接口（支持文件上传或 file_url）

#### POST /agent/data-pipeline — 纯数据流水线（Dify 主接口）

上传工程包后返回固定结构 JSON：`success`、`project_id`、`project_name`、`project_type`、`layers`、`summary`、`review`、`warnings`、`errors`、`status`，并保留 `file_info`、`review_results`、`serious_issues_detected`、`excel_data`、`pdf_text` 旧字段。

- `success=true` 表示流水线执行成功，不代表工程无问题。
- `review.issues[]` 每项固定包含 `rule_id`、`object_type`、`object_id`、`field`、`severity`、`message`、`source`。
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
