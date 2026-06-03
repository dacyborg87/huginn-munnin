from pydantic import BaseModel, Field


class SecurityAnalysisRequest(BaseModel):
    content: str = Field(min_length=1)
    source: str = "manual"


class SecurityAnalysisResponse(BaseModel):
    summary: str
    severity: str
    findings: list[str]
    mapped_tactics: list[str]
    recommendations: list[str]
