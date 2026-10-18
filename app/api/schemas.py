"""Request and response models of the public API."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class TravelRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def strip_message(self) -> "TravelRequest":
        self.message = self.message.strip()
        if not self.message:
            raise ValueError("Message cannot be empty.")
        return self


class ApprovalRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=100)
    approved: bool
    feedback: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def require_feedback_on_rejection(self) -> "ApprovalRequest":
        if not self.approved and not self.feedback.strip():
            raise ValueError("Please provide revision feedback when rejecting the draft.")
        return self


class TravelResponse(BaseModel):
    success: Literal[True] = True
    thread_id: str
    status: Literal["awaiting_approval", "completed"]
    requires_approval: bool
    answer: str
    approval_request: str = ""
    itinerary: str = ""
    flight_results: str = ""
    hotel_results: str = ""
    weather_results: str = ""
    budget_results: str = ""
    selected_agents: list[str] = []
    trip_constraints: dict[str, Any] = {}
    supervisor_reasoning: str = ""
    guardrail_allowed: bool = True
    guardrail_reason: str = ""
    approved: bool | None = None
    human_feedback: str = ""
    llm_calls: int = 0


class ErrorResponse(BaseModel):
    success: Literal[False] = False
    error: str
    code: str


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    checks: dict[str, str] = {}
