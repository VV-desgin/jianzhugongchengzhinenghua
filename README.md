# 通信工程智能化全流程交付 Agent（设计解析引擎）

面向通信线路工程（FTTH/FTTx）设计图、竣工图与工程表格的确定性解析审查引擎。
后端基于 FastAPI 提供统一 HTTP 接口，输出结构化审查结果、BOM 物料清单、纤芯分配方案与施工指令素材；
业务数字全部由确定性规则引擎计算，不依赖大模型生成，结果可复现、可追溯。

## 目录结构

```text
.
├─ api.py / schemas.py     # FastAPI 入口与响应模型
├─ design_parser/          # 工程解析、规则引擎、BOM/纤芯/施工计算
├─ tests/                  # 单元与回归测试（含标准案例夹具）
├─ docs/                   # 正式交付物文档
├─ bin/UnRAR.exe           # Windows 下 RAR 解压运行依赖
├─ license.txt             # UnRAR 第三方许可
├─ requirements.txt        # 运行依赖
└─ setup.py                # 打包配置
```

## 环境要求

- Python 3.10 ~ 3.14
- 空间矢量读取自动回退：3.10 ~ 3.13 使用 fiona，3.14+ 使用 pyshp

## 安装与启动

```powershell
pip install -r requirements.txt
pip install -e .
uvicorn api:app --host 0.0.0.0 --port 8001
```

启动后可通过 `http://127.0.0.1:8001/docs` 查看接口契约，使用 `GET /health` 做健康检查。
主审查接口为 `POST /agent/data-pipeline`（`multipart/form-data`，上传工程压缩包或传 `file_url`）。

## 测试

```powershell
pytest -q
```

## 正式交付物索引

| # | 文档 | 说明 |
|---|------|------|
| 0 | [作品系统说明](docs/00_作品系统说明.md) | 系统背景、架构、功能与技术路线 |
| 1 | [官方规则后端实现覆盖矩阵](docs/01_官方规则后端实现覆盖矩阵.md) | 官方规则与后端实现/测试的覆盖关系 |
| 2 | [engineering_data 字段说明](docs/03_engineering_data字段说明.md) | 统一工程对象模型的字段口径 |
| 3 | [FastAPI 接口说明](docs/04_FastAPI接口说明.md) | 接口参数、输出结构与异常码 |
| 4 | [GIS 规则测试记录](docs/05_GIS规则测试记录.md) | GIS/安全规则实测记录 |
| 5 | [已知限制清单](docs/06_已知限制清单.md) | 当前版本的边界与限制 |

仓库只包含后端代码、必要测试、运行依赖与上述正式交付物；内部过程记录与验收中间材料不随仓库发布。

## 外部数据与测试说明

本仓库只包含后端源码、必要测试、运行依赖与正式交付物文档，不包含：

- Dify 工作流节点代码与发布包；
- 官方固定数据（施工规程知识库 v2.0、设计对象-物料-工序映射表）；
- 本地运行记录、验收中间材料、评测 JSON 与图片证据。

施工知识库相关测试默认读取 `docs/官方固定数据/`。部署或本地复现时可用环境变量指定实际目录：

```powershell
$env:DESIGN_PARSER_FIXED_DATA_DIR = "D:\path\to\官方固定数据"
pytest -q
```

未提供官方固定数据时，相关测试会自动跳过；后端接口仍返回空结构，并在 `warnings` 中说明缺失原因。
