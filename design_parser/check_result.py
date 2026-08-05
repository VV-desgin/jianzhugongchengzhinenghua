# design_parser/check_result.py
from pydantic import BaseModel, Field
from typing import Optional

class CheckResult(BaseModel):
    check_object: str = Field(description="检查对象，如'图层 boite 第3条记录'")
    passed: bool = Field(description="是否通过")
    problem_location: Optional[str] = Field(None, description="问题位置，如'字段 CODE'")
    actual_value: Optional[str] = Field(None, description="实际值")
    expected_value: Optional[str] = Field(None, description="标准值/期望值")
    rule_id: str = Field(description="规则编号，如'R001'")
    error_description: Optional[str] = Field(None, description="错误说明")
    severity: Optional[str] = Field(None, description="严重性：fatal(阻断)/error(严重)/warning(警告)")
