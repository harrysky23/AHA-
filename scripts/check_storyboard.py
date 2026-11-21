"""Default: offline mock validation. Real Gemini requires the explicit --live flag."""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from backend.app.config import ConfigurationError, Settings, get_settings
from backend.app.services.errors import LearningError
from backend.app.services.storyboard import create_storyboard

CONCEPTS={"math":"미분계수의 기하학적 의미","science":"물의 순환","social":"수요와 공급","cs":"이진 탐색 알고리즘"}


async def run(args) -> int:
    settings=Settings()
    if args.live:
        try:
            settings=get_settings()
            if settings.mode!="gemini":
                raise ConfigurationError("실제 검증은 AHA_AI_PROVIDER=gemini 설정이 필요해요.")
            settings.validate_gemini()
            settings=replace(settings,cache_ttl_seconds=0)
        except ConfigurationError as exc:
            print("실제 호출 미실행: "+str(exc));return 2
        print("명시적 실제 Gemini 검증: 비식별 합성 질문만 사용하며 API 할당량을 소비합니다. 자동 재시도하지 않습니다.")
    else:
        print("mock 검증: .env의 실제 Provider 설정과 관계없이 외부 API를 호출하지 않습니다.")
    keys=list(CONCEPTS) if args.all else [args.concept]
    for key in keys:
        try:
            result=await create_storyboard(settings,CONCEPTS[key],"핵심 원리를 시각적으로 설명해 주세요.",None,None,args.duration,args.level)
            story=result["storyboard"]
            print(json.dumps({"concept":CONCEPTS[key],"mode":result["mode"],"model":result["generation"]["model"],
                "schema_version":story["schema_version"],"duration_seconds":story["duration_seconds"],
                "visualizations":[scene["visualization"]["type"] for scene in story["scenes"]],
                "validation":result["verification"],"usage":result["generation"]["usage"]},ensure_ascii=False))
            if args.json:
                print(json.dumps(story,ensure_ascii=False,indent=2))
        except LearningError as exc:
            print(f"검증 실패 ({exc.code}): {exc.message}")
            if exc.upstream_status is not None:print(f"Google HTTP status: {exc.upstream_status}")
            if exc.upstream_message:print("Google error message (key redacted): "+exc.upstream_message)
            return 1
    return 0


if __name__=="__main__":
    parser=argparse.ArgumentParser(description="스토리보드 검증. 기본 mock; --live만 실제 Gemini를 호출합니다.")
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--all",action="store_true",help="네 가지 합성 개념을 각각 검증. --live와 함께 쓰면 최대4회 실제 호출")
    parser.add_argument("--concept",choices=CONCEPTS,default="math")
    parser.add_argument("--duration",type=int,choices=range(30,61),default=45,metavar="30..60")
    parser.add_argument("--level",choices=["foundation","high_school","advanced"],default="high_school")
    parser.add_argument("--json",action="store_true",help="검증된 JSON을 stdout에 표시. 파일·영상은 저장하지 않음")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
