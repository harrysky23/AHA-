"""Additional Remotion worker path. No .env, AI calls or untrusted code."""
import hashlib
import json
from pathlib import Path
import resource
import shutil

from ..multimodal_schema import narration_digest, storyboard_digest
from ..remotion_schema import RemotionPlan
from ..storyboard_schema import StoryboardSpec
from .browser import browser_executable
from .core import Budget, RenderError, executable, probe, run_process
from .multimodal import parse_media_plan, prepare_assets, external_narration, crop_filters
from .tts import MacOSSay, build_narration
from .worker import verify_media

PROJECT=Path(__file__).resolve().parents[3]/"video-remotion"
RESOURCE_ERRORS={"render_timeout","disk_limit","disk_full","render_cancelled"}


def auto_plan(spec,timings,external=None):
    scenes=[];captions=[]
    water="물" in spec.topic and "순환" in spec.topic
    for index,s in enumerate(spec.scenes):
        kind="text_explanation"
        if water:
            kind="overview"
            for keyword,candidate in [("응결","condensation"),("강수","precipitation"),("증발","evaporation"),("모이며","collection")]:
                if keyword in s.screen.title:kind=candidate;break
        scenes.append({"id":s.id,"type":kind,"start_seconds":s.start_seconds,"end_seconds":s.end_seconds,
            "title":s.screen.title,"explanation":s.screen.bullets[0] if s.screen.bullets else s.narration_ko[:280]})
        if external:
            total=sum(len(x.narration_ko) for x in spec.scenes)
            start=sum(len(x.narration_ko) for x in spec.scenes[:index])/total*external["spoken_seconds"]
            end=start+len(s.narration_ko)/total*external["spoken_seconds"]
        else:
            timing=timings[index]
            start=s.start_seconds;end=min(s.end_seconds,start+timing["raw_seconds"]/timing["tempo"])
        # Long narration is paged, with cues within its measured speech interval.
        text=s.narration_ko;parts=[]
        while len(text)>56:
            cut=text.rfind(" ",0,56)
            if cut<25:cut=56
            parts.append(text[:cut]);text=text[cut:].lstrip()
        parts.append(text)
        cursor=start;weight=sum(len(p) for p in parts)
        for part_index,part in enumerate(parts):
            next_time=end if part_index==len(parts)-1 else cursor+(end-start)*len(part)/weight
            captions.append({"start_seconds":float(cursor),"end_seconds":float(next_time),"text":part})
            cursor=next_time
    return RemotionPlan.model_validate({"schema_version":"remotion-plan-1","storyboard_sha256":storyboard_digest(spec),
        "transcript_sha256":narration_digest(spec),"timing_source":"estimated_character_time" if external else "scene_tts_measurements", "scenes":scenes,"captions":captions}).bind(spec)


def prepare(work,options):
    budget=Budget(work,options)
    spec=StoryboardSpec.model_validate_json((work/"input.json").read_text())
    if not (PROJECT/"node_modules/@remotion/renderer").is_dir():
        raise RenderError("remotion_missing","video-remotion에서 npm ci --ignore-scripts를 먼저 실행해 주세요.")
    chrome=browser_executable()
    if not chrome or not Path(chrome).is_file():
        raise RenderError("browser_failed","Chrome 또는 AHA_BROWSER_EXECUTABLE 설정이 필요해요.")
    def progress(scene_id,phase,**detail):
        p=work/"progress.tmp";p.write_text(json.dumps({"scene_id":scene_id,"phase":phase,**detail}));p.replace(work/"progress.json")
    progress(None,"tts")
    media=None;external=None;fallbacks=[]
    if (work/"media-plan.json").exists():
        media=parse_media_plan(json.loads((work/"media-plan.json").read_text()),spec)
        metadata,failed=prepare_assets(media,work,budget)
        external,reason=external_narration(spec,media,work,budget,metadata,failed,preserve_waveform=True)
        if reason:fallbacks.append({"component":"narration","reason":reason,"to":"macos_local_tts"})
    if external:
        audio=external["path"];timings=[{k:v for k,v in external.items() if k!="path"}]
    else:
        audio,timings=build_narration(spec,work,budget,MacOSSay(),lambda id:progress(id,"tts"))
    plan=RemotionPlan.model_validate_json((work/"animation-plan.json").read_text()).bind(spec) if (work/"animation-plan.json").exists() else auto_plan(spec,timings,external)
    for scene in plan.scenes:
        if scene.type=="text_explanation":
            fallbacks.append({"scene_id":scene.id,"reason":"basic_text_template","to":"text_explanation"})
    if plan.timing_source=="reviewed_pause_cues":
        source=next((a for a in media.assets if a.id==media.narration.asset_id),None) if media and media.narration else None
        if not external or not source or source.sha256!=plan.audio_sha256 or external["tempo"]!=1:
            raise RenderError("timing_audio_mismatch","검토된 타임스탬프와 같은 원본 음성이 필요해요.")
    if external and external["spoken_seconds"]+plan.audio_offset_seconds>spec.duration_seconds:
        raise RenderError("narration_too_long","오디오 시작 지연을 포함하면 음성이 영상보다 길어요.")
    public=work/"public/generated";public.mkdir(parents=True)
    shutil.copyfile(audio,public/"narration.wav")
    background=None
    if media:
        candidate=next((s for s in media.scenes if s.mode in {"ai_image","ai_image_motion"} and s.asset_id not in failed),None)
        if candidate:
            asset=next(a for a in media.assets if a.id==candidate.asset_id)
            try:
                filters=crop_filters(candidate.framing).replace("__FPS__",str(options.fps))+"[out]"
                run_process([executable("ffmpeg"),"-nostdin","-v","error","-y","-protocol_whitelist","file,pipe","-i",str(work/"assets"/asset.filename),
                    "-filter_complex",filters,"-map","[out]","-frames:v","1",str(public/"background.jpg")],budget,"background_failed")
                background="generated/background.jpg"
            except RenderError as exc:
                if exc.code in RESOURCE_ERRORS:raise
                fallbacks.append({"component":"background","reason":exc.code,"to":"local_svg"})
        elif any(s.mode.startswith("ai_") for s in media.scenes):
            fallbacks.append({"component":"background","reason":"no_usable_reviewed_image","to":"local_svg"})
    props={"topic":spec.topic,"fps":options.fps,"duration":spec.duration_seconds,"scenes":[s.model_dump() for s in plan.scenes],
        "captions":[c.model_dump() for c in plan.captions],"audio":"generated/narration.wav","audioOffset":plan.audio_offset_seconds,
        "background":background,"reviewPrompt":"증발·응결·강수·집수를 순서대로 설명해 보세요." if "물" in spec.topic else "핵심 개념을 자신의 말로 다시 설명해 보세요."}
    (work/"remotion-input.json").write_text(json.dumps({"props":props,"browser":chrome,"preview":options.preview},ensure_ascii=False))
    return budget,spec,audio,external,timings,plan,fallbacks,progress,props


