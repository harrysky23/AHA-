"""Versioned, declarative video DSL. No expression evaluator, paths or executable code."""
import math
import re
from typing import Annotated, Literal, Union

from pydantic import AfterValidator, Field, model_validator

from .schemas import StrictModel

STORYBOARD_SCHEMA_VERSION = "storyboard-1"


def plain_text(value: str) -> str:
    # This is an output hygiene check, not a security boundary. Render as escaped text.
    if re.search(r"```|<\s*/?\s*(?:script|svg|iframe)\b|javascript:|__import__|\b(?:eval|exec)\s*\(|\bos\.system|\bsubprocess\.", value, re.I):
        raise ValueError("Executable code/markup is not part of the storyboard DSL")
    if re.search(r"(?:^|\n)\s*(?:import\s+\w|from\s+\w+\s+import\b|def\s+\w+\s*\(|class\s+\w+\s*[:(]|(?:const|let|var)\s+\w+\s*=|function\s+\w*\s*\(|(?:sudo|curl|wget|pip|npm|ffmpeg)\s|rm\s+-)", value):
        raise ValueError("Source code and shell commands are not display parameters")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError("Control characters are not supported")
    return value


def korean_narration(value: str) -> str:
    if not re.search(r"[가-힣]", value):
        raise ValueError("Narration must include Korean text")
    return value


Label = Annotated[str, Field(min_length=1, max_length=80), AfterValidator(plain_text)]
Text = Annotated[str, Field(min_length=1, max_length=280), AfterValidator(plain_text)]
Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")]
Coordinate = Annotated[float, Field(ge=-1000, le=1000)]
Normalized = Annotated[float, Field(ge=.05, le=.95)]
Seconds = Annotated[float, Field(ge=0, le=60, multiple_of=.1)]
Palette = Literal["violet", "yellow", "pink", "blue", "green"]


def unique_ids(items):
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Element IDs must be unique within a visualization")
    return set(ids)


class Point(StrictModel):
    x: Coordinate
    y: Coordinate


class AxisRange(StrictModel):
    min: Coordinate
    max: Coordinate

    @model_validator(mode="after")
    def ordered(self):
        if self.min >= self.max:
            raise ValueError("Axis min must be smaller than max")
        return self


class Curve(StrictModel):
    id: Identifier
    label: Label
    # Ascending powers: c0 + c1*x + c2*x² + c3*x³. No formula string.
    coefficients: Annotated[list[Coordinate], Field(min_length=1, max_length=4)]
    color: Palette


class Marker(StrictModel):
    id: Identifier
    label: Label
    point: Point
    color: Palette
    curve_id: Identifier | None = None


class Connector(StrictModel):
    id: Identifier
    start_marker: Identifier
    end_marker: Identifier
    label: Label
    extend: bool
    color: Palette


class MarkerKeyframe(StrictModel):
    at_seconds: Seconds
    marker_id: Identifier
    point: Point


class FunctionGraph(StrictModel):
    type: Literal["function_graph"]
    x_label: Label
    y_label: Label
    x_range: AxisRange
    y_range: AxisRange
    curves: Annotated[list[Curve], Field(min_length=1, max_length=4)]
    markers: Annotated[list[Marker], Field(max_length=8)]
    connectors: Annotated[list[Connector], Field(max_length=4)]
    marker_keyframes: Annotated[list[MarkerKeyframe], Field(max_length=16)]

    @model_validator(mode="after")
    def geometry(self):
        unique_ids([*self.curves, *self.markers, *self.connectors])
        markers = {m.id for m in self.markers}
        marker_map = {m.id: m for m in self.markers}
        curves = {c.id: c for c in self.curves}
        for line in self.connectors:
            if line.start_marker not in markers or line.end_marker not in markers or line.start_marker == line.end_marker:
                raise ValueError("Connectors must reference two different existing markers")
        last = {}
        for key in self.marker_keyframes:
            if key.marker_id not in markers or key.at_seconds <= last.get(key.marker_id, 0):
                raise ValueError("Marker keyframes must follow t=0 in increasing order for each marker")
            last[key.marker_id] = key.at_seconds
        for point in [m.point for m in self.markers] + [k.point for k in self.marker_keyframes]:
            if not self.x_range.min <= point.x <= self.x_range.max or not self.y_range.min <= point.y <= self.y_range.max:
                raise ValueError("Markers must lie inside the graph viewport")
        positions = [(m, m.point) for m in self.markers] + [(marker_map[k.marker_id], k.point) for k in self.marker_keyframes]
        for marker, point in positions:
            if marker.curve_id is not None:
                if marker.curve_id not in curves:
                    raise ValueError("Marker references an unknown curve")
                coefficients = curves[marker.curve_id].coefficients
                y = sum(c * point.x**power for power, c in enumerate(coefficients))
                if not math.isclose(y, point.y, abs_tol=1e-6):
                    raise ValueError("Curve-bound marker must match polynomial coordinates")
        return self


class DiagramNode(StrictModel):
    id: Identifier
    label: Label
    detail: Text
    x: Normalized
    y: Normalized
    color: Palette


