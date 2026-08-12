import yaml
import importlib.resources
from pathlib import Path
from typing import List, Dict, Any, Optional, Type
from pydantic import BaseModel
from .feature import UnifiedFeature
from . import models
from .utils import convert_coords

class LayerAdapter:
    def __init__(self, config_path: Optional[Path] = None):
        if config_path:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
        else:
            yaml_text = importlib.resources.read_text('design_parser.mappings', 'layer_mapping.yaml')
            self.config = yaml.safe_load(yaml_text)
        self.null_values = set(self.config.get('null_values', []))
        self.target_crs = self.config['target_crs']

    def convert_layer(self, features: List[UnifiedFeature], layer_name: str) -> List[Any]:
        layer_config = self._get_layer_config(layer_name)
        if not layer_config:
            return features

        target_entity = getattr(models, layer_config['target_entity'])
        field_map = layer_config['field_map']
        type_conversions = layer_config.get('type_conversions', {})

        result = []
        for feat in features:
            try:
                obj = self._convert_feature(feat, target_entity, field_map, type_conversions)
                if obj:
                    result.append(obj)
            except Exception as e:
                pass
        return result

    def _get_layer_config(self, layer_name: str) -> dict:
        # 精确匹配
        for key, cfg in self.config['layers'].items():
            if key.upper() == layer_name.upper():
                return cfg
        # 包含匹配
        for key, cfg in self.config['layers'].items():
            if key.upper() in layer_name.upper():
                return cfg

        # 硬编码 fallback：保证 CABLE 和 BOX 等总能转换
        if "CABLE" in layer_name.upper():
            return {
                "target_entity": "Cable",
                "field_map": {
                    "id": ["CODE"],
                    "code": ["CODE"],
                    "capacity": ["CAPACITE"],
                    "length": ["LGR_REELLE", "LGR_CARTO"],
                    "start_device": ["ORIGINE"],
                    "end_device": ["EXTREMITE"],
                    "geometry": None,
                },
                "code_field": "CODE"
            }
        if "BOX" in layer_name.upper() or "BOITE" in layer_name.upper() or "BPE" in layer_name.upper():
            return {
                "target_entity": "Box",
                "field_map": {
                    "id": ["CODE"],
                    "code": ["CODE"],
                    "type": ["TYPE_FONC", "FONCTION"],
                    "capacity": ["CAPACITE"],
                    "location": None,
                    "geometry": None,
                },
                "code_field": "CODE"
            }
        if "ZNRO" in layer_name.upper():
            return {
                "target_entity": "Znro",
                "field_map": {
                    "id": ["fid"],
                    "code": ["CODE"],
                    "ref_plaque": ["REF_PLAQUE"],
                    "ref_nro": ["REF_NRO"],
                    "statut": ["STATUT"],
                    "nb_prises": ["NB_PRISES"],
                    "geometry": None,
                },
                "type_conversions": {"nb_prises": "int"},
                "code_field": "CODE"
            }
        if "ZPM" in layer_name.upper():
            return {
                "target_entity": "Zpm",
                "field_map": {
                    "id": ["fid"],
                    "code": ["CODE"],
                    "ref_plaque": ["REF_PLAQUE"],
                    "ref_nro": ["REF_NRO"],
                    "ref_sro": ["REF_SRO"],
                    "statut": ["STATUT"],
                    "nb_prises": ["NB_PRISES"],
                    "geometry": None,
                },
                "type_conversions": {"nb_prises": "int"},
                "code_field": "CODE"
            }
        return None

    def _convert_feature(self, feat: UnifiedFeature, model_cls: Type[BaseModel],
                         field_map: dict, type_conversions: dict) -> Optional[BaseModel]:
        props = feat.properties
        init_data = {}
        for target_field, source_fields in field_map.items():
            if source_fields is None:
                if target_field == 'geometry':
                    init_data['geometry'] = feat._geometry
                elif target_field == 'location':
                    init_data['location'] = feat._geometry
                continue
            value = self._extract_value(props, source_fields)
            if value in self.null_values:
                value = None
            if value is not None and target_field in type_conversions:
                value = self._convert_type(value, type_conversions[target_field])
            init_data[target_field] = value

        init_data['id'] = str(init_data.get('id', feat.feature_id))
        init_data['properties'] = props
        init_data['source_layer'] = feat.source_layer_name

        # CRS 坐标重投影（自适应：如果数据CRS与目标不一致，自动以数据CRS为准）
        geometry = init_data.get('geometry')
        original_crs = getattr(feat, 'original_crs', None)
        if geometry is not None and original_crs:
            if original_crs != self.target_crs:
                # 检查数据CRS是否常见（EPSG:4326, 26191等），若是则以数据CRS为主
                common_crs_list = ['EPSG:4326', 'EPSG:26191', 'EPSG:3857', 'EPSG:4269', 'EPSG:2154']
                data_is_common = any(crs in str(original_crs).upper() for crs in common_crs_list)
                if data_is_common:
                    # 数据CRS常见且明确，保留原始坐标系，不强制重投影
                    pass  # 保持几何不变
                else:
                    init_data['geometry'] = convert_coords(geometry, original_crs, self.target_crs)

        return model_cls(**init_data)

    def _extract_value(self, props: dict, candidate_fields: List[str]) -> Any:
        for field in candidate_fields:
            if field in props:
                return props[field]
        return None

    def _convert_type(self, value: Any, target_type: str) -> Any:
        try:
            if target_type == 'int':
                return int(float(value))
            elif target_type == 'float':
                return float(value)
            elif target_type == 'str':
                return str(value)
        except (ValueError, TypeError):
            pass
        return value  # 转换失败保留原始值