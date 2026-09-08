from pydantic import BaseModel
from typing import List, Optional, Any

class ApiResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[Any] = None  # 字符串或结构化 {code, message}

class CheckResultOut(BaseModel):
    check_object: str
    passed: bool
    problem_location: Optional[str] = None
    actual_value: Optional[str] = None
    expected_value: Optional[str] = None
    rule_id: str
    error_description: Optional[str] = None
    severity: Optional[str] = None

class RunRulesRequest(BaseModel):
    rule_ids: Optional[List[str]] = None   # None 或空列表表示全部
    params: Optional[dict] = None           # 规则参数，如 {"R002": {"required_layers": ["boite"]}}

class HealthResponse(BaseModel):
    """GET /health 健康检查响应。"""
    status: str

class DataPipelineResponse(BaseModel):
    """POST /agent/data-pipeline 响应契约（含 request_id 对账字段）。"""
    success: bool
    request_id: str
    project_id: str
    project_name: str
    project_type: str
    summary: dict
    review: dict
    warnings: list
    errors: list
    status: str
    file_info: dict
    layers: list
    review_results: list
    serious_issues_detected: bool
    excel_data: dict
    pdf_text: dict
    engineering_data: dict
    bom_tables: Optional[dict] = None
    fiber_tables: Optional[dict] = None
    review_scope: Optional[str] = None
    skipped_gis_rules: Optional[list] = None
    review_message: Optional[str] = None
    business_params: Optional[dict] = None
    stage_results: Optional[dict] = None

class BusinessParamsOut(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[dict] = None
