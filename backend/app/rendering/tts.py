"""Replaceable offline speech adapter. Never runs a command from a storyboard."""
from pathlib import Path
import math
import platform
from typing import Callable, Protocol

from .core import Budget, RenderError, executable, probe, run_process


class TTSEngine(Protocol):
    name: str

    def synthesize(self, text: str, output: Path, budget: Budget) -> None: ...


class MacOSSay:
    name = "macos-say-yuna-185"

    def synthesize(self, text: str, output: Path, budget: Budget) -> None:
        if platform.system() != "Darwin":
            raise RenderError("tts_unavailable", "기본 한국어 TTS는 macOS의 로컬 Yuna 음성이 필요해요.", budget.scene_id)
        # Neutralize macOS embedded speech control delimiters. DSL narration is
        # plain spoken text, never a way to change rate/voice or inject silence.
        spoken = text.replace("[[", "［［").replace("]]", "］］")
        # stdin keeps narration out of process arguments. No voice download/API.
        run_process([executable("say"), "-v", "Yuna", "-r", "185", "-o", str(output)],
                    budget, "tts_failed", input_data=spoken.encode("utf-8"))
        if not output.exists() or output.stat().st_size < 128:
            raise RenderError("tts_failed", "한국어 음성 파일이 생성되지 않았어요.", budget.scene_id)


def fit_ratio(raw_seconds: float, scene_seconds: float) -> float:
    """Keep 150ms trailing silence; never crop spoken words or alter scenes."""
    available = scene_seconds - .15
    if not math.isfinite(raw_seconds) or not math.isfinite(scene_seconds) or raw_seconds <= 0 or available <= 0:
        raise RenderError("tts_failed", "음성 길이를 확인할 수 없어요.")
    ratio = max(1., raw_seconds / available)
    if ratio > 1.35:
        raise RenderError("narration_too_long", "내레이션이 장면보다 너무 길어요. 문장을 줄이거나 장면 시간을 늘려 주세요.")
    return ratio


def build_narration(spec, work: Path, budget: Budget, engine: TTSEngine,
                    on_scene: Callable[[str], None] | None = None) -> tuple[Path, list[dict]]:
    ffmpeg = executable("ffmpeg")
    entries = []
    paths = []
    for index, scene in enumerate(spec.scenes):
        budget.scene_id = scene.id
        if on_scene:
            on_scene(scene.id)
        raw = work / f"voice-{index}.aiff"
        fitted = work / f"voice-{index}.wav"
        engine.synthesize(scene.narration_ko, raw, budget)
        info = probe(raw, budget)
        try:
            duration = float(info["format"]["duration"])
            ratio = fit_ratio(duration, scene.end_seconds - scene.start_seconds)
        except RenderError as exc:
            exc.scene_id = scene.id
            raise
        except (KeyError, TypeError, ValueError):
            raise RenderError("tts_failed", "음성 길이를 확인할 수 없어요.", scene.id) from None
        length = scene.end_seconds - scene.start_seconds
        run_process([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(raw),
                     "-af", f"atempo={ratio:.8f},apad,atrim=duration={length:.1f},asetpts=PTS-STARTPTS",
                     "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(fitted)], budget, "audio_fit_failed")
        entries.append({"scene_id": scene.id, "raw_seconds": round(duration, 3), "scene_seconds": round(length, 1),
                        "tempo": round(ratio, 6), "policy": "pad_silence" if ratio == 1 else "tempo_then_pad"})
        paths.append(fitted)
        raw.unlink()
    # Generated local filenames only; the concat file cannot contain user paths.
    listing = work / "audio-list.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in paths), encoding="utf-8")
    output = work / "narration.wav"
    run_process([ffmpeg, "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "1", "-i", str(listing),
                 "-c:a", "copy", str(output)], budget, "audio_concat_failed")
    for path in paths:
        path.unlink()
    return output, entries
