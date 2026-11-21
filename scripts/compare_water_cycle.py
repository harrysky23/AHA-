"""Offline A/B/C comparison using the three ALREADY approved local receipts.

Never loads .env or calls any provider. Missing/changed media uses SVG/local TTS.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.providers.base import StoryboardInput
from backend.app.providers.chatkhu.requests import NARRATION
from backend.app.rendering.engine import render_storyboard
from backend.app.rendering.core import RenderOptions, RenderError
from backend.app.services.materials import MaterialContext
from backend.app.services.storyboard_mock import generate_mock_storyboard
from backend.app.services.multimodal import create_media_plan
from backend.app.storyboard_schema import StoryboardSpec


def water_storyboard():
    data=generate_mock_storyboard(StoryboardInput("물의 순환","증발·응결·강수의 관계",MaterialContext(),30)).model_dump()
    data["scenes"]=data["scenes"][:3]
    sentences=NARRATION.split(". ")
    for index,scene in enumerate(data["scenes"]):
        scene.update(start_seconds=[0.,8.,16.][index],end_seconds=[8.,16.,30.][index],
            narration_ko=sentences[index]+("." if index<2 else ""))
        scene["screen"]={"title":"태양과 물, 순환으로 연결해요","bullets":["증발 → 응결 → 강수 → 유출·집수"],"formulas":[]}
    data["limitations"]=["증산·침투·지하수 저장을 생략한 기본 모형이며 배경 영상은 정확한 과학 도식이 아니에요.",
        "외부 음성 자막은 측정 길이에 따른 글자 수 배분이며 단어 단위 정렬이 아니에요."]
    return StoryboardSpec.model_validate(data)


def official_accounting(events):
    # Later polls may omit a previously reported charge; never add repeated fees.
    return {key:next((e[key] for e in reversed(events) if e.get(key) is not None),None)
            for key in ["credits_charged","input_tokens","output_tokens"]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"tmp/chatkhu/comparison/final")
    parser.add_argument("--receipts",type=Path,default=ROOT/"tmp/chatkhu")
    parser.add_argument("--prepare-only",action="store_true")
    parser.add_argument("--preview",action="store_true")
    parser.add_argument("--fps",type=int,default=3)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True,mode=0o700)
    root=args.output/"assets";root.mkdir(exist_ok=True,mode=0o700)
    spec=water_storyboard()
    (args.output/"storyboard.json").write_text(spec.model_dump_json(indent=2))
    assets={};costs={};source_times={}
    for kind,suffix in [("image","jpg"),("video","mp4"),("tts","wav")]:
        receipt=args.receipts/kind/"result.json"
        if not receipt.exists():continue
        data=json.loads(receipt.read_text());source=Path(data["path"])
        if not source.is_file() or source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest()!=data["sha256"]:
            continue
        if kind=="tts":
            # Bind the actual approved transcript, not just the current fixture.
            original=json.loads((args.receipts/kind/"plan.json").read_text())
            if original.get("request",{}).get("input")!=" ".join(s.narration_ko for s in spec.scenes):
                continue
        name=f"{kind}.{suffix}";shutil.copyfile(source,root/name);(root/name).chmod(0o600)
        assets[kind]={"id":kind,"kind":"audio" if kind=="tts" else kind,"filename":name,"sha256":data["sha256"],
                      "review":"background_only" if kind=="tts" else "requires_mask"}
        costs[kind]=official_accounting(data["accounting"])
        source_times[kind]=data["elapsed_seconds"]
    summary={"external_api_calls_this_run":0,"source_accounting":costs,"source_elapsed_seconds":source_times,
             "known_reported_credits_subtotal":sum(c["credits_charged"] for c in costs.values() if c["credits_charged"] is not None),
             "accounting_note":"기존 결과 재사용. 미반환 차감액은 미확인으로 두며 부분 합계를 전체 비용으로 표시하지 않아요.", "results":[]}
    for variant in "ABC":
        chosen=[];modes={};narration=None
        if variant!="A":
            chosen=[assets[k] for k in (["image"] if variant=="B" else ["image","video","tts"]) if k in assets]
            for i,scene in enumerate(spec.scenes):
                kind="video" if variant=="C" and i>0 and "video" in assets else "image"
                if kind in assets:
                    modes[scene.id]={"mode":"ai_video" if kind=="video" else "ai_image_motion","asset_id":kind,"framing":"water_cycle_crops"}
            if variant=="C" and "tts" in assets:narration="tts"
        plan=create_media_plan(spec,chosen,modes,narration_id=narration)
        (args.output/f"{variant}-plan.json").write_text(plan.model_dump_json(indent=2))
        if args.prepare_only:continue
        output=args.output/f"{variant}.mp4"
        if output.exists():
            raise ValueError("출력 파일이 존재해요. 다른 --output 디렉터리를 사용해 주세요.")
        start=time.monotonic()
        report=render_storyboard(spec,output,RenderOptions(preview=args.preview,fps=args.fps),media_plan=plan,asset_root=root)
        entry={"variant":variant,"file":output.name,"render_seconds":round(time.monotonic()-start,3),
               "media":report["media"],"decoded":report["decoded"],"multimodal":report["multimodal"]}
        summary["results"].append(entry)
        (args.output/"comparison.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
        print(json.dumps(entry,ensure_ascii=False),flush=True)
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except RenderError as exc:
        print(json.dumps(exc.as_dict(),ensure_ascii=False),file=sys.stderr);raise SystemExit(1)
