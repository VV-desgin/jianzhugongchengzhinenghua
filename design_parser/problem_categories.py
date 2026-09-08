"""审查问题分类：对齐组委会官方五大问题分类体系。

官方分类（《图层表字段说明和数据校验规则.xlsx》问题分类体系）：
- 数据完整性：必填字段缺失、对象编号缺失、数据类型错误、单位错误、坐标缺失、重复对象、图表数据不一致
- 空间与安全：电力交越距离不足、建筑安全距离不足、路由重叠、管道冲突、设备安装间距不足、防雷接地不符合要求
- 资源：管孔容量不足、纤芯不足、设备端口不足、资源重复占用、利旧资源状态不明
- 逻辑一致性：拓扑连接错误、起止点不一致、光缆段断裂、图纸与材料表不一致
- 工程合理性：路由绕行、冗余不足、配置过度、材料选型不合理、施工不可达、工序冲突、保护措施不足
"""

from typing import Dict, Optional

CATEGORY_LABELS: Dict[str, str] = {
    "data_completeness": "数据完整性",
    "spatial_safety": "空间与安全",
    "resource": "资源",
    "logic_consistency": "逻辑一致性",
    "engineering_reasonableness": "工程合理性",
}

# 规则 -> 官方问题分类（未列出的规则默认归入“工程合理性”）
RULE_PROBLEM_CATEGORY: Dict[str, str] = {
    # 数据完整性：文件/图层/字段/编码/坐标系/长度
    "R001": "data_completeness",
    "R002": "data_completeness",
    "R003": "data_completeness",
    "R004": "data_completeness",
    "R005": "data_completeness",
    "R006": "data_completeness",
    "R007": "data_completeness",
    "R016": "data_completeness",
    "R017": "data_completeness",
    "R018": "data_completeness",
    "R021": "data_completeness",
    "R031": "data_completeness",
    "R032": "data_completeness",
    "R033": "data_completeness",
    "R-FLD-001": "data_completeness",
    "R-FLD-002": "data_completeness",
    "R-FILE-001": "data_completeness",
    # 空间与安全：几何重叠/包含/端点重合/安全距离
    "R006_3": "spatial_safety",
    "R006_4": "spatial_safety",
    "R006_5": "spatial_safety",
    "R006_6": "spatial_safety",
    "R010": "spatial_safety",
    "R013": "spatial_safety",
    "R014": "spatial_safety",
    "R015": "spatial_safety",
    "R025": "spatial_safety",
    "R026": "spatial_safety",
    "R027": "spatial_safety",
    "R028": "spatial_safety",
    "R029": "spatial_safety",
    "R-GIS-001": "spatial_safety",
    "R-GIS-002": "spatial_safety",
    "R-GIS-003": "spatial_safety",
    "R-GIS-004": "spatial_safety",
    "R-GIS-005": "spatial_safety",
    "R-GIS-006": "spatial_safety",
    "R-GIS-007": "spatial_safety",
    "R-SAFE-001": "spatial_safety",
    "R-SAFE-002": "spatial_safety",
    "R-SAFE-003": "spatial_safety",
    "R-SAFE-004": "spatial_safety",
    "R-SAFE-005": "spatial_safety",
    "R-SAFE-006": "spatial_safety",
    "R-SAFE-007": "spatial_safety",
    "R-SAFE-008": "spatial_safety",
    "R-SAFE-009": "spatial_safety",
    "R-SAFE-010": "spatial_safety",
    "R-SAFE-011": "spatial_safety",
    "R-SAFE-012": "spatial_safety",
    # 资源：容量/纤芯/端口/物料
    "R007_1": "resource",
    "R007_2": "resource",
    "R011": "resource",
    "R012": "resource",
    "R019": "resource",
    "R020": "resource",
    "R022": "resource",
    "R030": "resource",
    "R034": "resource",
    "R-FIBER-001": "resource",
    "R-FIBER-002": "resource",
    "R-FIBER-003": "resource",
    "R-DAT-001": "resource",
    "R-BOM-001": "resource",
    # 逻辑一致性：引用/拓扑/孤立/断裂
    "R005_1": "logic_consistency",
    "R005_2": "logic_consistency",
    "R005_3": "logic_consistency",
    "R008": "logic_consistency",
    "R009": "logic_consistency",
    "R005_4": "logic_consistency",
    "R-LIFE-001": "logic_consistency",
    "R-REL-001": "logic_consistency",
    "R-REL-004": "logic_consistency",
    "R023": "logic_consistency",
    "R024": "logic_consistency",
}


def problem_category_for(rule_id: str) -> str:
    """返回规则所属官方问题分类 key，未知规则默认“工程合理性”。"""
    return RULE_PROBLEM_CATEGORY.get(rule_id, "engineering_reasonableness")


def problem_category_label(category: Optional[str] = None) -> str:
    """返回分类中文标签。"""
    key = category or "engineering_reasonableness"
    return CATEGORY_LABELS.get(key, key)
