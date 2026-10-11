from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import section

SCHEMA_VERSION = 1
CORE_VERSION = "0.1.0"
DEFAULT_MODEL_ID = section("model")["id"]
DEFAULT_MODEL_REVISION = section("model")["revision"]


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ReadingSource(StrEnum):
    USER = "user_override"
    AGENT = "agent_override"
    RUBY = "explicit_ruby"
    MECAB = "mecab_unidic"
    FALLBACK = "local_fallback"
    DISPLAY_ONLY = "display_only"


class LineState(StrEnum):
    READY = "ready"
    STALE = "stale"
    ALIGNED = "aligned"
    STRUCTURAL_WARNING = "structural_warning"


class Span(StrictModel):
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def ordered(self) -> Span:
        if self.end < self.start:
            raise ValueError("span end must not precede start")
        return self


class DisplayToken(StrictModel):
    id: str
    text: str
    span: Span
    alignable: bool


class MoraToken(StrictModel):
    id: str
    kana: str
    romaji: str
    group_id: str
    display_token_id: str


class RubyGroup(StrictModel):
    id: str
    span: Span
    display_token_ids: list[str]
    display: str
    reading: str
    mora_ids: list[str]
    source: ReadingSource
    synthetic_breaks: list[int] = Field(default_factory=list)


class LyricLine(StrictModel):
    id: str
    source_index: int
    paragraph_before: int = 0
    original: str
    display_tokens: list[DisplayToken]
    ruby_groups: list[RubyGroup]
    moras: list[MoraToken]
    yohane_input: str
    state: LineState = LineState.READY
    warning_codes: list[str] = Field(default_factory=list)
    reference_time_ms: int | None = None

    @property
    def display_text(self) -> str:
        return "".join(token.text for token in self.display_tokens)


class SourceRecord(StrictModel):
    lyrics_path: str | None = None
    lyrics_format: Literal["txt", "lrc", "ass"] | None = None
    audio_path: str | None = None
    video_path: str | None = None
    legacy_parentheses_ruby: bool = False
    preserve_ass_timing: bool = False
    imported_at: datetime | None = None


class AudioRecord(StrictModel):
    original_sha256: str | None = None
    prepared_path: str | None = None
    prepared_sha256: str | None = None
    sample_rate: int = 16000
    channels: int = 1
    duration_ms: int | None = None


class ModelRecord(StrictModel):
    model_id: str = DEFAULT_MODEL_ID
    revision: str = DEFAULT_MODEL_REVISION
    license: str = "CC-BY-NC-SA-4.0"
    license_accepted_at: datetime | None = None
    resolved_snapshot: str | None = None
    checksums: dict[str, str] = Field(default_factory=dict)


class RawAlignedLine(StrictModel):
    line_id: str
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(ge=0)]
    k_values_cs: list[Annotated[int, Field(ge=0)]]
    labels: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_interval(self) -> RawAlignedLine:
        if self.end_ms < self.start_ms:
            raise ValueError("alignment line end precedes start")
        return self


class RawAlignment(StrictModel):
    cache_key: str
    created_at: datetime = Field(default_factory=utc_now)
    adapter_version: str
    model_id: str
    model_revision: str
    audio_sha256: str
    normalized_romaji_sha256: str
    lines: list[RawAlignedLine]


class TimingPatch(StrictModel):
    id: str
    line_id: str
    kind: Literal["line_shift", "boundary", "line_start", "line_end", "restore"]
    boundary_index: int | None = None
    before_ms: list[int]
    after_ms: list[int]
    author: str = "user"
    reason: str = "manual timeline edit"
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def non_negative_ordered(self) -> TimingPatch:
        if any(value < 0 for value in self.after_ms):
            raise ValueError("timing patches cannot contain negative timestamps")
        if self.after_ms != sorted(self.after_ms):
            raise ValueError("timing patch boundaries must be ordered")
        return self


class OverrideHistory(StrictModel):
    id: str
    line_id: str
    span: Span
    before: dict[str, object]
    after: dict[str, object]
    author: str
    reason: str
    created_at: datetime = Field(default_factory=utc_now)


class StructuralIssue(StrictModel):
    code: str
    severity: Literal["info", "warning", "error"]
    line_id: str | None = None
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class KaraokeProject(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    core_version: str = CORE_VERSION
    project_id: str
    title: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    source: SourceRecord = Field(default_factory=SourceRecord)
    audio: AudioRecord = Field(default_factory=AudioRecord)
    model: ModelRecord = Field(default_factory=ModelRecord)
    lines: list[LyricLine] = Field(default_factory=list)
    raw_alignment: RawAlignment | None = None
    alignment_stale: bool = False
    alignment_source: Literal["yohane", "preserved_ass"] | None = None
    timing_patches: list[TimingPatch] = Field(default_factory=list)
    override_history: list[OverrideHistory] = Field(default_factory=list)
    issues: list[StructuralIssue] = Field(default_factory=list)
    read_only: bool = False


class ReadingOverride(StrictModel):
    line_id: str
    expected_text: str
    span: Span
    reading: str | None = None
    romaji: str | None = None
    display_only: bool = False
    author: str = "agent"
    reason: str


class OverrideFile(StrictModel):
    schema_version: Literal[1] = 1
    project_id: str
    overrides: list[ReadingOverride]


class JobEvent(StrictModel):
    stage: str
    progress: Annotated[float, Field(ge=0, le=1)]
    message: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
