from typing import List, Literal, Optional
from pydantic import BaseModel, Field

System = Literal['Roofing','Electrical','Plumbing','HVAC','Structure','Exterior','Interior','Other']
Priority = Literal['Safety','Urgent','Planned','Cosmetic']

class Finding(BaseModel):
    """The model supplies observations, never priorities, prices or workflow decisions."""
    system: System
    location: str
    title: str
    description: str
    page: int = Field(ge=1)
    evidence: str = Field(min_length=12)
    report_reference: str
    kind: Literal['observed_defect','limitation','informational']
    inspector_recommendation: str
    inspector_severity: str

class Extraction(BaseModel):
    findings: List[Finding]

class Review(BaseModel):
    expected_revision: int = Field(ge=0)
    decision: Literal['pending','accepted','rejected']
    note: str = Field(default='',max_length=2000)
    title: Optional[str] = Field(default=None,min_length=1,max_length=300)
    description: Optional[str] = Field(default=None,min_length=1,max_length=4000)
    location: Optional[str] = Field(default=None,min_length=1,max_length=300)
    priority: Optional[Priority] = None
    kind: Optional[Literal['observed_defect','limitation','informational']] = None
