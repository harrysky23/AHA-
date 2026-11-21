"""Explicit local rendering only. No AI/provider calls or .env loading."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.providers.base import StoryboardInput
from backend.app.rendering.core import RenderError, RenderOptions
from backend.app.rendering.engine import render_storyboard
from backend.app.services.materials import MaterialContext
from backend.app.services.storyboard_mock import generate_mock_storyboard
from backend.app.services.validation import load_json

CONCEPTS = {"math": "미분계수의 기하학적 의미", "science": "물의 순환", "social": "수요와 공급", "cs": "이진 탐색 알고리즘"}


def main():
    parser = argparse.ArgumentParser(description="검증된 스토리보드를 로컬 한국어 TTS + HTML/SVG + FFmpeg로 렌더링")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="StoryboardSpec JSON 파일 또는 /api/storyboard의 JSON 응답")
    source.add_argument("--mock", choices=CONCEPTS, help="API 호출 없는 합성 스토리보드")
    source.add_argument("--all-mocks", action="store_true", help="합성 예제 네 개를 순서대로 렌더링")
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/videos", help="입력 하나면 .mp4 경로, 여러 예제면 디렉터리")
    parser.add_argument("--preview", action="store_true", help="540×960; 기본 1080×1920")
    parser.add_argument("--fps", type=int, default=30, help="개발 검증 권장 3~6; 기본30")
    parser.add_argument("--duration", type=int, choices=range(30, 61), default=45, metavar="30..60", help="mock 목표 길이")
    parser.add_argument("--timeout", type=int, default=600, help="영상 하나의 최대 처리 시간(초)")
    parser.add_argument("--max-disk-mb", type=int, default=512, help="작업 하나의 임시 파일 합계 상한")
    parser.add_argument("--media-plan", type=Path, help="승인·검토된 로컬 미디어 계획 JSON; 추가 API 호출 없음")
    parser.add_argument("--asset-root", type=Path, help="미디어 계획의 파일명이 위치한 운영자 지정 디렉터리")
    parser.add_argument("--renderer",choices=["svg","remotion"],default="svg")
    parser.add_argument("--animation-plan",type=Path,help="명시적인 Remotion 장면·자막 시간 JSON")
    args = parser.parse_args()
    try:
        options = RenderOptions(preview=args.preview, fps=args.fps, timeout_seconds=args.timeout, max_disk_bytes=args.max_disk_mb*1024**2)
        media_plan = None
        animation_plan = None
        if args.animation_plan:
            if args.renderer!="remotion" or args.animation_plan.stat().st_size>128*1024:
                parser.error("--animation-plan에는 remotion 렌더러와 최대128KiB 계획이 필요해요.")
            animation_plan=load_json(args.animation_plan.read_text())
        if args.media_plan:
            if not args.input or not args.asset_root or args.media_plan.stat().st_size > 128*1024:
                parser.error("--media-plan에는 단일 --input과 --asset-root가 필요하며 계획은 최대128KiB예요.")
            media_plan = load_json(args.media_plan.read_text(encoding="utf-8"))
        if args.input:
            if args.input.stat().st_size > 128*1024:
                raise RenderError("input_too_large", "스토리보드 파일은 최대 128KiB예요.")
            data = load_json(args.input.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise RenderError("invalid_storyboard", "스토리보드 입력은 JSON 객체여야 해요.")
            jobs = [("storyboard", data.get("storyboard", data))]
        else:
            keys = list(CONCEPTS) if args.all_mocks else [args.mock]
            jobs = [(key, generate_mock_storyboard(StoryboardInput(CONCEPTS[key], "핵심 관계를 설명해 주세요.",
                      MaterialContext(), args.duration)).model_dump()) for key in keys]
        for name, data in jobs:
            output = args.output / f"{name}.mp4" if args.output.suffix.lower() != ".mp4" else args.output
            if len(jobs) > 1 and args.output.suffix.lower() == ".mp4":
                parser.error("여러 예제는 출력 디렉터리를 지정해 주세요.")
            print(json.dumps({"event": "start", "example": name, "resolution": options.size, "fps": options.fps}), flush=True)
            report = render_storyboard(data, output, options, media_plan=media_plan, asset_root=args.asset_root,
                                       renderer=args.renderer,animation_plan=animation_plan)
            print(json.dumps({"event": "complete", "output": str(output), "media": report["media"],
                              "fallbacks": report["layout"]["fallbacks"], "decoded": report["decoded"]}, ensure_ascii=False), flush=True)
        return 0
    except RenderError as exc:
        print(json.dumps({"event": "error", **exc.as_dict()}, ensure_ascii=False), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"event": "error", "code": "cancelled", "message": "로컬 렌더링을 중단하고 임시 파일을 정리했어요."}, ensure_ascii=False), file=sys.stderr)
        return 130
    except (OSError, ValueError, RecursionError):
        print(json.dumps({"event": "error", "code": "invalid_local_input", "message": "로컬 입력 파일과 실행 옵션을 확인해 주세요."}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
