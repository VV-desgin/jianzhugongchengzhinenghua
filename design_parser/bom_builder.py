"""后端标准 BOM 生成：设计对象 → 物料（官方映射表口径）→ bom_formula（损耗/预留/取整）→ 利旧冲减。

映射依据：docs/官方固定数据/设计对象-物料-工序映射表.xlsx（29 类）。
数值口径：business_params.json（source=行业参考默认值，待官方确认 D01~D07）。
原则：确定性计算，未覆盖/无法确定数量的物料标记"待人工确认"，不静默放行。
"""
from typing import Dict, List

from .business_params import load_business_params
from .bom_formula import compute_bom_quantity

# 官方映射表核心物料（设计对象-物料-工序映射表）
MAT_SAFETY = "500003800"        # 安全防护与准备（全局 1/项目）
MAT_MOBILIZE = "500003890"      # 运输、进场与退场（全局 1/项目）
MAT_CABLE = "500002050"         # ADSS 光缆 24 芯（KM，CABLE 图层）
MAT_POLE_7M_4IN = "500002480"   # 7m 电杆 4 英寸（PTECH）
MAT_POLE_9M_4IN = "500002337"   # 9m 单电杆 4 英寸（PTECH）
MAT_POLE_7M_3IN = "500002159"   # 7m 电杆 3 英寸（PTECH）
MAT_POLE_7M_25IN = "500004729"  # 7m 电杆 2.5 英寸（PTECH）
MAT_FDT_72 = "500002054"        # 72 芯杆式 FDT（BOITE，容量≥72）
MAT_BOX_16 = "500002142"        # 16 口杆式光箱（BOITE，容量<72）
MAT_SPLICING = "500000510"      # 光纤熔接（按接续点数）
MAT_CABLE_LABEL = "200000290"   # 光缆标签（CABLE 1/缆）
MAT_FDT_LABEL = "200000273"     # FDT 标签（FDT 1/个）
MAT_FAT_LABEL = "200000288"     # FAT 标签含二维码（16口箱 1/个）
MAT_POLE_LABEL = "500001742"    # 电杆标签（PTECH 1/杆）
MAT_HANGER = "200000185"        # 电缆吊架/固定夹板/挂钩
MAT_STEEL_WIRE = "200001033"    # 6mm 钢绞线（M，架空光缆）
MAT_TEST = "500002107"          # OTDR & OPM 测试（按光箱/接头点数）
MAT_PERMIT = "500002155"        # RT/RW 许可（M，长度口径）
MAT_PROJECT_MGMT = "500001887"  # 项目管理（全局 1/项目）
MAT_WAREHOUSE = "500001853"     # 仓储管理（全局 1/项目）
MAT_SURVEY = "500001519"        # 勘察设计（全局 1/项目）
MAT_ASBUILT = "500002108"       # 竣工图A1（全局 1/项目）

# 官方映射表：设计对象 → 对应工序（组委会材料需求清单/映射表口径）
_MATERIAL_PROCESS = {
    MAT_SAFETY: ("PCP安装-安装标准", "项目整体"),
    MAT_MOBILIZE: ("全局", "项目整体"),
    MAT_CABLE: ("光纤接续", "光缆路由"),
    MAT_POLE_7M_4IN: ("架空光缆配套施工", "架空杆路"),
    MAT_POLE_9M_4IN: ("架空光缆配套施工", "架空杆路"),
    MAT_POLE_7M_3IN: ("架空光缆配套施工", "架空杆路"),
    MAT_POLE_7M_25IN: ("架空光缆配套施工", "架空杆路"),
    MAT_FDT_72: ("PCP安装-安装标准；光纤接续", "PCP"),
    MAT_BOX_16: ("电缆端接；光纤接续", "光箱"),
    MAT_SPLICING: ("光纤接续", "接续点"),
    MAT_CABLE_LABEL: ("人孔内光缆备件管理", "光缆路由"),
    MAT_FDT_LABEL: ("PCP安装-安装标准", "PCP"),
    MAT_FAT_LABEL: ("电缆端接", "光箱"),
    MAT_POLE_LABEL: ("架空光缆配套施工", "架空杆路"),
    MAT_HANGER: ("光纤接续", "光缆路由"),
    MAT_STEEL_WIRE: ("光纤接续", "架空杆路"),
    MAT_TEST: ("光学测试", "PCP/光箱"),
    MAT_PERMIT: ("前置", "光缆路由"),
}

