"""Offline media-plan safety/fallback tests. Never loads keys or uses AI."""
import hashlib
import json
from threading import Event

import pytest
from pydantic import ValidationError

from backend.app.multimodal_schema import LocalMedia, MediaPlan, storyboard_digest, narration_digest
from backend.app.providers.base import StoryboardInput
from backend.app.rendering import multimodal as media
from backend.app.rendering.core import Budget, RenderError, RenderOptions
from backend.app.services.materials import MaterialContext
from backend.app.services.multimodal import create_media_plan, propose_visual_requests
from backend.app.services.storyboard_mock import generate_mock_storyboard


def spec(topic="물의 순환"):
    return generate_mock_storyboard(StoryboardInput(topic,"관계를 설명해 주세요.",MaterialContext(),30))


def asset(kind="image", review="background_only", raw=b"fixture"):
    return {"id":kind,"kind":kind,"filename":{"image":"image.jpg","video":"video.mp4","audio":"voice.wav"}[kind],
            "sha256":hashlib.sha256(raw).hexdigest(),"review":review}


def plan(value=None, mode="ai_image", kind="image", review="background_only"):
    value=value or spec()
    return create_media_plan(value,[asset(kind,review)],{s.id:{"mode":mode,"asset_id":kind,
        "framing":"water_cycle_crops" if review=="requires_mask" else "contain"} for s in value.scenes})


@pytest.mark.parametrize("mode,kind",[("ai_image","image"),("ai_image_motion","image"),("ai_video","video")])
def test_media_modes_bind_to_existing_storyboard(mode,kind):
    value=spec();p=plan(value,mode,kind)
    assert media.parse_media_plan(p,value).storyboard_sha256==storyboard_digest(value)


@pytest.mark.parametrize("mode",["svg_animation","text_motion"])
def test_code_free_modes_need_no_asset(mode):
    value=spec();p=create_media_plan(value,[],{s.id:{"mode":mode} for s in value.scenes})
    assert all(e.asset_id is None for e in p.scenes)


@pytest.mark.parametrize("change",[
    {"filename":"../secret.jpg"},{"filename":"https://example.test/a.jpg"},
    {"filename":"x.mp4"},{"javascript":"alert(1)"},{"sha256":"wrong"},
])
def test_reject_untrusted_asset_fields(change):
    with pytest.raises(ValidationError):LocalMedia.model_validate({**asset(),**change})


def test_edited_spec_or_missing_scene_rejected():
    value=spec();p=plan(value);value.scenes[0].narration_ko="수정된 내레이션으로 기존 미디어 연결을 바꿔요."
    with pytest.raises(RenderError):media.parse_media_plan(p,value)
    value=spec();data=p.model_dump();data["scenes"]=data["scenes"][:3]
    with pytest.raises(RenderError):media.parse_media_plan(data,value)


def test_unreviewed_arrows_require_crop_and_duplicate_filename_rejected():
    p=plan(review="requires_mask").model_dump();p["scenes"][0]["framing"]="cover"
    with pytest.raises(ValidationError):MediaPlan.model_validate(p)
    p=plan().model_dump();p["assets"].append({**p["assets"][0],"id":"other"})
    with pytest.raises(ValidationError):MediaPlan.model_validate(p)


def test_math_and_algorithm_force_svg():
    for topic in ["미분계수","이진 탐색"]:
        value=spec(topic);entries,fallbacks=media.resolve_scenes(value,plan(value),{})
        for scene in value.scenes:
            if scene.visualization.type in {"function_graph","state_transition"}:
                assert entries[scene.id]["mode"]=="svg_animation"
        assert any(f["reason"]=="exact_diagram_requires_svg" for f in fallbacks)


@pytest.mark.parametrize("problem",["missing","symlink","hash","rejected"])
def test_bad_assets_fall_back_without_reading_remote(tmp_path,problem):
    root=tmp_path/"source";root.mkdir();work=tmp_path/"work";work.mkdir()
    p=plan(review="rejected" if problem=="rejected" else "background_only")
    if problem=="symlink":(root/"image.jpg").symlink_to(tmp_path/"private")
    elif problem!="missing":(root/"image.jpg").write_bytes(b"modified" if problem=="hash" else b"fixture")
    media.stage_media(p,root,work,Budget(work,RenderOptions(min_free_bytes=0)))
    failed=json.loads((work/"asset-failures.json").read_text())
    entries,fallbacks=media.resolve_scenes(spec(),p,failed)
    assert failed and all(e["mode"]=="svg_animation" for e in entries.values()) and len(fallbacks)==4


