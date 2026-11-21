"""The only executable visualization type in Phase 2 is a vetted x² component."""
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ShortText = Annotated[str, Field(min_length=1, max_length=240)]
Explanation = Annotated[str, Field(min_length=1, max_length=700)]
Number = Annotated[float, Field(ge=-10, le=10)]
Delta = Annotated[float, Field(ge=-1.2, le=1.2, multiple_of=.0001)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)


class Analysis(StrictModel):
    learning_level: Literal["foundation", "standard", "advanced"]
    level_reason: ShortText
    student_need: ShortText
    core_concepts: Annotated[list[ShortText], Field(min_length=1, max_length=4)]
    prerequisites: Annotated[list[ShortText], Field(min_length=1, max_length=3)]


class Step(StrictModel):
    title: Annotated[str, Field(min_length=1, max_length=60)]
    explanation: Explanation


class Variable(StrictModel):
    name: Literal["h"]
    label: ShortText
    min: Annotated[float, Field(ge=-1.2, le=-1.2)]
    max: Annotated[float, Field(ge=1.2, le=1.2)]
    step: Annotated[float, Field(ge=.0001, le=.0001)]
    initial: Delta


class Visualization(StrictModel):
    type: Literal["secant_tangent_x2"]
    function: Literal["x_squared"]
    a: Annotated[float, Field(ge=1, le=1)]
    variable: Variable


class Example(StrictModel):
    h: Delta
    secant_slope: Number
    tangent_slope: Number
    explanation: ShortText

    @model_validator(mode="after")
    def check_math(self):
        if self.h == 0 or not math.isclose(self.secant_slope, 2+self.h, abs_tol=1e-7) or self.tangent_slope != 2:
            raise ValueError("Example mathematics is inconsistent with f(x)=x², a=1")
        return self


class Quiz(StrictModel):
    kind: Literal["secant_slope", "tangent_slope", "undefined_at_zero"]
    h: Delta
    answer: Number | None
    explanation: ShortText

    @model_validator(mode="after")
    def check_math(self):
        if self.kind == "undefined_at_zero":
            valid = self.h == 0 and self.answer is None
        elif self.kind == "tangent_slope":
            valid = self.answer == 2
        else:
            valid = self.h != 0 and self.answer is not None and math.isclose(self.answer, 2+self.h, abs_tol=1e-7)
        if not valid:
            raise ValueError("Quiz answer does not match deterministic mathematics")
        return self


class SourceQuote(StrictModel):
    page: Annotated[int, Field(ge=1, le=20)]
    quote: ShortText


class LessonSpec(StrictModel):
    schema_version: Literal["1"]
    scope: Literal["supported", "unsupported"]
    title: Annotated[str, Field(min_length=1, max_length=80)]
    analysis: Analysis
    explanation: Explanation
    steps: Annotated[list[Step], Field(min_length=2, max_length=4)]
    visualization: Visualization
    examples: Annotated[list[Example], Field(min_length=1, max_length=3)]
    quiz: Annotated[list[Quiz], Field(min_length=1, max_length=3)]
    source_quotes: Annotated[list[SourceQuote], Field(max_length=3)]
    assumptions: Annotated[list[ShortText], Field(min_length=1, max_length=4)]


def verify_grounding(spec: LessonSpec, pages: list[dict]) -> None:
    available = {p["page"]: " ".join(p["text"].split()) for p in pages}
    if pages and not spec.source_quotes:
        raise ValueError("Available material needs an exact source quote")
    for source in spec.source_quotes:
        if source.page not in available or " ".join(source.quote.split()) not in available[source.page]:
            raise ValueError("Source quote does not occur on the cited page")