def render(work,options):
    resource.setrlimit(resource.RLIMIT_FSIZE,(options.max_disk_bytes,options.max_disk_bytes))
    budget,spec,audio,external,timings,plan,fallbacks,progress,props=prepare(work,options)
    try:
        runtime=json.loads((work/"remotion-runtime.json").read_text())
        if runtime.get("audit"):
            input_path=work/"remotion-input.json";data=json.loads(input_path.read_text());data["audit"]=True;data["probe_network"]=True
            input_path.write_text(json.dumps(data,ensure_ascii=False))
        run_process([executable("node"),"--preserve-symlinks","--preserve-symlinks-main",str(Path(runtime["project"])/"render.mjs"),runtime["work"]],budget,"remotion_failed")
    except RenderError as exc:
        if (work/"remotion-error.json").exists():
            detail=json.loads((work/"remotion-error.json").read_text())
            stage=detail.get("stage")
            if stage in {"bundle","csp","select","frames"}:
                raise RenderError("remotion_failed",f"Remotion {stage} 단계에 실패했어요.",budget.scene_id) from None
        raise
    frames=sorted((work/"frames").glob("frame-*.jpeg"))
    expected=spec.duration_seconds*options.fps
    if len(frames)!=expected:
        raise RenderError("frame_failed","Remotion의 출력 프레임 수를 확인하지 못했어요.")
    # Remotion controls visuals and Studio audio. Reuse the existing FFmpeg
    # audio path for export, retaining original speech and exact padding policy.
    progress(None,"encode",frames_done=expected,frames_total=expected)
    output=work/"result.mp4"
    padding=len(frames[0].stem.split('-')[-1])
    run_process([executable("ffmpeg"),"-nostdin","-v","error","-y","-protocol_whitelist","file,pipe",
        "-framerate",str(options.fps),"-i",str(work/"frames"/f"frame-%0{padding}d.jpeg"),"-i",str(audio),
        "-map","0:v:0","-map","1:a:0","-vf","scale=in_range=auto:out_range=tv,setparams=range=limited",
        "-af",f"adelay={round(plan.audio_offset_seconds*1000)},apad,atrim=duration={spec.duration_seconds}",
        "-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-color_range","tv",
        "-c:a","aac","-b:a","128k","-ar","48000","-t",str(spec.duration_seconds),"-movflags","+faststart","-map_metadata","-1",str(output)],budget,"encode_failed")
    progress(None,"verify",frames_done=expected,frames_total=expected)
    info=verify_media(probe(output,budget),spec,options)
    run_process([executable("ffmpeg"),"-nostdin","-v","error","-xerror","-i",str(output),"-f","null","-"],budget,"decode_failed")
    frame_report=json.loads((work/"remotion-frame-report.json").read_text())
    if frame_report["blocked_requests"] and not runtime.get("audit"):
        raise RenderError("network_blocked","허용되지 않은 네트워크 요청이 발생했어요.")
    report={"renderer_version":"remotion-4.0.545-water-1","schema_version":spec.schema_version,"media":info,
        "frame_count":expected,"capture_size":list(options.size),"layout":{"fallbacks":{f.get("scene_id",f.get("component")):f["reason"] for f in fallbacks},"blocked_requests":frame_report["blocked_requests"],"checks":frame_report["layout"]},
        "tts_engine":"chatkhu-approved-local-audio" if external else MacOSSay.name,"narration":timings,"decoded":True,
        "timing_source":plan.timing_source,"audio_offset_seconds":plan.audio_offset_seconds,"animation_scenes":[s.model_dump() for s in plan.scenes],
        "external_api_calls":0,"frame_audit":frame_report.get("audit",[]),"sha256":hashlib.sha256(output.read_bytes()).hexdigest()}
    (work/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