class DiagramEdge(StrictModel):
    id: Identifier
    source: Identifier
    target: Identifier
    label: Label


def check_edges(nodes, edges):
    ids = unique_ids([*nodes, *edges])
    node_ids = {node.id for node in nodes}
    for edge in edges:
        if edge.source not in node_ids or edge.target not in node_ids or edge.source == edge.target:
            raise ValueError("Edges must reference two different existing nodes")
    return ids


class ProcessDiagram(StrictModel):
    type: Literal["process_diagram"]
    flow: Literal["sequence", "cycle", "network"]
    nodes: Annotated[list[DiagramNode], Field(min_length=2, max_length=8)]
    edges: Annotated[list[DiagramEdge], Field(min_length=1, max_length=12)]

    @model_validator(mode="after")
    def links(self):
        check_edges(self.nodes, self.edges)
        if self.flow == "cycle":
            # A cycle must actually return to the starting node, not merely say so.
            graph = {node.id: [] for node in self.nodes}
            for edge in self.edges:
                graph[edge.source].append(edge.target)
            start = self.nodes[0].id
            visited = set()

            def reaches_start(node):
                if node in visited:
                    return False
                visited.add(node)
                return any(target == start or reaches_start(target) for target in graph[node])

            if not reaches_start(start):
                raise ValueError("A cycle diagram must include a directed cycle through its first node")
        return self


class TimelineEvent(StrictModel):
    id: Identifier
    position: Annotated[float, Field(ge=-10000, le=10000)]
    time_label: Label
    title: Label
    detail: Text


class Timeline(StrictModel):
    type: Literal["timeline"]
    time_unit: Literal["year", "second", "step"]
    events: Annotated[list[TimelineEvent], Field(min_length=2, max_length=8)]

    @model_validator(mode="after")
    def ordered(self):
        unique_ids(self.events)
        positions = [event.position for event in self.events]
        if any(a >= b for a, b in zip(positions, positions[1:])):
            raise ValueError("Timeline positions must be strictly increasing")
        return self


class ComparisonRow(StrictModel):
    id: Identifier
    aspect: Label
    left: Text
    right: Text
    emphasis: Literal["none", "left", "right"]


class Comparison(StrictModel):
    type: Literal["comparison"]
    left_title: Label
    right_title: Label
    rows: Annotated[list[ComparisonRow], Field(min_length=1, max_length=5)]

    @model_validator(mode="after")
    def ids(self):
        unique_ids(self.rows)
        return self


class IndexRange(StrictModel):
    low: Annotated[int, Field(ge=0, le=15)]
    high: Annotated[int, Field(ge=0, le=15)]


class State(DiagramNode):
    items: Annotated[list[Label], Field(max_length=16)]
    highlight_indices: Annotated[list[int], Field(max_length=16)]
    active_range: IndexRange | None = None

    @model_validator(mode="after")
    def indices(self):
        if len(set(self.highlight_indices)) != len(self.highlight_indices) or any(i < 0 or i >= len(self.items) for i in self.highlight_indices):
            raise ValueError("Highlighted indices must refer to unique existing data items")
        if self.active_range is not None:
            if not self.active_range.low <= self.active_range.high < len(self.items):
                raise ValueError("Active range must lie inside state data")
            if any(not self.active_range.low <= i <= self.active_range.high for i in self.highlight_indices):
                raise ValueError("Highlighted indices must lie inside active range")
        return self


class StateStep(StrictModel):
    at_seconds: Seconds
    state_id: Identifier
    caption: Text


class StateTransition(StrictModel):
    type: Literal["state_transition"]
    states: Annotated[list[State], Field(min_length=2, max_length=8)]
    transitions: Annotated[list[DiagramEdge], Field(min_length=1, max_length=12)]
    initial_state: Identifier
    steps: Annotated[list[StateStep], Field(min_length=1, max_length=10)]

    @model_validator(mode="after")
    def path(self):
        check_edges(self.states, self.transitions)
        ids = {s.id for s in self.states}
        if self.initial_state not in ids or self.steps[0].state_id != self.initial_state or self.steps[0].at_seconds != 0:
            raise ValueError("State steps must begin at t=0 in the declared initial state")
        allowed = {(edge.source, edge.target) for edge in self.transitions}
        for index, step in enumerate(self.steps):
            if step.state_id not in ids:
                raise ValueError("State step references an unknown state")
            if index:
                previous = self.steps[index-1]
                if step.at_seconds <= previous.at_seconds or (previous.state_id != step.state_id and (previous.state_id, step.state_id) not in allowed):
                    raise ValueError("State steps must advance in time along declared transitions")
        return self


class TextExplanation(StrictModel):
    type: Literal["text_explanation"]
    heading: Label
    paragraphs: Annotated[list[Text], Field(min_length=1, max_length=3)]
    fallback_reason: Text


Visualization = Annotated[Union[FunctionGraph, ProcessDiagram, Timeline, Comparison, StateTransition, TextExplanation], Field(discriminator="type")]


class Cue(StrictModel):
    at_seconds: Seconds
    action: Literal["reveal", "highlight", "hide"]
    target_id: Identifier


