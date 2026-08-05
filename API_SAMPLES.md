# design_parser V0.2 ? API ????????????

> ? 2026-08-05 ???? / ???????????????????????????????

## engineering-data

```json
{
  "project_id": "7dcdbe8a",
  "project_type": "unknown",
  "objects": {
    "cable": [
      {
        "code": "CDI-JAD-MAR-01-0001",
        "longueur": 13.473601128875206,
        "capacite": 24,
        "type": "DISTRIBUTION",
        "nb_fibre_util": 10,
        "id": "cable:CDI-JAD-MAR-01-0001"
      }
    ],
    "boite": [
      {
        "code": "BPE-JAD-MAR-1021",
        "capacite": 72,
        "type": "BPE",
        "nb_fibre_util": 10,
        "id": "boite:BPE-JAD-MAR-1021"
      }
    ],
    "ptech": [
      {
        "code": "IAM-CHA-001",
        "type": "CHAMBRE",
        "hauteur_appui": 0,
        "id": "ptech:IAM-CHA-001"
      }
    ],
    "site": [
      {
        "code": "JAD-MAR1076",
        "type": "NRO",
        "id": "site:JAD-MAR1076"
      }
    ],
    "infrastructure": [
      {
        "code": "UNF-INF-0003",
        "longueur": 30.87194625126841,
        "type": "SOUTERRAIN",
        "id": "infrastructure:UNF-INF-0003"
      }
    ]
  },
  "counts": {
    "cable": 121,
    "boite": 118,
    "ptech": 141,
    "site": 3,
    "infrastructure": 193
  }
}
```

## relations

```json
{
  "cable_edges": [
    {
      "cable_code": "CDI-JAD-MAR-01-0001",
      "upstream": {
        "code": "BPE-JAD-MAR-1006",
        "layer": "BOITE",
        "distance_m": 0.0
      },
      "downstream": {
        "code": "PBO-JAD-MAR-0001",
        "layer": "BOITE",
        "distance_m": 0.0
      }
    }
  ],
  "unresolved_refs": [],
  "distance_stats": {
    "count": 240,
    "min_m": 0.0,
    "median_m": 0.0,
    "max_m": 0.0
  }
}
```

## gis-check

```json
{
  "total": 2,
  "counts": {
    "R-GIS-004": 2
  },
  "issues": [
    {
      "rule_id": "R-GIS-004",
      "object_type": "CABLE",
      "object_id": "CDI-JAD-MAR-02-0046",
      "field": "",
      "severity": "高",
      "message": "CABLE CDI-JAD-MAR-02-0046 存在点位（2 个）超出归属 ZPM JAD-MAR-0002 范围",
      "source": "gis_rules"
    },
    {
      "rule_id": "R-GIS-004",
      "object_type": "CABLE",
      "object_id": "CDI-JAD-MAR-02-0052",
      "field": "",
      "severity": "高",
      "message": "CABLE CDI-JAD-MAR-02-0052 存在点位（2 个）超出归属 ZPM JAD-MAR-0002 范围",
      "source": "gis_rules"
    }
  ]
}
```

## safety-check

```json
{
  "total": 0,
  "counts": {},
  "skipped_sample": [
    "光缆 CDI-JAD-MAR-01-0001：二维数据无 Z，无法检查离地高度"
  ],
  "skipped_count": 120
}
```

## rule-library

```json
{
  "file": "图层表字段说明和数据校验规则.xlsx",
  "validation_rules": 39,
  "layers": [
    "BOITE",
    "CABLE",
    "INFRASTRUCTURE",
    "PTECH",
    "SITE",
    "ZNRO",
    "ZPM",
    "IMB"
  ],
  "executable_rules": 400
}
```

## unrecognized-fields

```json
{
  "count": 138,
  "fields": [
    {
      "layer": "BOITE",
      "field": "ADRESSSE",
      "suggested_standard_field": null,
      "suggestion_source": null,
      "suggestion_confidence": null,
      "known_official_field": true,
      "note": "官方字段清单或 field_lengths 已登记，但尚未加入 field_map；建议补充映射"
    },
    {
      "layer": "BOITE",
      "field": "CABLE_AMON",
      "suggested_standard_field": null,
      "suggestion_source": null,
      "suggestion_confidence": null,
      "known_official_field": true,
      "note": "官方字段清单或 field_lengths 已登记，但尚未加入 field_map；建议补充映射"
    }
  ]
}
```

## bom-tables

```json
{
  "files": [
    {
      "file": "BOM_LIST.xlsx",
      "sheets": [
        {
          "name": "Sheet1",
          "row_count": 1048412
        },
        {
          "name": "Sheet2",
          "row_count": 1
        }
      ]
    },
    {
      "file": "material_code_20260519090241.xls",
      "sheets": [
        {
          "name": "data0",
          "row_count": 65536
        },
        {
          "name": "data1",
          "row_count": 2965
        }
      ]
    }
  ]
}
```

## fiber-tables

```json
{
  "workbooks": [
    "SRO-JAD-MAR-0001-TOPO_20251212-180459.xlsx",
    "SRO-JAD-MAR-0002-TOPO_20251212-180459.xlsx"
  ],
  "vectors": [
    {
      "file": "BOX.gpkg",
      "layer": "elj_qae_boite_optique",
      "count": 116
    },
    {
      "file": "CABLE.gpkg",
      "layer": "elj_qae_cable_optique",
      "count": 116
    }
  ]
}
```

## table-data

```json
{
  "file": "BOM_LIST.xlsx",
  "sheet": "Sheet1",
  "headers": [
    "物料编码\nmaterial code",
    "物料描述\nDescription",
    "厂家/类型\nManufacturer/type"
  ],
  "rows": [
    [
      500003800,
      "Pengamanan & Persiapan (Kesehatan dan Keselamatan Kerja)",
      "FH-FH",
      "PC",
      1,
      "Pengamanan & Persiapan (Kesehatan dan Keselamatan Kerja)"
    ],
    [
      500003890,
      "Transportasi, Mobilisasi & demobilisasi",
      "FH-FH",
      "PC",
      1,
      "Transportasi, Mobilisasi & demobilisasi"
    ]
  ],
  "total": 2,
  "page": 1,
  "page_size": 2
}
```

## procedure-kb

```json
{
  "file": "",
  "entries": []
}
```

