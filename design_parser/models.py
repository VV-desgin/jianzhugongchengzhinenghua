from pydantic import BaseModel, Field
from typing import Optional, Any

class Cable(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    id: str
    code: Optional[str] = None
    capacity: Optional[Any] = None
    length: Optional[float] = None
    start_device: Optional[str] = None
    end_device: Optional[str] = None
    geometry: Optional[Any] = None
    source_layer: Optional[str] = None
    properties: dict = Field(default_factory=dict)

class Box(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    id: str
    code: Optional[str] = None
    type: Optional[str] = None
    capacity: Optional[Any] = None
    location: Optional[Any] = None
    parent_device: Optional[str] = None
    geometry: Optional[Any] = None
    source_layer: Optional[str] = None
    properties: dict = Field(default_factory=dict)

class Infrastructure(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    id: str
    code: Optional[str] = None
    ref_plaque: Optional[str] = None
    origine: Optional[str] = None
    extremite: Optional[str] = None
    composition: Optional[str] = None
    type: Optional[str] = None
    type_log: Optional[str] = None
    statut: Optional[str] = None
    proprietaire: Optional[str] = None
    gestionnaire: Optional[str] = None
    longueur: Optional[float] = None
    geometry: Optional[Any] = None
    source_layer: Optional[str] = None
    properties: dict = Field(default_factory=dict)

class Znro(BaseModel):
    """NRO区域-多边形"""
    model_config = {"arbitrary_types_allowed": True}
    id: str
    code: Optional[str] = None
    ref_plaque: Optional[str] = None
    ref_nro: Optional[str] = None
    statut: Optional[str] = None
    nb_prises: Optional[int] = None
    geometry: Optional[Any] = None
    source_layer: Optional[str] = None
    properties: dict = Field(default_factory=dict)

class Zpm(BaseModel):
    """PM/SRO区域-多边形"""
    model_config = {"arbitrary_types_allowed": True}
    id: str
    code: Optional[str] = None
    ref_plaque: Optional[str] = None
    ref_nro: Optional[str] = None
    ref_sro: Optional[str] = None
    statut: Optional[str] = None
    nb_prises: Optional[int] = None
    geometry: Optional[Any] = None
    source_layer: Optional[str] = None
    properties: dict = Field(default_factory=dict)