class ScreenContent(StrictModel):
    title: Label
    bullets: Annotated[list[Text], Field(max_length=3)]
    # Plain mathematical display strings, not TeX programs or an expression language.
    formulas: Annotated[list[Label], Field(max_length=3)]


def visualization_ids(visual) -> set[str]:
    if isinstance(visual, FunctionGraph):
        return {x.id for x in [*visual.curves, *visual.markers, *visual.connectors]}
    if isinstance(visual, ProcessDiagram):
        return {x.id for x in [*visual.nodes, *visual.edges]}
    if isinstance(visual, Timeline):
        return {x.id for x in visual.events}
    if isinstance(visual, Comparison):
        return {x.id for x in visual.rows}
    if isinstance(visual, StateTransition):
        return {x.id for x in [*visual.states, *visual.transitions]}
    return set()


class Scene(StrictModel):
    id: Identifier
    start_seconds: Seconds
    end_seconds: Seconds
    screen: ScreenContent
    narration_ko: Annotated[str, Field(min_length=10, max_length=500), AfterValidator(plain_text), AfterValidator(korean_narration)]
    visualization: Visualization
    cues: Annotated[list[Cue], Field(max_length=12)]
    source_ids: Annotated[list[Identifier], Field(max_length=3)]

    @model_validator(mode="after")
    def local_times(self):
        # Timestamps are deciseconds; use integer ticks to avoid rejecting 2.3-0.3.
        duration = (round(self.end_seconds*10)-round(self.start_seconds*10))/10
        if duration < 2:
            raise ValueError("A scene must last at least two seconds")
        ids = visualization_ids(self.visualization)
        previous = -1
        for cue in self.cues:
            if cue.target_id not in ids or cue.at_seconds < previous or cue.at_seconds > duration + 1e-7:
                raise ValueError("Cues must be ordered, inside the scene, and reference declared elements")
            previous = cue.at_seconds
        timed = getattr(self.visualization, "marker_keyframes", []) or getattr(self.visualization, "steps", [])
        if any(item.at_seconds > duration + 1e-7 for item in timed):
            raise ValueError("Animation/state timing exceeds scene duration")
        return self


class VideoFormat(StrictModel):
    aspect_ratio: Literal["9:16"]
    width: Literal[1080]
    height: Literal[1920]
    fps: Literal[30]


class StorySource(StrictModel):
    id: Identifier
    page: Annotated[int, Field(ge=1, le=20)]
    quote: Annotated[str, Field(min_length=1, max_length=240)]


class StoryboardSpec(StrictModel):
    schema_version: Literal["storyboard-1"]
    topic: Label
    learning_objectives: Annotated[list[Text], Field(min_length=1, max_length=3)]
    student_level: Literal["foundation", "high_school", "advanced"]
    difficult_point: Text
    duration_seconds: Annotated[int, Field(ge=30, le=60)]
    video: VideoFormat
    scenes: Annotated[list[Scene], Field(min_length=3, max_length=8)]
    material_usage: Literal["used", "not_relevant", "unavailable"]
    sources: Annotated[list[StorySource], Field(max_length=3)]
    assumptions: Annotated[list[Text], Field(min_length=1, max_length=5)]
    review_status: Literal["ready_for_review", "needs_context"]
    limitations: Annotated[list[Text], Field(max_length=4)]

    @model_validator(mode="after")
    def timeline_and_sources(self):
        unique_ids(self.scenes)
        sources = unique_ids(self.sources)
        expected = 0.
        cited = set()
        for scene in self.scenes:
            if not math.isclose(scene.start_seconds, expected, abs_tol=1e-7):
                raise ValueError("Scenes must be ordered, nonoverlapping and contiguous from t=0")
            if scene.end_seconds > self.duration_seconds:
                raise ValueError("Scene exceeds total duration")
            if not set(scene.source_ids) <= sources or len(set(scene.source_ids)) != len(scene.source_ids):
                raise ValueError("Unknown or duplicate scene source ID")
            cited.update(scene.source_ids)
            expected = scene.end_seconds
        if not math.isclose(expected, self.duration_seconds, abs_tol=1e-7):
            raise ValueError("Scenes must cover the full declared duration")
        if self.material_usage == "used":
            if not sources or cited != sources:
                raise ValueError("Used material must be cited by at least one scene per source")
        elif sources or cited:
            raise ValueError("Unused material must not have invented citations")
        if self.review_status == "needs_context" and not self.limitations:
            raise ValueError("Missing context must have an explicit limitation")
        return self


def verify_storyboard_sources(spec: StoryboardSpec, pages: list[dict]) -> None:
    available = {p["page"]: " ".join(p["text"].split()) for p in pages}
    if not available and spec.material_usage != "unavailable":
        raise ValueError("Material is not available")
    if available and spec.material_usage == "unavailable":
        raise ValueError("Available text must be used or explicitly classified as unrelated")
    for source in spec.sources:
        if source.page not in available or " ".join(source.quote.split()) not in available[source.page]:
            raise ValueError("Storyboard quote does not occur on the cited page")
