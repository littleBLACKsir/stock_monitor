from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ActionLiteral = Literal["观望", "观察", "满足条件可小仓试错", "不符合策略"]
ConfidenceLiteral = Literal["unknown", "low", "medium", "high"]


class ScoreComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_value: float | None = None
    score: float = Field(ge=-100, le=100)
    normalized_score: float = Field(ge=-1, le=1)
    weight: float = Field(ge=0, le=1)
    explanation: str


class ConfirmationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    raw_value: dict[str, Any]
    threshold: dict[str, Any]
    explanation: str


class RelativeStrengthResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmark: str
    benchmark_name: str | None = None
    return_diff_5d: float | None = None
    return_diff_20d: float | None = None
    ratio_vs_ma10: float | None = None
    signal: str


class UniverseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    universe_type: str
    sector: str
    subsector: str
    role: str
    passed_hard_filters: bool
    suggestion: str
    reasons: list[str]
    validation_flags: list[str] = Field(default_factory=list)
    metrics: dict[str, Any]


class DataStandardMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frequency: str
    adjust: str
    price_field: str
    benchmark_price_field: str
    data_source_status: str
    validation_notes: list[str] = Field(default_factory=list)


class AgentMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    vendor: str
    model: str
    toolchain: str
    run_id: str


class ReportMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    generated_at: str
    agent: AgentMeta
    theme: str
    market_regime: str
    macro_score: float | None = None
    data_standard: DataStandardMeta
    warnings: list[str] = Field(default_factory=list)


class ModelRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overfitting_risk_notes: list[str] = Field(default_factory=list)


class StockAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    universe_type: str
    sector: str
    subsector: str
    role: str
    benchmark: str
    benchmark_name: str | None = None
    oversold_score_total: float = Field(ge=0, le=100)
    oversold_components: dict[str, ScoreComponent]
    confirmation_pass: bool
    confirmations: dict[str, ConfirmationResult]
    relative_strength: RelativeStrengthResult
    risk_flags: list[str] = Field(default_factory=list)
    action: ActionLiteral
    invalidation_conditions: list[str] = Field(default_factory=list)
    confidence: ConfidenceLiteral = "unknown"
    notes: list[str] = Field(default_factory=list)
    data_quality: dict[str, Any] = Field(default_factory=dict)
    tradeability: dict[str, Any] = Field(default_factory=dict)
    pre_trade_checklist: dict[str, Any] = Field(default_factory=dict)
    trade_plan: dict[str, Any] = Field(default_factory=dict)


class AnalysisPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: ReportMeta
    model_risk: ModelRisk
    universe: list[UniverseResult]
    per_stock: list[StockAnalysis]
    summary: dict[str, Any]


class ConsensusItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    sector: str
    consensus_action: str
    positive_votes: int
    negative_votes: int
    exact_match_count: int
    participants: list[str]
    agreement_score: float = Field(ge=0, le=100)
    disagreement_reasons: list[str] = Field(default_factory=list)


class DivergenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    sector: str
    actions: dict[str, str]
    agreement_score: float = Field(ge=0, le=100)
    disagreement_reasons: list[str]


class ConsensusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: dict[str, Any]
    consensus: list[ConsensusItem]
    divergences: list[DivergenceItem]
    summary: dict[str, Any]


def validate_analysis_payload(payload: dict[str, Any]) -> AnalysisPayload:
    return AnalysisPayload.model_validate(payload)


def validate_consensus_payload(payload: dict[str, Any]) -> ConsensusPayload:
    return ConsensusPayload.model_validate(payload)
