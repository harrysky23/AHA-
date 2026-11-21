"""Offline artifact staging, cropping and narration. No API/provider calls here."""
import hashlib
import json
import math
import os
from pathlib import Path
import stat

from pydantic import ValidationError

from ..multimodal_schema import MediaPlan, narration_digest
from .core import Budget, RenderError, executable, probe, run_process
from .tts import fit_ratio


def parse_media_plan(value, spec):
    try:
        data = value.model_dump() if isinstance(value, MediaPlan) else value
        return MediaPlan.model_validate(data).bind(spec)
    except (ValueError, TypeError, ValidationError):
        raise RenderError("invalid_media_plan", "미디어 계획의 형식·장면·명세 연결을 확인하지 못했어요.") from None


def stage_media(plan, root, work, budget, cancel_event=None):
    """Trusted caller supplies root; generated JSON may reference basenames only."""
    target = work / "assets"
    target.mkdir(mode=0o700)
    failures = {}
    total = 0
    for asset in plan.assets:
        try:
            if root is None or asset.review == "rejected":
                raise ValueError()
            source = Path(root) / asset.filename
            # No symlinks or URLs, including the caller-provided root itself.
            if Path(root).is_symlink() or source.is_symlink():
                raise ValueError()
            fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd,"rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 100*1024**2:
                    raise ValueError()
                total += info.st_size
                if total > 256*1024**2:
                    raise ValueError()
                destination = target / asset.filename
                digest = hashlib.sha256()
                with destination.open("wb") as output:
                    while chunk := stream.read(1024**2):
                        if cancel_event is not None and cancel_event.is_set():
                            raise RenderError("render_cancelled", "영상 생성을 취소했어요.")
                        output.write(chunk);digest.update(chunk);budget.check()
                        if output.tell()>100*1024**2:
                            raise ValueError()
                destination.chmod(0o600)
                if digest.hexdigest() != asset.sha256:
                    destination.unlink();raise ValueError()
        except (OSError, ValueError):
            failures[asset.id] = "asset_missing_unreviewed_or_hash_mismatch"
    (work / "media-plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    (work / "asset-failures.json").write_text(json.dumps(failures), encoding="utf-8")


def prepare_assets(plan, work, budget):
    from ..providers.chatkhu.artifacts import validate_media
    from ..providers.chatkhu.contracts import ChatKHUError
    failed = json.loads((work / "asset-failures.json").read_text())
    metadata = {}
    for asset in plan.assets:
        if asset.id in failed:
            continue
        try:
            path = work / "assets" / asset.filename
            metadata[asset.id] = validate_media(path, "tts" if asset.kind == "audio" else asset.kind)
            budget.check()
        except ChatKHUError:
            failed[asset.id] = "asset_decode_failed"
    return metadata, failed


def resolve_scenes(spec, plan, failed):
    entries = {entry.scene_id: entry.model_dump() for entry in plan.scenes}
    fallbacks = []
    for scene in spec.scenes:
        entry = entries[scene.id]
        reason = None
        if scene.visualization.type in {"function_graph", "state_transition"} and entry["mode"] != "svg_animation":
            reason = "exact_diagram_requires_svg"
        elif entry["asset_id"] in failed:
            reason = failed[entry["asset_id"]]
        if reason:
            fallbacks.append({"scene_id":scene.id,"reason":reason,"from":entry["mode"],"to":"svg_animation"})
            entry.update(mode="svg_animation",asset_id=None)
    return entries, fallbacks


def external_narration(spec, plan, work, budget, metadata, failed):
    if not plan.narration:
        return None, None
    request = plan.narration
    if request.asset_id in failed:
        return None, failed[request.asset_id]
    if request.transcript_sha256 != narration_digest(spec):
        return None, "narration_transcript_mismatch"
    asset = next(a for a in plan.assets if a.id == request.asset_id)
    try:
        duration = metadata[asset.id]["duration_seconds"]
        ratio = fit_ratio(duration, spec.duration_seconds)
        output = work / "narration.wav"
        run_process([executable("ffmpeg"),"-nostdin","-v","error","-y","-protocol_whitelist","file,pipe",
            "-i",str(work/"assets"/asset.filename),"-af",f"atempo={ratio:.8f},apad,atrim=duration={spec.duration_seconds},asetpts=PTS-STARTPTS",
            "-ar","48000","-ac","1","-c:a","pcm_s16le",str(output)],budget,"audio_fit_failed")
        return {"path":output,"spoken_seconds":duration/ratio,"tempo":ratio,"source":"approved_local_chatkhu_wav"}, None
    except RenderError as exc:
        if exc.code in {"render_timeout","disk_limit","disk_full","render_cancelled"}:
            raise
        return None, exc.code


def subtitle_at(spec, seconds, spoken_seconds, review_prompt):
    # Approximate character-time captions over the *measured* voice interval.
    # No claim of forced alignment or sentence boundary detection.
    if seconds >= spoken_seconds:
        return review_prompt
    parts = []
    for scene in spec.scenes:
        text = scene.narration_ko
        while len(text)>62:
            cut=text.rfind(" ",0,62)
            if cut<28:cut=62
            parts.append(text[:cut]);text=text[cut:].lstrip()
        parts.append(text)
    cursor = seconds/spoken_seconds*sum(len(p)for p in parts)
    for part in parts:
        cursor -= len(part)
        if cursor < 0:
            return part
    return parts[-1]


def crop_filters(framing, width=1080, height=1920):
    """Fixed reviewed windows. The centre containing AI labels never enters frames."""
    if framing == "water_cycle_crops":
        return (
            "[0:v]split=2[h][f];"
            f"[h]crop=iw:trunc(ih*0.30/2)*2:0:0,scale={width}:580:force_original_aspect_ratio=increase,crop={width}:580[head];"
            f"[f]crop=iw:trunc(ih*0.20/2)*2:0:ih-trunc(ih*0.20/2)*2,scale={width}:400:force_original_aspect_ratio=increase,crop={width}:400[foot];"
            f"color=c=0xf9f7ff:s={width}x{height}:r=__FPS__[base];[base][head]overlay=0:0:shortest=1[b];"
            "[b][foot]overlay=0:1520:shortest=1"
        )
    if framing == "contain":
        return f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0xf9f7ff"
    return f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"


def build_background(spec, plan, entries, work, budget, progress, fallbacks):
    paths = []
    assets = {a.id:a for a in plan.assets}
    fps = budget.options.fps
    for index, scene in enumerate(spec.scenes):
        budget.scene_id = scene.id
        progress(scene.id,"background")
        entry = entries[scene.id]
        count = math.ceil(round(scene.end_seconds*fps,6))-math.ceil(round(scene.start_seconds*fps,6))
        output = work / f"background-{index}.mp4"
        command = [executable("ffmpeg"),"-nostdin","-v","error","-y"]
        if entry["mode"].startswith("ai_"):
            asset = assets[entry["asset_id"]]
            command += (["-stream_loop","-1"] if asset.kind == "video" else ["-loop","1","-framerate",str(fps)])
            command += ["-protocol_whitelist","file,pipe","-i",str(work/"assets"/asset.filename)]
            filters = crop_filters(entry["framing"]).replace("__FPS__",str(fps))
            if entry["mode"] == "ai_image_motion":
                # Zoom only after safe cropping; never expose excluded raw pixels.
                filters += f",zoompan=z='1+0.035*on/{max(1,count)}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1080x1920:fps={fps}"
            filters += f",fps={fps},setsar=1,format=yuv420p[out]"
            command += ["-filter_complex",filters,"-map","[out]"]
        else:
            command += ["-f","lavfi","-i",f"color=c=0xf9f7ff:s=1080x1920:r={fps}"]
        command += ["-an","-frames:v",str(count),"-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p",str(output)]
        try:
            run_process(command,budget,"background_failed")
        except RenderError as exc:
            if exc.code in {"render_timeout","disk_limit","disk_full","render_cancelled"}:
                raise
            fallbacks.append({"scene_id":scene.id,"reason":exc.code,"from":entry["mode"],"to":"svg_animation"})
            entry.update(mode="svg_animation",asset_id=None)
            run_process([executable("ffmpeg"),"-nostdin","-v","error","-y","-f","lavfi","-i",f"color=c=0xf9f7ff:s=1080x1920:r={fps}",
                "-an","-frames:v",str(count),"-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p",str(output)],budget,"background_failed")
        paths.append(output)
    listing = work/"background-list.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in paths))
    result = work/"background.mp4"
    run_process([executable("ffmpeg"),"-nostdin","-v","error","-y","-f","concat","-safe","1","-i",str(listing),"-c:v","copy",str(result)],budget,"background_failed")
    for path in paths:path.unlink()
    return result