_MATERIAL_NAMES = {
    MAT_SAFETY: ("安全防护与准备", "PC"),
    MAT_MOBILIZE: ("运输、进场与退场", "PC"),
    MAT_CABLE: ("ADSS光缆24芯", "KM"),
    MAT_POLE_7M_4IN: ("7m电杆4英寸直径", "PC"),
    MAT_POLE_9M_4IN: ("9m单电杆4英寸直径", "PC"),
    MAT_POLE_7M_3IN: ("7m电杆3英寸直径", "PC"),
    MAT_POLE_7M_25IN: ("7m电杆2.5英寸直径", "PC"),
    MAT_FDT_72: ("72芯杆式光纤配线终端(FDT)", "PC"),
    MAT_BOX_16: ("16口杆式光箱", "PC"),
    MAT_SPLICING: ("光纤熔接", "PC"),
    MAT_CABLE_LABEL: ("光缆标签", "PC"),
    MAT_FDT_LABEL: ("FDT标签", "PC"),
    MAT_FAT_LABEL: ("FAT标签含二维码", "PC"),
    MAT_POLE_LABEL: ("电杆标签", "PC"),
    MAT_HANGER: ("电缆吊架/固定夹板/电缆挂钩", "PC"),
    MAT_STEEL_WIRE: ("6mm钢绞线", "M"),
    MAT_TEST: ("OTDR & OPM测试", "PC"),
    MAT_PERMIT: ("RT/RW许可", "M"),
    MAT_PROJECT_MGMT: ("项目管理", "M"),
    MAT_WAREHOUSE: ("仓储管理", "PC"),
    MAT_SURVEY: ("勘察与设计", "M"),
    MAT_ASBUILT: ("竣工图A1", "PC"),
}


def _num(v, default=0.0) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return default


def _obj_field(obj: dict, *names) -> str:
    for n in names:
        v = obj.get(n)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _is_reuse(obj: dict, params: dict) -> bool:
    flag = params.get("reuse", {}).get("flag_field", "reuse")
    v = str(obj.get(flag) or obj.get("reuse") or "").strip().upper()
    return v in ("YES", "Y", "OUI", "1", "TRUE", "利旧")


def _pole_material(ptech: dict) -> str:
    """按电杆高度/类型映射 4 类电杆物料（映射表 9-12 行）。"""
    h = _obj_field(ptech, "hauteur_appui", "hauteur", "height")
    t = _obj_field(ptech, "type", "TYPE")
    if "9" in h:
        return MAT_POLE_9M_4IN
    if "3" in t or "3 inch" in t.lower():
        return MAT_POLE_7M_3IN
    if "2.5" in t or "2.5 inch" in t.lower():
        return MAT_POLE_7M_25IN
    return MAT_POLE_7M_4IN


def _box_material(boite: dict) -> str:
    """按容量映射箱体：容量≥72 → FDT(500002054)，否则 16口光箱(500002142)。"""
    cap = _num(boite.get("capacite"))
    t = _obj_field(boite, "type", "TYPE")
    if cap >= 72 or "FDT" in t.upper() or "72" in t:
        return MAT_FDT_72
    return MAT_BOX_16