def test_copy_validates_hash_and_cancel_does_not_become_fallback(tmp_path):
    root=tmp_path/"source";root.mkdir();(root/"image.jpg").write_bytes(b"fixture")
    work=tmp_path/"work";work.mkdir();event=Event();event.set()
    with pytest.raises(RenderError) as exc:
        media.stage_media(plan(),root,work,Budget(work,RenderOptions(min_free_bytes=0)),event)
    assert exc.value.code=="render_cancelled"


def test_wrong_transcript_never_uses_external_voice(tmp_path):
    value=spec();p=create_media_plan(value,[asset("audio")],{},narration_id="audio")
    p.narration.transcript_sha256="0"*64
    result,reason=media.external_narration(value,p,tmp_path,Budget(tmp_path,RenderOptions()),{}, {})
    assert result is None and reason=="narration_transcript_mismatch"


@pytest.mark.parametrize("failure",["audio_fit_failed","render_timeout","disk_limit","render_cancelled"])
def test_audio_failure_policy_never_hides_resource_limits(tmp_path,monkeypatch,failure):
    value=spec();p=create_media_plan(value,[asset("audio")],{},narration_id="audio")
    def fail(*args,**kwargs):raise RenderError(failure,"fixed diagnostic")
    monkeypatch.setattr(media,"run_process",fail)
    budget=Budget(tmp_path,RenderOptions())
    if failure=="audio_fit_failed":
        assert media.external_narration(value,p,tmp_path,budget,{"audio":{"duration_seconds":19.4}}, {})==(None,failure)
    else:
        with pytest.raises(RenderError) as exc:media.external_narration(value,p,tmp_path,budget,{"audio":{"duration_seconds":19.4}}, {})
        assert exc.value.code==failure


def test_subtitles_stop_at_measured_speech_end():
    value=spec();assert media.subtitle_at(value,20,19.4,"복습해 보세요.")=="복습해 보세요."
    assert media.subtitle_at(value,0,19.4,"복습해 보세요.") in value.scenes[0].narration_ko


def test_only_reviewed_windows_can_reach_water_background():
    filters=media.crop_filters("water_cycle_crops")
    assert "ih*0.30" in filters and "ih*0.20" in filters and "overlay=0:1520" in filters
    assert "http" not in filters and "movie=" not in filters


def test_scene_request_proposal_is_offline_and_limited():
    from types import SimpleNamespace
    settings=SimpleNamespace(image_model="fixture-image")
    value=propose_visual_requests(spec(),settings)
    assert len(value["requests"])==1 and value["requests"][0]["payload"]["number_of_images"]==1
    assert "물의 순환" in value["requests"][0]["payload"]["prompt"]
    assert "separate_approval" in value["video_status"]
    other=spec("이진 탐색")
    for s in other.scenes:s.visualization=other.scenes[0].visualization
    assert propose_visual_requests(other,settings)["requests"]==[]


def test_polling_accounting_is_not_summed_or_erased_by_null():
    from scripts.compare_water_cycle import official_accounting
    assert official_accounting([{"credits_charged":252.},{"credits_charged":252.},{"credits_charged":None}])["credits_charged"]==252.
    assert official_accounting([{"credits_charged":None,"input_tokens":76}])=={
        "credits_charged":None,"input_tokens":76,"output_tokens":None}


def test_reused_voice_skips_even_unit_tempo_processing(tmp_path,monkeypatch):
    value=spec();p=create_media_plan(value,[asset("audio")],{},narration_id="audio")
    commands=[]
    monkeypatch.setattr(media,"run_process",lambda command,*args,**kwargs:commands.append(command))
    result,reason=media.external_narration(value,p,tmp_path,Budget(tmp_path,RenderOptions()),
        {"audio":{"duration_seconds":19.4}}, {},preserve_waveform=True)
    assert reason is None and result["tempo"]==1
    assert not any("atempo=" in arg for arg in commands[0])
