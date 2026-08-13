# engineering_data 字段说明

来源：design_parser/project_data.py ENGINEERING_OBJECTS + 赛题四实测

> 说明：本文档兼作 P1 验收的 engineering_data 字段核对表。

| 对象 | 输出字段 | 源字段映射（按序取首个非空） | 实测样例（赛题四） | 缺失时行为 | 实测核对结论 |
|---|---|---|---|---|---|
| cable | code | CODE, CABLE_CODE | CDI-JAD-MAR-01-0001 | 有 | 有值且映射正确 |
| cable | longueur | LONGUEUR, LGR_REELLE, LGR_CARTO | 13.47（米） | 有 | 有值且映射正确 |
| cable | capacite | CAPACITE, CAPACITY, FIBER_COUNT | 24 | 有 | 有值且映射正确 |
| cable | type | TYPE_CABLE, TYPE | DISTRIBUTION | 有 | 有值且映射正确 |
| cable | nb_fibre_util | NB_FIBRE_U, NB_FIBRE_UTIL, NB_FIBRE_D | 10 | 有 | 有值且映射正确 |
| cable | hauteur_appui | - | - | 源数据无此字段，不输出 | 符合：源数据缺字段/缺值，正确不输出 |
| boite | code | CODE, BOITE_CODE, ID | BPE-JAD-MAR-1021 | 有 | 有值且映射正确 |
| boite | longueur | - | - | 源数据无此字段，不输出 | 符合：源数据缺字段/缺值，正确不输出 |
| boite | capacite | CAPACITE, CAPACITY | 72 | 有 | 有值且映射正确 |
| boite | type | TYPE, TYPE_BOITE, BOXTYPE, TYPE_FONC, FONCTION | BPE | 有 | 有值且映射正确 |
| boite | nb_fibre_util | NB_FIBRE_U, NB_FIBRE_UTIL, NBFUTILE | 10 | 有 | 有值且映射正确 |
| boite | hauteur_appui | HAUTEUR_AP, HAUTEUR_APPUI, HAUTEUR | - | 源数据无值，不输出 | 符合：源数据缺字段/缺值，正确不输出 |
| ptech | code | CODE, PTECH_CODE | IAM-CHA-001 | 有 | 有值且映射正确 |
| ptech | longueur | - | - | 源数据无此字段，不输出 | 符合：源数据缺字段/缺值，正确不输出 |
| ptech | capacite | CAPACITE, CAPACITY | - | 源数据无值，不输出 | 符合：源数据缺字段/缺值，正确不输出 |
| ptech | type | TYPE | CHAMBRE | 有 | 有值且映射正确 |
| ptech | nb_fibre_util | NB_FIBRE_U, NB_FIBRE_UTIL | - | 源数据无值，不输出 | 符合：源数据缺字段/缺值，正确不输出 |
| ptech | hauteur_appui | HAUTEUR_AP, HAUTEUR_APPUI | 0 | 有（0 视为有效值） | 有值且映射正确 |

- 输出顶层结构：`{project_id, project_type, objects:{cable,boite,ptech,site,infrastructure}}`；每个对象带唯一 `id`（如 `cable:CDI-JAD-MAR-01-0001`）。
- 包内含纤芯表（纤芯连接与分配 / SRO TOPO / 单箱页）时，额外输出 `fiber_tables`（`[{file, sheet, headers, rows}]`），供 Dify 纤芯分配工具 V0.5 做重复占用检查。
- 字段值均为 None 时不写入 JSON（源数据缺字段/缺值则不出现该键）。

## 核对结论

核对样本：赛题四-摩洛哥.rar（822 对象）+ TC-01_正确工程案例.xlsx；逐字段核对全部通过，无字段错映射；缺失字段/缺值行为与设计一致。