def build_bom(engineering_data: dict, params: dict = None) -> dict:
    """输入 engineering_data（含 objects），输出标准 BOM 行列表与汇总。

    返回 {success, project_id, bom_items, summary}。
    bom_items 每行含 规则编号/物料编码/物料名称/规格型号/单位/设计数量/损耗数量/预留数量/
    最终数量/对应设计对象/计算方式/计算依据/置信状态/数据来源。
    """
    if params is None:
        params = load_business_params()
    objects = (engineering_data or {}).get("objects") or {}
    cables = objects.get("cable") or []
    boites = objects.get("boite") or []
    ptechs = objects.get("ptech") or []

    source = params.get("_meta", {}).get("source", "待官方确认")
    items: List[dict] = []
    pending_official: List[str] = list(params.get("_meta", {}).get("official_pending", []) or [])
    rule_seq = 0

    def add(material_code: str, design_qty: float, counts: dict, ref: str,
            calc_note: str, unit: str = None, confirm: str = "自动匹配"):
        nonlocal rule_seq
        rule_seq += 1
        name, default_unit = _MATERIAL_NAMES.get(material_code, (material_code, "PC"))
        u = unit or default_unit
        # 电杆/箱体/标签/测试等按件物料不参与长度损耗/预留公式；光缆/钢绞线走公式
        if material_code in (MAT_CABLE, MAT_STEEL_WIRE):
            calc = compute_bom_quantity(material_code, design_qty, counts, params, unit=u)
            loss_qty, reserve_qty = calc["loss"], calc["reserve"]
            final_qty = calc["final"]
            detail = calc["detail"]
        else:
            loss_qty, reserve_qty = 0.0, 0.0
            final_qty = float(design_qty)
            detail = f"{calc_note}；按件/按点计量，不取整" if calc_note else "按件/按点计量，不取整"
        process, location = _MATERIAL_PROCESS.get(material_code, ("待确认", "待确认"))
        items.append({
            "规则编号": f"BOM-B{rule_seq:02d}",
            "对应工序": process,
            "使用位置": location,
            "物料编码": material_code,
            "物料名称": name,
            "规格型号": _MATERIAL_NAMES.get(material_code, ("", ""))[0],
            "单位": u,
            "设计数量": round(design_qty, 6),
            "损耗数量": round(loss_qty, 6),
            "预留数量": round(reserve_qty, 6),
            "最终数量": round(final_qty, 6),
            "对应设计对象": ref,
            "计算方式": calc_note,
            "计算依据": detail,
            "置信状态": confirm,
            "数据来源": f"{calc_note}｜{source}",
        })

    # 全局工程固定项（每项目 1 次）
    add(MAT_SAFETY, 1.0, {}, "项目整体", "每项目1次")
    add(MAT_MOBILIZE, 1.0, {}, "项目整体", "每项目1次")
    add(MAT_PROJECT_MGMT, 1.0, {}, "项目整体", "每项目1次")
    add(MAT_WAREHOUSE, 1.0, {}, "项目整体", "每项目1次")
    add(MAT_SURVEY, 1.0, {}, "项目整体", "每项目1次")
    add(MAT_ASBUILT, 1.0, {}, "项目整体", "每项目1次")

    # 光缆：净量=各缆 longueur 之和（KM）
    total_cable_km = sum(_num(c.get("longueur")) for c in cables)
    n_splice = sum(1 for c in cables if _obj_field(c, "extremite", "EXTREMITE"))
    zero_len = [c for c in cables if _num(c.get("longueur")) <= 0]  # 长度零值/缺失（2026-08-23，评测 TC-14）
    cable_confirm = "待人工确认" if zero_len else "自动匹配"
    cable_note = "光缆长度累加→损耗→预留→2KM/盘取整"
    if zero_len:
        cable_note += f"；{len(zero_len)}条光缆长度零值/缺失，数量待人工确认"
    if total_cable_km > 0 or zero_len:
        # 弯曲增长按 YD/T 5102-2024 表4：默认管道 10‰（可扩展按敷设方式细分）
        counts = {"splice": n_splice, "pole": len(ptechs), "endpoint": len(boites) + 1,
                  "bend_permille": 10}
        add(MAT_CABLE, total_cable_km, counts, f"{len(cables)}条光缆", cable_note, confirm=cable_confirm)
    if total_cable_km > 0 or zero_len:
        # 钢绞线：架空光缆配套，按光缆长度（M），500m/卷取整
        add(MAT_STEEL_WIRE, total_cable_km * 1000.0, {}, f"{len(cables)}条光缆",
            cable_note, unit="M", confirm=cable_confirm)

    # 电杆：按高度/类型映射，利旧冲减（reuse=yes 不新建）
    pole_groups: Dict[str, int] = {}
    pole_reused: Dict[str, int] = {}
    for pt in ptechs:
        m = _pole_material(pt)
        pole_groups[m] = pole_groups.get(m, 0) + 1
        if _is_reuse(pt, params):
            pole_reused[m] = pole_reused.get(m, 0) + 1
    for m, total in pole_groups.items():
        reused = pole_reused.get(m, 0)
        new_qty = max(0, total - reused)
        note = f"设计{total}根" + (f"，利旧冲减{reused}根" if reused else "")
        confirm = "自动匹配" if reused == 0 else "待人工确认"
        add(m, new_qty, {}, f"{total}根电杆", note, confirm=confirm)

    # 箱体：按容量映射 FDT/16口，利旧冲减
    box_groups: Dict[str, int] = {}
    box_reused: Dict[str, int] = {}
    for b in boites:
        m = _box_material(b)
        box_groups[m] = box_groups.get(m, 0) + 1
        if _is_reuse(b, params):
            box_reused[m] = box_reused.get(m, 0) + 1
    for m, total in box_groups.items():
        reused = box_reused.get(m, 0)
        new_qty = max(0, total - reused)
        note = f"设计{total}个" + (f"，利旧冲减{reused}个" if reused else "")
        confirm = "自动匹配" if reused == 0 else "待人工确认"
        add(m, new_qty, {}, f"{total}个箱体", note, confirm=confirm)

    # 熔接：按接续点数（简化：每 PCP 4 芯熔接 + 直通，口径待官方确认）
    n_fdt = box_groups.get(MAT_FDT_72, 0)
    n_box = box_groups.get(MAT_BOX_16, 0)
    n_pcp = n_fdt + n_box
    splice_cores = params.get("fiber_policy", {}).get("splice_cores_per_pcp", 4)
    if n_pcp > 0:
        add(MAT_SPLICING, n_pcp * splice_cores, {}, f"{n_pcp}个PCP",
            f"每PCP熔接{splice_cores}芯（口径待官方确认）", confirm="待人工确认")

    # 标签
    if len(cables) > 0:
        add(MAT_CABLE_LABEL, len(cables), {}, f"{len(cables)}条光缆", "每条光缆1张")
    if n_fdt > 0:
        add(MAT_FDT_LABEL, n_fdt, {}, f"{n_fdt}个FDT", "每个FDT1张")
    if n_box > 0:
        add(MAT_FAT_LABEL, n_box, {}, f"{n_box}个光箱", "每个光箱1张")
    if ptechs:
        add(MAT_POLE_LABEL, len(ptechs), {}, f"{len(ptechs)}根电杆", "每杆1张")

    # 吊架/挂钩：架空光缆配套（数量口径待官方确认，标记待人工确认）
    if total_cable_km > 0:
        add(MAT_HANGER, len(cables), {}, f"{len(cables)}条光缆",
            "吊架数量口径待官方确认", confirm="待人工确认")

    # 测试：按光箱/接头点数（每 PCP 1 点，口径待官方确认）
    if n_pcp > 0:
        add(MAT_TEST, n_pcp, {}, f"{n_pcp}个PCP",
            "按光箱/接头点数（口径待官方确认）", confirm="待人工确认")

    # 施工许可：按架空光缆长度（M，口径待官方确认）
    if total_cable_km > 0:
        add(MAT_PERMIT, total_cable_km * 1000.0, {}, "架空光缆",
            "按长度计量（口径待官方确认）", unit="M", confirm="待人工确认")

    confirm_count = sum(1 for it in items if it["置信状态"] != "自动匹配")
    return {
        "success": True,
        "project_id": (engineering_data or {}).get("project_id", ""),
        "bom_items": items,
        "summary": {
            "total_items": len(items),
            "confirm_count": confirm_count,
            "total_cable_km": round(total_cable_km, 6),
            "pole_count": len(ptechs),
            "box_count": len(boites),
            "pending_official": pending_official,
        },
    }
