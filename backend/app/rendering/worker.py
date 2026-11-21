"""Private worker. Parent enforces wall time/disk quota and kills process group."""
import hashlib
import json
from pathlib import Path
import resource
import sys

from ..storyboard_schema import StoryboardSpec
from ..services.validation import load_json
from .browser import FrameRenderer
from .core import Budget, RenderError, RenderOptions, executable, probe, run_process
from .tts import MacOSSay, build_narration


def verify_media(info: dict, spec: StoryboardSpec, options: RenderOptions) -> dict:
    try:
        videos = [s for s in info["streams"] if s["codec_type"] == "video"]
        audios = [s for s in info["streams"] if s["codec_type"] == "audio"]
        v, a = videos[0], audios[0]
        width, height = options.size
        duration = float(info["format"]["duration"])
        audio_duration = float(a["duration"])
        video_duration = float(v["duration"])
        fps_n, fps_d = map(int, v["avg_frame_rate"].split("/"))
        if not (len(videos) == len(audios) == 1 and v["codec_name"] == "h264" and a["codec_name"] == "aac"
                and (v["width"], v["height"]) == (width, height) and v["pix_fmt"] == "yuv420p"
                and abs(fps_n/fps_d-options.fps) < .001
                and all(abs(t-spec.duration_seconds) <= .1 for t in [duration, audio_duration, video_duration])):
            raise ValueError()
        return {"video_codec": "h264", "audio_codec": "aac", "pixel_format": "yuv420p", "width": width, "height": height,
                "fps": options.fps, "duration_seconds": duration, "audio_seconds": audio_duration, "video_seconds": video_duration,
                "audio_channels": a["channels"], "audio_sample_rate": int(a["sample_rate"])}
    except (ValueError, KeyError, TypeError, IndexError, ZeroDivisionError):
        raise RenderError("invalid_mp4", "출력 영상의 길이·해상도·음성 형식을 검증하지 못했어요.") from None


def render(work: Path, options: RenderOptions):
    # Per-file hard limit complements the parent's aggregate directory monitor.
    resource.setrlimit(resource.RLIMIT_FSIZE, (options.max_disk_bytes, options.max_disk_bytes))
    budget = Budget(work, options)
    spec = StoryboardSpec.model_validate(load_json((work / "input.json").read_text(encoding="utf-8")))
    def progress(scene_id, phase):
        # Atomic replace avoids exposing partial JSON to the parent on failure.
        p = work / "progress.tmp"
        p.write_text(json.dumps({"scene_id": scene_id, "phase": phase}), encoding="utf-8")
        p.replace(work / "progress.json")
    audio, timings = build_narration(spec, work, budget, MacOSSay(), lambda scene_id: progress(scene_id, "tts"))
    frames = work / "frames"
    frames.mkdir()
    frame_count = spec.duration_seconds * options.fps
    budget.scene_id = None
    progress(None, "browser")
    with FrameRenderer(spec, budget) as renderer:
        for index in range(frame_count):
            seconds = index/options.fps
            scene = next(s for s in spec.scenes if s.start_seconds <= seconds < s.end_seconds)
            budget.scene_id = scene.id
            progress(scene.id, "frames")
            png, state = renderer.frame(seconds)
            (frames / f"{index:06d}.png").write_bytes(png)
            budget.check()
        layout = renderer.layout
        layout["fallbacks"] = state["fallbacks"]
        layout["blocked_requests"] = renderer.blocked_requests
    progress(None, "encode")
    budget.scene_id = None
    output = work / "result.mp4"
    # Only fixed generated paths/validated numbers are passed to FFmpeg.
    run_process([executable("ffmpeg"), "-nostdin", "-v", "error", "-y", "-framerate", str(options.fps),
                 "-i", str(frames / "%06d.png"), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
                 "-vf", f"scale={options.size[0]}:{options.size[1]}:flags=lanczos",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-t", str(spec.duration_seconds),
                 "-movflags", "+faststart", "-map_metadata", "-1", str(output)], budget, "encode_failed")
    media = verify_media(probe(output, budget), spec, options)
    # Decode the entire result, not just inspect the container headers.
    run_process([executable("ffmpeg"), "-nostdin", "-v", "error", "-xerror", "-i", str(output),
                 "-f", "null", "-"], budget, "decode_failed")
    report = {"renderer_version": "html-svg-1", "schema_version": spec.schema_version,
              "media": media, "frame_count": frame_count, "capture_size": [1080, 1920], "layout": layout, "tts_engine": MacOSSay.name,
              "narration": timings, "decoded": True,
              "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
    (work / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    work = Path(sys.argv[1])
    try:
        options = RenderOptions(**json.loads((work / "options.json").read_text()))
        render(work, options)
    except RenderError as exc:
        (work / "error.json").write_text(json.dumps(exc.as_dict(), ensure_ascii=False))
        raise SystemExit(1)
    except Exception:
        # Do not leak tracebacks, credentials, original JSON or command arguments.
        (work / "error.json").write_text(json.dumps({"code": "render_failed", "message": "로컬 렌더링 처리에 실패했어요.", "scene_id": None}))
        raise SystemExit(1)
