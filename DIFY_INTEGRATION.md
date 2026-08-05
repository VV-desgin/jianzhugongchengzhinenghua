# 通信设计审查 Agent — Dify 接入文档（V0.2）

| 项目 | 说明 |
|------|------|
| 基础 URL | `http://<服务IP>:8000` |
| 认证 | 无 |
| 主接口 | `POST /agent/data-pipeline`（纯数据，不依赖 LLM） |
| 超时建议 | data-pipeline 120 秒；orchestrate（含 LLM）600 秒 |

## 一、接口选择

- **POST /agent/data-pipeline** — Dify 主调用接口。纯数据流水线：上传工程包 → 解析 → 审查 → 返回固定结构 JSON，不经过外部大模型，结果可复现。
- **GET /health** — 健康检查，返回 `{"status": "ok"}`。
- **POST /agent/orchestrate** — 总控编排（含 LLM 报告）。需要配置 `LLM_API_URL`、`LLM_API_KEY`、`LLM_MODEL`；未配置时返回 502 `LLM 未配置`，不影响 data-pipeline 与 health。

## 二、/agent/data-pipeline 请求

支持 `multipart/form-data` 上传文件，或 JSON body 传入 `file_url`：

```bash
curl -X POST http://127.0.0.1:8000/agent/data-pipeline \
  -F "file=@场勘设计图.zip"
```

可选参数：`excel_limit`（Excel 行数上限，默认 500）、`pdf_chars`（PDF 字符数上限，默认 3000）。

## 三、响应契约

```json
{
  "success": true,
  "project_id": "uuid",
  "project_name": "场勘设计图",
  "project_type": "survey_design",
  "layers": [
    {
      "name": "IMB",
      "source_layer_name": "IMB",
      "exists": true,
      "geometry_type": "Point",
      "fields": [["CODE", "str"]],
      "feature_count": 51
    }
  ],
  "summary": {"layer_count": 23, "object_count": 244},
  "review": {"total_rules": 43, "passed_rules": 43, "failed_rules": 0, "issues": []},
  "warnings": [],
  "errors": [],
  "status": "success",
  "file_info": {},
  "review_results": [],
  "serious_issues_detected": false,
  "excel_data": {},
  "pdf_text": {},
  "engineering_data": {
    "project_id": "uuid",
    "project_type": "survey_design",
    "objects": {"cable": [], "boite": [], "ptech": []}
  }
}
```

说明：
- `success=true` 仅表示流水线执行成功，不代表工程无问题；业务问题在 `review.issues` 中。
- `engineering_data` 为统一工程对象输出（格式：project_id/project_type/objects，objects 包含 cable/boite/ptech），供 BOM / 纤芯分配工作流使用；字段覆盖 code/longueur/capacite/type/nb_fibre_util/hauteur_appui，每种对象只输出相关字段，缺失字段省略。
- `layers[].exists=true 且 feature_count=0` 表示图层存在但为空；`exists=false` 表示图层不存在或配套文件不完整。
- `review.issues[]` 每项固定包含 `rule_id`、`object_type`、`object_id`、`field`、`severity`、`message`、`source`。
- 异常时返回结构化 `errors`，不会输出 Traceback。
- `project_type` 枚举：`survey_design`、`full_design`、`as_built`、`unknown`。

## 四、环境要求

- Python 3.10 ~ 3.14（推荐 3.12）。
- 安装：`pip install -r requirements.txt`。Python 3.14 上 pip 会提示 `Ignoring fiona`（预期行为），自动安装 pyshp 纯 Python 回退，SHP 读取不受影响。
- 启动：`python api.py`，监听 `http://0.0.0.0:8000`。

## 五、配置步骤（Dify）

1. 启动服务并确认 `GET /health` 返回 200。
2. 在 Dify 中新建 HTTP 工具：
   - URL：`http://<服务IP>:8000/agent/data-pipeline`
   - 方法：POST
   - 请求体：`multipart/form-data`，字段 `file`（文件类型）
   - 超时：建议 120 秒
3. 用官方《场勘设计图.zip》测试，返回 `project_type=survey_design` 即接入成功。
4. 如需 LLM 报告，配置环境变量后另建工具调用 `/agent/orchestrate`。

## 六、Python 调用示例

```python
import httpx

with open("场勘设计图.zip", "rb") as f:
    r = httpx.post("http://127.0.0.1:8000/agent/data-pipeline",
                   files={"file": f}, timeout=120)
print(r.json()["project_type"])  # survey_design
```

## 七、验收指标（官方场勘包）

- project_type = survey_design
- 23 个图层 / 244 个对象
- IMB=51、SITE=1、BOITE/CABLE/PTECH=0（空图层保留）
- 连续运行 3 次，状态码与核心计数一致
