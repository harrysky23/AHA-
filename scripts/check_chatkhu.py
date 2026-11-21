"""Default offline plan. Generating media requires explicit request-bound approval.

No --all, retries, paid fallback, or import-time networking. See README before live use.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from backend.app.config import ConfigurationError
from backend.app.providers.chatkhu import (Approval, GatewayClient, ChatKHUError,
    ChatKHUImageProvider, ChatKHUVideoProvider, ChatKHUTTSProvider, get_chatkhu_settings)
from backend.app.providers.chatkhu.artifacts import validate_media
from backend.app.providers.chatkhu.contracts import fingerprint
from backend.app.providers.chatkhu.requests import (image_request, video_request, tts_request, public_request, PROMPT_VERSION)
from backend.app.services.validation import load_json

PROVIDERS = {"image":ChatKHUImageProvider,"video":ChatKHUVideoProvider,"tts":ChatKHUTTSProvider}
UNKNOWN = {"credits":None,"bound":"unknown","source":"no_account_quote"}


def private_json(path, data):
    staged = path.with_suffix('.tmp')
    staged.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    staged.chmod(0o600);staged.replace(path)


def prepare(settings, kind, image=None, text_only=False):
    settings.validate()
    if kind=='image':return image_request(settings)
    if kind=='tts':return tts_request(settings)
    if image is not None:
        validate_media(image,'image') # No upload until local image decoding passes.
    return video_request(settings,image,text_only=text_only)


def plan_for(kind,payload,settings):
    return {"kind":kind,"model":payload['model'],"request_hash":fingerprint(kind,payload),
        "prompt_version":PROMPT_VERSION,"request":public_request(payload),"base_url":settings.base_url.rstrip('/'),
        "planned_generation_posts":1,"actual_generation_posts":0,"automatic_retries":0,"automatic_model_switches":0,
        "max_status_gets":settings.max_polls if kind!='tts' else 0,"max_media_gets":0 if kind=='tts' else 1,
        "cost":dict(UNKNOWN),"network_called":False,
        "notice":"설정·계획만 확인했어요. 응답·생성 품질·사용 가능 여부는 아직 실제 검증하지 않았어요."}


def load_quote(path, expected_hash):
    if path is None:return dict(UNKNOWN)
    if path.stat().st_size>64*1024:raise ValueError()
    value=load_json(path.read_text(encoding='utf-8'))
    if (value.get('request_hash')!=expected_hash or value.get('action')!='preflight'
            or not 0<=time.time()-value.get('checked_at',0)<=3600):
        raise ChatKHUError('stale_quote','동일 요청에 대한 최근1시간 안의 preflight 기록이 필요해요.')
    return value['cost']


def main(argv=None):
    parser=argparse.ArgumentParser(description='ChatKHU 물의 순환 독립 검증. 기본은 네트워크 없는 계획 출력.')
    parser.add_argument('--kind',choices=PROVIDERS,default='image')
    action=parser.add_mutually_exclusive_group()
    action.add_argument('--preflight',action='store_true',help='인증된 모델 GET1회 + 무료 견적 POST1회(TTS는 견적 미지원). 생성 없음')
    action.add_argument('--live',action='store_true',help='사용자 승인 후에만 사용. 선택 종류 생성 POST 최대1회')
    action.add_argument('--resume',type=Path,help='저장한 비동기 작업의 조회/다운로드만 재개. 새 생성 없음')
    parser.add_argument('--approval-hash',help='직접 승인받은 계획의 request_hash를 그대로 지정')
    parser.add_argument('--accept-unknown-cost',action='store_true',help='최종 비용 상한 미확정 상태의 실행을 사용자가 명시적으로 승인했을 때만 지정')
    parser.add_argument('--quote-file',type=Path,help='같은 요청의 무료 preflight 기록')
    parser.add_argument('--input-image',type=Path,help='영상 참조 이미지. 실제 생성 이미지 검토 후 지정')
    parser.add_argument('--text-only',action='store_true',help='이미지 미사용 영상. 별도 승인 필요, 자동 fallback 아님')
    parser.add_argument('--output-dir',type=Path,help='결과는 프로젝트 tmp/chatkhu 아래에만 저장')
    args=parser.parse_args(argv)
    client=None;run_path=None
    try:
        settings=get_chatkhu_settings()
        print(json.dumps({'configuration':settings.public()},ensure_ascii=False))
        base=ROOT/'tmp/chatkhu'
        out=(args.output_dir or base/args.kind).resolve()
        if not out.is_relative_to(base.resolve()):
            raise ChatKHUError('invalid_output','검증 출력은 tmp/chatkhu 아래로 지정해 주세요.')
        out.mkdir(parents=True,exist_ok=True,mode=0o700)
        if args.resume:
            if args.resume.stat().st_size>16*1024:raise ValueError()
            pending=load_json(args.resume.read_text(encoding='utf-8'))
            if pending.get('kind')!=args.kind or pending.get('model')!=getattr(settings,args.kind+'_model'):
                raise ChatKHUError('resume_mismatch','원래 종류·모델 설정과 조회 재개 요청이 달라요.')
            payload=None
        else:
            try:
                payload=prepare(settings,args.kind,args.input_image,args.text_only)
            except ChatKHUError as exc:
                if exc.code=='input_image_required' and not(args.live or args.preflight):
                    print(json.dumps({'kind':'video','status':'waiting_for_approved_image','network_called':False,'detail':exc.message},ensure_ascii=False));return 0
                raise
            plan=plan_for(args.kind,payload,settings)
            private_json(out/'plan.json',plan)
            if not(args.live or args.preflight):
                print(json.dumps(plan,ensure_ascii=False,indent=2));return 0
            if args.live:
                cost=load_quote(args.quote_file,plan['request_hash'])
                if args.approval_hash!=plan['request_hash']:
                    raise ChatKHUError('approval_required','실제 호출 전 이 요청의 예상 비용·횟수를 보고하고 사용자 승인을 받아 request_hash를 지정해 주세요.')
                if cost.get('bound') not in {'exact','maximum'} and not args.accept_unknown_cost:
                    raise ChatKHUError('cost_confirmation_required','최종 크레딧 상한을 확인하지 못했어요. 미확정 비용의 실행 여부를 다시 승인받아야 해요.')
        events=[]
        run_path=out/('run-'+uuid4().hex+'.json')
        def record(event):
            events.append(event)
            private_json(run_path,{'kind':args.kind,'events':events,'generative_call_limit':1 if args.live else 0})
            if event.get('phase')=='operation':
                private_json(out/'pending-operation.json',{'kind':args.kind,'model':event['model'],'operation_id':event['operation_id'],
                    'origin_run':pending.get('origin_run') if args.resume else run_path.name})
        with GatewayClient(settings,on_event=record) as client:
            if args.preflight:
                models=client.models()
                model=payload['model']
                enabled=any(isinstance(item,dict) and item.get('id')==model for item in models['data'])
                if not enabled:raise ChatKHUError('model_not_listed','현재 계정 모델 목록에서 선택한 모델을 확인하지 못했어요. 생성하지 않아요.')
                cost=client.estimate(args.kind,payload) if args.kind!='tts' else dict(UNKNOWN)
                report={**plan,'action':'preflight','network_called':True,'checked_at':time.time(),'model_listed':True,'cost':cost,'actual_generation_posts':0}
                private_json(out/'preflight.json',report)
                print(json.dumps(report,ensure_ascii=False,indent=2));return 0
            provider=PROVIDERS[args.kind](client)
            target=out/('asset-'+uuid4().hex)
            if args.resume:
                artifact=provider.resume(pending['operation_id'],target)
            else:
                approval=Approval(args.kind,args.approval_hash,args.accept_unknown_cost)
                artifact=provider.generate(payload,target,approval,cost)
            report=asdict(artifact);report['path']=str(artifact.path)
            report['attempt_journal']=str(run_path)
            report['origin_run']=pending.get('origin_run') if args.resume else run_path.name
            private_json(out/'result.json',report)
            print(json.dumps({'status':'validated','kind':args.kind,'local_file':str(artifact.path),
                'metadata':artifact.metadata,'elapsed_seconds':artifact.elapsed_seconds,'report':str(out/'result.json')},ensure_ascii=False))
            return 0
    except (ChatKHUError,ConfigurationError) as exc:
        error={'status':'not_completed','code':getattr(exc,'code','invalid_configuration'),'message':str(exc),
               'http_status':getattr(exc,'status',None),'automatic_retry':False}
        if run_path and run_path.exists():
            record=load_json(run_path.read_text());record['failure']=error;private_json(run_path,record)
        print(json.dumps(error,ensure_ascii=False),file=sys.stderr);return 1
    except (OSError,ValueError,TypeError,RecursionError):
        print(json.dumps({'status':'not_completed','code':'invalid_local_input','message':'로컬 입력·출력·견적 파일을 확인해 주세요. 비밀 값과 원문은 표시하지 않아요.'},ensure_ascii=False),file=sys.stderr);return 2


if __name__=='__main__':
    raise SystemExit(main())
