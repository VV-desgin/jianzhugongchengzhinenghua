# GIS 规则测试记录

生成：2026-08-08（2026-08-09 复核）｜测试基线：tests/test_gis_rules.py；全量 pytest 93 passed，回归门 tools/regression_check.py 14 项 ALL PASS

| 测试函数 | 覆盖规则 | 场景 | 结果 |
|---|---|---|---|
| test_zone_overlap_and_touch | R-GIS-001 | 同层多边形重叠判违规、共边/共端点不判违规 | 通过（基线） |
| test_range_containment | R-GIS-002/003/004 | SITE(PM)/BOITE(PBO)/CABLE(DISTRIBUTION) 越界检出、范围内不报 | 通过（基线） |
| test_cable_self_loop | R-GIS-005 | ORIGINE=EXTREMITE 自环检出 | 通过（基线） |
| test_endpoint_on_device_tolerance | R-GIS-006 | 端点距设备 >0.5m 检出、≈0 通过 | 通过（基线） |
| test_run_gis_checks_empty_and_api_shape | R-GIS 汇总 | 空项目不报错、返回结构固定 | 通过（基线） |

> 另：真实赛题一/四 GIS 相关告警：R014 非端点交叉 1 条、R023 孤立端点 1 条，均可复现。
