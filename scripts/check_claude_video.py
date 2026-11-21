"""Run one explicitly selected synthetic ChatKHU video check."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from threading import Event

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.rendering.core import RenderError, RenderOptions
from backend.app.services.generated_video import resolve_reference, run_generated_video

EXAMPLES = {
    "A": ("미분계수", "함수 y=x²에서 할선이 접선에 가까워지는 과정을 설명해 줘."),
    "B": ("수요와 공급", "수요가 증가하면 시장 균형 가격과 거래량이 왜 변하는지 설명해 줘."),
    "C": ("전자기 유도", "자석을 코일에 빠르게 움직이면 유도 기전력이 커지는 이유를 설명해 줘."),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic", choices=EXAMPLES)
    parser.add_argument("--live", action="store_true", help="ChatKHU 코드 1회, TTS 최대 1회 실행")
    parser.add_argument("--allow-repair", action="store_true", help="코드 오류 시 ChatKHU 수정 최대 1회 추가")
    parser.add_argument("--preview", action="store_true", help="540×960, 3fps")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume-draft", type=Path, help="검토한 이전 작업 초안으로 Claude 호출 없이 남은 TTS와 렌더 실행")
    args = parser.parse_args()
    concept, question = EXAMPLES[args.topic]
    if args.resume_draft and args.allow_repair:
        parser.error("--resume-draft와 --allow-repair는 함께 사용할 수 없어요.")
    if not args.live:
        print(json.dumps({"test":args.topic,"concept":concept,"code_calls":0 if args.resume_draft else 1,"tts_calls_max":1,
                          "repair_calls_max":int(args.allow_repair),"generation_started":False},ensure_ascii=False))
        return 0
    output = args.output or ROOT / "tmp" / "claude-video" / args.topic / "video.mp4"
    options = RenderOptions(preview=args.preview, fps=3 if args.preview else 30)
    reference, image, grounding = asyncio.run(resolve_reference({
        "concept":concept,"question":question,"student_level":"high_school","target_duration_seconds":30,
    }))
    try:
        draft = None
        def before_tts():
            if draft is not None:
                try:
                    with (previous / "tts-reserved").open("x") as receipt:
                        receipt.write("One TTS attempt reserved for the reviewed draft.\n")
                except FileExistsError:
                    raise RenderError("call_limit", "이 초안에 승인된 TTS 시도는 이미 사용됐어요.") from None
        if args.resume_draft:
            path = args.resume_draft.resolve()
            previous = path.parent
            expected = ROOT / "tmp" / "claude-video" / args.topic
            if previous.parent != expected or not previous.name.startswith("code-") or path.stat().st_size > 65536:
                raise RenderError("invalid_video_script", "선택한 주제의 저장된 작업 디렉터리에 검토 초안을 두어야 해요.")
            record = json.loads((previous / "report.json").read_text())
            calls = record.get("calls", [])
            if (record.get("status") != "failed"
                or not any(c.get("kind") == "code" and c.get("phase") == "accepted" for c in calls)
                or any(c.get("kind") == "tts" for c in calls)
                or record.get("tts_started")
                or not (previous / "script.json").is_file()):
                raise RenderError("call_limit", "완성된 대본을 받았고 TTS가 남아 있는 실패 작업만 재개할 수 있어요.")
            draft = json.loads(path.read_text())
        result = run_generated_video(output, options, Event(), reference, image, grounding, repair=args.allow_repair,
                                     on_stage=lambda stage: print(stage, flush=True), draft=draft, before_tts=before_tts)
    except RenderError as exc:
        print(json.dumps(exc.as_dict(), ensure_ascii=False), file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("이전 작업의 보고서와 검토한 초안 JSON을 확인해 주세요.", file=sys.stderr)
        return 1
    print(json.dumps({"path":str(output),**result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
