"""Data-only animation timing, separate from storyboard-1 and media-plan-1."""
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .multimodal_schema import Digest, storyboard_digest, narration_digest
from .schemas import StrictModel
from .storyboard_schema import Identifier

Seconds = Annotated[float, Field(ge=0, le=60)]


class AnimationScene(StrictModel):
    id: Identifier
    type: Literal["introduction", "evaporation", "condensation", "precipitation", "collection", "overview", "text_explanation"]
    start_seconds: Seconds
    end_seconds: Seconds
    title: Annotated[str, Field(min_length=1, max_length=100)]
    explanation: Annotated[str, Field(min_length=1, max_length=280)]

    @field_validator("type", mode="before")
    @classmethod
    def supported(cls, value):
        allowed={"introduction","evaporation","condensation","precipitation","collection","overview","text_explanation"}
        return value if not isinstance(value,str) or value in allowed else "text_explanation"

    @model_validator(mode="after")
    def positive(self):
        if self.end_seconds-self.start_seconds < .2:
            raise ValueError("Animation scene must be at least 0.2 seconds")
        return self


class CaptionCue(StrictModel):
    start_seconds: Seconds
    end_seconds: Seconds
    text: Annotated[str, Field(min_length=1, max_length=160)]

    @model_validator(mode="after")
    def positive(self):
        if self.end_seconds <= self.start_seconds:
            raise ValueError("Caption must have positive duration")
        return self


class RemotionPlan(StrictModel):
    schema_version: Literal["remotion-plan-1"]
    storyboard_sha256: Digest
    transcript_sha256: Digest
    audio_sha256: Digest | None = None
    audio_offset_seconds: Annotated[float, Field(ge=0, le=3)] = 0.
    timing_source: Literal["scene_tts_measurements", "reviewed_pause_cues", "estimated_character_time"]
    scenes: Annotated[list[AnimationScene], Field(min_length=1, max_length=12)]
    captions: Annotated[list[CaptionCue], Field(max_length=64)]

    @model_validator(mode="after")
    def timeline(self):
        if self.timing_source=="reviewed_pause_cues" and self.audio_sha256 is None:
            raise ValueError("Reviewed timing must be bound to its measured audio")
        cursor=0.
        if len({s.id for s in self.scenes})!=len(self.scenes):
            raise ValueError("Animation identifiers must be unique")
        for scene in self.scenes:
            if abs(scene.start_seconds-cursor) > .00001:
                raise ValueError("Scenes must be ordered, contiguous and non-overlapping")
            cursor=scene.end_seconds
        end=0.
        for cue in self.captions:
            if cue.start_seconds < end-.00001 or cue.end_seconds > cursor+.00001 or cue.start_seconds < self.audio_offset_seconds:
                raise ValueError("Caption timing is outside its timeline or overlaps")
            end=cue.end_seconds
        return self

    def bind(self,spec):
        if (self.storyboard_sha256!=storyboard_digest(spec) or self.transcript_sha256!=narration_digest(spec)
                or abs(self.scenes[-1].end_seconds-spec.duration_seconds)>.00001):
            raise ValueError("Animation plan does not match this storyboard")
        # Timed subtitles may only reproduce the actual script, never add speech.
        normalized=lambda value:"".join(value.split())
        if normalized(" ".join(c.text for c in self.captions)) != normalized(" ".join(s.narration_ko for s in spec.scenes)):
            raise ValueError("Captions must reproduce the storyboard narration")
        if any(s.type not in {"text_explanation","introduction"} for s in self.scenes):
            if "물" not in spec.topic or "순환" not in spec.topic:
                raise ValueError("Water animation is limited to water-cycle storyboards")
        return self
