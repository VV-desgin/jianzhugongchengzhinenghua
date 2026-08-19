"""BOM 确定性公式：净量 → 损耗 → 预留 → 包装取整。

口径来源：《问题清单——我方解决方案（详细版）》统一 BOM 公式；
数值默认值见 business_params.json（source=行业参考默认值，待官方确认）。
"""
import math
from typing import Dict

from .business_params import load_business_params


def _num(v, default=0.0) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return default


def apply_loss(net_qty: float, material_code: str, params: dict) -> tuple:
    cfg = params.get("loss_rates", {}).get(str(material_code))
    rate = _num(cfg.get("rate")) if isinstance(cfg, dict) else 0.0
    loss = net_qty * rate
    return loss, f"损耗率 {rate:.0%}"


def apply_reserve_m(counts: dict, params: dict, net_qty: float = None) -> tuple:
    r = params.get("reserve_lengths", {})
    parts = []
    total = 0.0
    pcp = _num(counts.get("pcp"))
    if pcp:
        v = _num(r.get("pcp_joint_m"), 1.35) * pcp
        total += v
        parts.append(f"{pcp:g}个PCP盒内余长{v:g}m")
    splice = _num(counts.get("splice"))
    if splice:
        v = _num(r.get("splice_per_side_m"), 7.5) * 2 * splice
        total += v
        parts.append(f"{splice:g}个接头每侧盘留{v:g}m")
    manhole = _num(counts.get("manhole"))
    if manhole:
        v = _num(r.get("manhole_m"), 0.75) * manhole
        total += v
        parts.append(f"{manhole:g}处人孔盘留{v:g}m")
    pole = _num(counts.get("pole"))
    if pole:
        v = _num(r.get("pole_m"), 7.5) * pole
        total += v
        parts.append(f"{pole:g}根电杆上下杆预留{v:g}m")
    endpoint = _num(counts.get("endpoint"))
    if endpoint:
        # YD/T 5102-2024 表4：交接箱/分纤箱/终端盒处预留 1~3m（取中值 2.0）
        v = _num(r.get("endpoint_m"), 2.0) * endpoint
        total += v
        parts.append(f"{endpoint:g}处分纤箱/终端盒预留{v:g}m")
    # 光缆弯曲增长（YD/T 5102-2024 表4：直埋 7‰、管道 10‰、架空 7~10‰）
    bend_permille = _num(counts.get("bend_permille"))
    if bend_permille > 0 and net_qty is not None and net_qty > 0:
        v = net_qty * bend_permille / 1000.0
        total += v
        parts.append(f"弯曲增长 {bend_permille:g}‰ × {net_qty:g}{'KM' if net_qty < 1000 else 'm'}")
    return total, "；".join(parts) if parts else "无预留场景"


def apply_packaging(qty: float, material_code: str, params: dict, unit: str = "KM") -> tuple:
    cfg = params.get("packaging", {}).get(str(material_code), {})
    mode = cfg.get("round", "ceil") if isinstance(cfg, dict) else "ceil"
    if mode == "exact":
        return qty, "按实际数量，不取整"
    pack = _num(cfg.get("pack"))
    if pack > 0:
        n = int(math.ceil(qty / pack))
        final = n * pack
        return final, f"{qty:g}{unit} → {n}×{pack:g}{unit} = {final:g}{unit}"
    final = float(math.ceil(qty))
    return final, f"按整数向上取整 {qty:g} → {final:g}"


def compute_bom_quantity(material_code: str, net_qty: float, counts: Dict,
                         params: dict = None, unit: str = "KM") -> dict:
    if params is None:
        params = load_business_params()
    net = _num(net_qty)
    loss, loss_desc = apply_loss(net, material_code, params)
    reserve_m, reserve_desc = apply_reserve_m(counts or {}, params, net_qty=net)
    reserve = reserve_m / 1000.0 if unit == "KM" else reserve_m
    before = net + loss + reserve
    final, pack_desc = apply_packaging(before, material_code, params, unit)
    source = params.get("_meta", {}).get("source", "待官方确认")
    return {
        "net": round(net, 6),
        "loss": round(loss, 6),
        "reserve": round(reserve, 6),
        "before_pack": round(before, 6),
        "final": round(final, 6),
        "unit": unit,
        "detail": f"{loss_desc}；预留：{reserve_desc}；取整：{pack_desc}",
        "source": source,
    }
