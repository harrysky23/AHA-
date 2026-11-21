"""Explicit live Gemini check with synthetic questions; never logs prompts or keys."""
import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from backend.app.config import ConfigurationError, get_settings
from backend.app.services.errors import LearningError
from backend.app.services.lessons import create_learning


async def run(compare: bool) -> int:
    try:
        settings=get_settings()
        if settings.mode != 'gemini':
            print('실제 호출 미실행: AHA_AI_PROVIDER=gemini를 설정해 주세요.')
            return 2
        settings.validate_gemini()
        # This explicit diagnostic must prove a new call, not count a cache hit as one.
        settings=replace(settings,cache_ttl_seconds=0)
        questions=['h=0을 바로 대입하면 왜 할선 기울기를 구할 수 없나요?']
        if compare:questions.append('음수 h에서 왼쪽으로 접근해도 기울기가 2로 수렴하나요?')
        evidence=[];explanations=[]
        for question in questions:
            result=await create_learning(settings,'미분계수의 기하학적 의미',question,None,None)
            explanations.append(result['lesson']['spec']['explanation'])
            evidence.append({'request_id':result['generation']['request_id'],'provider':result['mode'],
                'model':result['generation']['model'],'usage':result['generation']['usage'],
                'numeric_checks':result['verification']['numeric_checks'],
                'explanation_sha256':hashlib.sha256(explanations[-1].encode()).hexdigest()})
        changed=len(set(explanations))>1 if compare else None
        target=ROOT/'tmp/gemini-live-check.json';target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps({'timestamp_utc':datetime.now(timezone.utc).isoformat(),
            'actual_api_calls':len(evidence),'question_change_checked':compare,'explanations_differ':changed,'results':evidence},ensure_ascii=False,indent=2))
        print(f'Gemini 실제 호출 {len(evidence)}회 및 JSON·수학 검증 성공. 기록: {target}')
        if compare and not changed:
            print('두 질문의 설명이 동일하므로 질문 변경 검증은 미충족입니다.')
            return 1
        return 0
    except ConfigurationError as exc:
        print('실제 호출 미실행: '+str(exc))
        return 2
    except LearningError as exc:
        print(f'실제 호출 검증 실패 ({exc.code}): {exc.message}')
        if exc.upstream_status is not None:
            print(f'Google HTTP status: {exc.upstream_status}')
        if exc.upstream_message:
            print('Google error message (key redacted): '+exc.upstream_message)
        return 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='합성 질문으로 실제 Gemini 호출을 검증합니다. 무료 할당량을 사용하며, 유료 프로젝트 키는 과금될 수 있습니다.')
    parser.add_argument('--compare',action='store_true',help='합성 질문 2개를 보내 설명 변화도 확인 (기본 1개)')
    raise SystemExit(asyncio.run(run(parser.parse_args().compare)))
