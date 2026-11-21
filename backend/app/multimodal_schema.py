"""Optional local-media plan; never changes the storyboard-1 generation contract."""
import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .schemas import StrictModel
from .storyboard_schema import Identifier, StoryboardSpec

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


def storyboard_digest(spec: StoryboardSpec):
    return hashlib.sha256(json.dumps(spec.model_dump(), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def narration_digest(spec: StoryboardSpec):
    return hashlib.sha256(" ".join(s.narration_ko for s in spec.scenes).encode()).hexdigest()


class LocalMedia(StrictModel):
    id: Identifier
    kind: Literal["image", "video", "audio"]
    filename: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,90}\.(?:png|jpg|webp|mp4|wav)$")]
    sha256: Digest
    review: Literal["background_only", "requires_mask", "rejected"]

    @model_validator(mode="after")
    def extension(self):
        allowed = {"image":{"png","jpg","webp"},"video":{"mp4"},"audio":{"wav"}}
        if self.filename.rsplit(".",1)[-1] not in allowed[self.kind]:
            raise ValueError("Media suffix must match kind")
        return self


class SceneMedia(StrictModel):
    scene_id: Identifier
    mode: Literal["svg_animation", "ai_image", "ai_image_motion", "ai_video", "text_motion"]
    asset_id: Identifier | None = None
    framing: Literal["contain", "cover", "water_cycle_crops"] = "contain"

    @model_validator(mode="after")
    def reference(self):
        if self.mode.startswith("ai_") != (self.asset_id is not None):
            raise ValueError("AI modes need exactly one local asset reference")
        return self


class ExternalNarration(StrictModel):
    asset_id: Identifier
    transcript_sha256: Digest


class MediaPlan(StrictModel):
    schema_version: Literal["media-plan-1"]
    storyboard_sha256: Digest
    assets: Annotated[list[LocalMedia], Field(max_length=16)]
    scenes: Annotated[list[SceneMedia], Field(min_length=3, max_length=8)]
    narration: ExternalNarration | None = None
    review_prompt: Annotated[str, Field(max_length=100)] = "그림을 보며 핵심 과정을 순서대로 다시 설명해 보세요."

    @model_validator(mode="after")
    def references(self):
        assets = {a.id: a for a in self.assets}
        if len(assets) != len(self.assets) or len({a.filename for a in self.assets}) != len(self.assets) or len({s.scene_id for s in self.scenes}) != len(self.scenes):
            raise ValueError("Media and scene identifiers must be unique")
        for scene in self.scenes:
            if scene.asset_id:
                asset = assets.get(scene.asset_id)
                if asset is None or asset.kind != ("video" if scene.mode == "ai_video" else "image"):
                    raise ValueError("Scene asset kind/reference mismatch")
                if asset.review == "requires_mask" and scene.framing != "water_cycle_crops":
                    raise ValueError("Unreliable AI labels must be excluded by a reviewed crop")
        if self.narration and (self.narration.asset_id not in assets or assets[self.narration.asset_id].kind != "audio"):
            raise ValueError("Narration must reference local audio")
        return self

    def bind(self, spec: StoryboardSpec):
        if self.storyboard_sha256 != storyboard_digest(spec) or {s.scene_id for s in self.scenes} != {s.id for s in spec.scenes}:
            raise ValueError("Media plan does not match this storyboard")
        return self
