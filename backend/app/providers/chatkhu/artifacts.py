"""Bounded local media inspection. Remote URLs never reach a media decoder."""
from pathlib import Path
import tempfile
import wave

from ...rendering.core import Budget, RenderError, RenderOptions, executable, run_process
from .contracts import ChatKHUError


def validate_media(path: Path, kind: str):
    budget = Budget(path.parent, RenderOptions(timeout_seconds=30, min_free_bytes=32*1024**2))
    try:
        # Use an explicit protocol allowlist even though input is a local path.
        raw = run_process([executable("ffprobe"), "-v", "error", "-protocol_whitelist", "file,pipe",
            "-show_streams", "-show_format", "-of", "json", str(path)], budget, "probe_failed")
        from ...services.validation import load_json
        info = load_json(raw)
        video = [s for s in info["streams"] if s.get("codec_type") == "video"]
        audio = [s for s in info["streams"] if s.get("codec_type") == "audio"]
        if kind in {"image", "video"}:
            stream = video[0]
            width, height = stream["width"], stream["height"]
            if len(video) != 1 or not 0 < width <= 4096 or not 0 < height <= 4096 or width*height > 16_777_216:
                raise ValueError()
            if kind == "image" and (audio or stream["codec_name"] not in {"png", "mjpeg", "webp"}):
                raise ValueError()
            result = {"width":width, "height":height, "aspect_ratio":round(width/height,6), "video_codec":stream["codec_name"]}
            if kind == "video":
                duration = float(info["format"]["duration"])
                if not 0 < duration <= 60:
                    raise ValueError()
                result["duration_seconds"] = duration
        else:
            stream = audio[0]
            duration = float(info["format"]["duration"])
            if video or len(audio) != 1 or stream["codec_name"] != "pcm_s16le" or stream["channels"] != 1 or int(stream["sample_rate"]) != 24000 or not 0 < duration <= 120:
                raise ValueError()
            result = {"audio_codec":"pcm_s16le", "channels":1, "sample_rate":24000, "duration_seconds":duration}
        # Inspect actual decoding too. Image frame limit prevents animation input.
        command = [executable("ffmpeg"), "-nostdin", "-v", "error", "-xerror", "-protocol_whitelist", "file,pipe", "-threads", "1", "-i", str(path)]
        if kind == "image":
            command += ["-frames:v", "1"]
        run_process(command+["-f", "null", "-"], budget, "decode_failed")
        return result
    except (RenderError, ValueError, KeyError, TypeError, IndexError):
        raise ChatKHUError("invalid_media", "결과 미디어의 크기·길이·코덱·디코딩을 확인하지 못했어요. 렌더러에 전달하지 않아요.") from None


def media_suffix(raw, kind):
    if kind == "image":
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):return ".png"
        if raw.startswith(b"\xff\xd8\xff"):return ".jpg"
        if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":return ".webp"
    elif kind == "video":
        if len(raw)>12 and raw[4:8] == b"ftyp":return ".mp4"
    elif kind == "tts":
        if raw and not raw.startswith((b"RIFF",b"ID3",b"OggS")) and len(raw)%2 == 0 and len(raw) <= 120*24000*2:return ".wav"
    raise ChatKHUError("invalid_media", "문서에 정의된 이미지·MP4·PCM 형식이 아니에요.")


def save_media(raw, kind, output: Path, inspect=validate_media):
    suffix = media_suffix(raw, kind)
    output = output.with_suffix(suffix)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.exists():
        raise ChatKHUError("output_exists", "기존 미디어를 덮어쓰지 않아요. 다른 출력 경로를 사용해 주세요.")
    with tempfile.TemporaryDirectory(prefix=".chatkhu-", dir=output.parent) as directory:
        staged = Path(directory)/("asset"+suffix)
        if kind == "tts":
            with wave.open(str(staged), "wb") as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000);wav.writeframes(raw)
        else:
            staged.write_bytes(raw)
        metadata = inspect(staged, kind)
        # No partially validated output is published. Same-filesystem no-overwrite.
        import os
        staged.chmod(0o600)
        os.link(staged, output)
        return output, metadata
