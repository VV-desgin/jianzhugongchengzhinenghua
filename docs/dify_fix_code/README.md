# Dify 完整可粘贴代码包（2026-09-05）

本目录每个文件都是完整代码/完整替换块，供 Dify 网页端代码编辑器直接整段复制。

| 文件 | 粘贴到哪个节点 | 说明 |
|---|---|---|
| `01_parse_BOM_result_FULL.py` | 总控 → 解析黄福林BOM结果（1786023921854） | 整个代码编辑器内容替换为本文 |
| `02_parse_review_api_FULL.py` | 总控 → 解析真实接口返回（1785836509606） | 整个代码编辑器内容替换为本文 |
| `03_final_report_formatter_FULL.py` | 总控 → 全流程交付报告格式化（1786031004832） | 整个代码编辑器内容替换为本文 |
| `04_construction_fix_snippets_FULL.py` | 施工指令工具 → 代码执行（1785839947624） | 按文件内“替换位置 1~6”逐段整段替换；每个替换块都是完整代码，不含省略号 |

配套操作（非代码）：

- 总控 1786023921854：右侧输入变量新增 `api_success(boolean)`、`api_error(string)`，来源选 1786367437101；
- 总控 1785836509606：右侧输出变量新增 `review_state/review_reason/review_error(string)`；
- 总控 1786031004832：输入变量新增 `environment_pending_count/manual_package_count(number)`、`review_state(string)`；输出变量新增 `result_type/stage_results_json(string)`；
- 总控 End 1785573827916：输出变量新增 `overall_status/result_type/stage_results_json`；
- 施工 End 1785841073663：输出变量新增 `environment_pending_count/manual_package_count(number)`、`pending_review_items_json(string)`；
- If-Else 1785836928806：true 分支新增 `review_state == "executed"` 条件。

> 注：施工 04 文件中的第 6 段（return 追加）需要整段复制到该节点最外层 return 字典内部；不要直接整文件运行。
> 纤芯引擎完整代码待 FIB-02/03 策略确定后补齐，当前不提供整节点替换文件。
