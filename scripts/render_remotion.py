"""Recreate the approved C.mp4 lesson with local Remotion. No AI/API calls."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.multimodal_schema import MediaPlan,storyboard_digest,narration_digest
from backend.app.remotion_schema import RemotionPlan
from backend.app.rendering.core import RenderError,RenderOptions
from backend.app.rendering.engine import render_storyboard,render_slot
from backend.app.rendering.multimodal import stage_media
from backend.app.rendering.core import Budget
from backend.app.storyboard_schema import StoryboardSpec


def inputs(source,media,cues):
    spec=StoryboardSpec.model_validate_json(source.read_text())
    old=MediaPlan.model_validate_json(media.read_text()).bind(spec).model_dump()
    image=next(a for a in old["assets"] if a["kind"]=="image")
    old["assets"]=[a for a in old["assets"] if a["kind"] in {"image","audio"}]
    for entry in old["scenes"]:entry.update(mode="ai_image",asset_id=image["id"],framing="water_cycle_crops")
    media_plan=MediaPlan.model_validate(old).bind(spec)
    template=json.loads(cues.read_text())
    plan=RemotionPlan.model_validate({"schema_version":"remotion-plan-1","storyboard_sha256":storyboard_digest(spec),
        "transcript_sha256":narration_digest(spec),"audio_sha256":template["source_audio_sha256"],
        "audio_offset_seconds":template["audio_offset_seconds"],"timing_source":"reviewed_pause_cues",
        "scenes":template["scenes"],"captions":template["captions"]}).bind(spec)
    return spec,media_plan,plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    base=ROOT/"tmp/chatkhu/comparison/verified-full"
    parser.add_argument("--input",type=Path,default=base/"storyboard.json")
    parser.add_argument("--media-plan",type=Path,default=base/"C-plan.json")
    parser.add_argument("--asset-root",type=Path,default=base/"assets")
    parser.add_argument("--cues",type=Path,default=ROOT/"video-remotion/examples/water-cycle-cues.json")
    parser.add_argument("--output",type=Path,default=ROOT/"tmp/remotion/water-cycle.mp4")
    parser.add_argument("--preview",action="store_true")
    parser.add_argument("--fps",type=int,default=30)
    parser.add_argument("--audit",action="store_true",help="같은 시점 PNG·입자 좌표·외부 요청 차단을 추가 검사")
    parser.add_argument("--prepare-studio",action="store_true",help="검토된 예제만 로컬 Studio public/generated로 복사")
    args=parser.parse_args()
    if args.output.exists() and not args.prepare_studio:
        raise RenderError("output_exists","기존 출력은 덮어쓰지 않아요. 새 --output 경로를 지정해 주세요.")
    options=RenderOptions(preview=args.preview,fps=args.fps)
    spec,media,plan=inputs(args.input,args.media_plan,args.cues)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for filename,data in [("storyboard.json",spec),("media-plan.json",media),("animation-plan.json",plan)]:
        (args.output.parent/filename).write_text(data.model_dump_json(indent=2))
    if args.prepare_studio:
        from backend.app.rendering.remotion import prepare
        with render_slot(),tempfile.TemporaryDirectory(dir=args.output.parent,prefix=".aha-prepare-") as directory:
            work=Path(directory)
            (work/"input.json").write_text(spec.model_dump_json());(work/"animation-plan.json").write_text(plan.model_dump_json())
            stage_media(media,args.asset_root,work,Budget(work,options))
            *_,props=prepare(work,options)
            dest=ROOT/"video-remotion/public/generated";dest.mkdir(parents=True,exist_ok=True)
            for name in ["narration.wav","background.jpg"]:
                if (work/"public/generated"/name).exists():shutil.copyfile(work/"public/generated"/name,dest/name)
            (args.output.parent/"studio-props.json").write_text(json.dumps(props,ensure_ascii=False,indent=2))
        print(json.dumps({"studio_props":str(args.output.parent/"studio-props.json"),"external_api_calls":0}));return 0
    started=time.monotonic()
    report=render_storyboard(spec,args.output,options,renderer="remotion",media_plan=media,asset_root=args.asset_root,animation_plan=plan,audit=args.audit)
    summary={"output":str(args.output),"render_seconds":round(time.monotonic()-started,3),"media":report["media"],"decoded":report["decoded"],"external_api_calls":0}
    original=args.input.parent/"C.mp4"
    if original.is_file() and not (args.output.parent/"C-original.mp4").exists():
        shutil.copyfile(original,args.output.parent/"C-original.mp4")
    args.output.with_suffix(".comparison.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False));return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except RenderError as exc:
        print(json.dumps(exc.as_dict(),ensure_ascii=False),file=sys.stderr);raise SystemExit(1)
    except (OSError,ValueError,StopIteration):
        print(json.dumps({"code":"invalid_local_input","message":"승인된 기존 자산·명세·큐 JSON을 확인해 주세요."},ensure_ascii=False),file=sys.stderr);raise SystemExit(2)
