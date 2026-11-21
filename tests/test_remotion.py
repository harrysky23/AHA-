"""Data/selection safety only. Actual Remotion rendering is explicitly opt-in."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.multimodal_schema import storyboard_digest,narration_digest
from backend.app.remotion_schema import RemotionPlan
from backend.app.rendering.core import RenderError
from backend.app.rendering.engine import render_storyboard
from backend.app.rendering.remotion import auto_plan
from backend.app.services.video_jobs import VideoJobs
from backend.app.video_config import VideoSettings,get_video_settings
from backend.app.config import ConfigurationError
from scripts.compare_water_cycle import water_storyboard

ROOT=Path(__file__).resolve().parents[1]


def plan():
    spec=water_storyboard();template=json.loads((ROOT/"video-remotion/examples/water-cycle-cues.json").read_text())
    data={"schema_version":"remotion-plan-1","storyboard_sha256":storyboard_digest(spec),
        "transcript_sha256":narration_digest(spec),"audio_sha256":template["source_audio_sha256"],
        "audio_offset_seconds":1.,"timing_source":"reviewed_pause_cues", "scenes":template["scenes"],"captions":template["captions"]}
    return spec,data


def test_original_script_and_measured_audio_are_bound():
    spec,data=plan();value=RemotionPlan.model_validate(data).bind(spec)
    assert len(value.scenes)==6 and len(value.captions)==8
    assert value.audio_offset_seconds==1 and value.scenes[-1].end_seconds==30
    assert {s.type for s in value.scenes}=={"introduction","evaporation","condensation","precipitation","collection","overview"}


@pytest.mark.parametrize("problem",["overlap","gap","out_of_bounds","subtitle_overlap","subtitle_new_words","wrong_audio","javascript","wrong_story"])
def test_invalid_animation_data_rejected(problem):
    spec,data=plan()
    if problem=="overlap":data["scenes"][1]["start_seconds"]=1.
    elif problem=="gap":data["scenes"][1]["start_seconds"]=2.
    elif problem=="out_of_bounds":data["scenes"][-1]["end_seconds"]=31.
    elif problem=="subtitle_overlap":data["captions"][1]["start_seconds"]=2.
    elif problem=="subtitle_new_words":data["captions"][0]["text"]="원본 음성에 없는 새 설명이에요."
    elif problem=="wrong_audio":data["audio_sha256"]=None
    elif problem=="javascript":data["scenes"][0]["javascript"]="fetch('https://example.test')"
    else:data["storyboard_sha256"]="0"*64
    with pytest.raises((ValueError,ValidationError)):RemotionPlan.model_validate(data).bind(spec)


def test_unknown_animation_is_safe_text_and_non_water_cannot_use_water():
    spec,data=plan();data["scenes"][0]["type"]="arbitrary_python"
    assert RemotionPlan.model_validate(data).scenes[0].type=="text_explanation"
    spec.topic="다른 학습 주제";data["storyboard_sha256"]=storyboard_digest(spec)
    with pytest.raises(ValueError):RemotionPlan.model_validate(data).bind(spec)


def test_invalid_renderer_fails_before_worker(tmp_path):
    with pytest.raises(RenderError) as exc:render_storyboard(water_storyboard(),tmp_path/"video.mp4",renderer="python")
    assert exc.value.code=="invalid_renderer"
    assert not list(tmp_path.iterdir())


def test_local_tts_measurements_determine_captions_without_clipping():
    spec=water_storyboard()
    for s in spec.scenes:s.narration_ko="가"*150
    timings=[{"raw_seconds":4.5,"tempo":1.} for s in spec.scenes]
    value=auto_plan(spec,timings)
    assert value.timing_source=="scene_tts_measurements"
    assert max(len(c.text) for c in value.captions)<=56
    assert all(c.end_seconds<=s.start_seconds+4.5+.0001 for s in spec.scenes for c in value.captions if s.start_seconds<=c.start_seconds<s.end_seconds)


def test_external_unaligned_audio_is_labelled_estimate():
    value=auto_plan(water_storyboard(),[],{"spoken_seconds":19.4})
    assert value.timing_source=="estimated_character_time"
    assert value.captions[-1].end_seconds==pytest.approx(19.4)


def test_async_queue_selects_renderer_but_keeps_default():
    svg=VideoJobs(VideoSettings());remotion=VideoJobs(VideoSettings(renderer="remotion"))
    assert svg.render is render_storyboard
    assert remotion.render.func is render_storyboard and remotion.render.keywords=={"renderer":"remotion"}
    svg.pool.shutdown();remotion.pool.shutdown()


def test_unknown_backend_configuration_is_rejected(monkeypatch):
    monkeypatch.setenv("AHA_VIDEO_RENDERER","untrusted-script")
    with pytest.raises(ConfigurationError):get_video_settings()
