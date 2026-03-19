from typing import List
from pydantic import BaseModel, Field


class OutputRequirements(BaseModel):
    requirements: List[str] = Field(..., description="Список требований", max_length=500)