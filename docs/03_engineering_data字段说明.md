# engineering_data 字段说明

生成：2026-08-08｜来源：design_parser/project_data.py ENGINEERING_OBJECTS + 赛题四实测

| 对象 | 输出字段 | 源字段映射（按序取首个非空） | 实测样例（赛题四） | 缺失时行为 |
|---|---|---|---|---|
| cable | code | CODE, CABLE_CODE | CDI-JAD-MAR-01-0001 | 有 |
| cable | longueur | LONGUEUR, LGR_REELLE, LGR_CARTO | 13.47（米） | 有 |
| cable | capacite | CAPACITE, CAPACITY, FIBER_COUNT | 24 | 有 |
| cable | type | TYPE_CABLE, TYPE | DISTRIBUTION | 有 |
| cable | nb_fibre_util | NB_FIBRE_U, NB_FIBRE_UTIL, NB_FIBRE_D | 10 | 有 |
| cable | hauteur_appui | - | - | 源数据无此字段，不输出 |
| boite | code | CODE, BOITE_CODE, ID | BPE-JAD-MAR-1021 | 有 |
| boite | longueur | - | - | 源数据无此字段，不输出 |
| boite | capacite | CAPACITE, CAPACITY | 72 | 有 |
| boite | type | TYPE, TYPE_BOITE, BOXTYPE, TYPE_FONC, FONCTION | BPE | 有 |
| boite | nb_fibre_util | NB_FIBRE_U, NB_FIBRE_UTIL, NBFUTILE | 10 | 有 |
| boite | hauteur_appui | HAUTEUR_AP, HAUTEUR_APPUI, HAUTEUR | - | 源数据无值，不输出 |
| ptech | code | CODE, PTECH_CODE | IAM-CHA-001 | 有 |
| ptech | longueur | - | - | 源数据无此字段，不输出 |
| ptech | capacite | CAPACITE, CAPACITY | - | 源数据无值，不输出 |
| ptech | type | TYPE | CHAMBRE | 有 |
| ptech | nb_fibre_util | NB_FIBRE_U, NB_FIBRE_UTIL | - | 源数据无值，不输出 |
| ptech | hauteur_appui | HAUTEUR_AP, HAUTEUR_APPUI | 0 | 有（0 视为有效值） |

- 输出顶层结构：`{project_id, project_type, objects:{cable,boite,ptech,site,infrastructure}}`；每个对象带唯一 `id`（如 `cable:CDI-JAD-MAR-01-0001`）。
- 字段值均为 None 时不写入 JSON（源数据缺字段/缺值则不出现该键）。