"""Opt-in inspection of existing MP4 files. No model calls or rendering."""
import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import wave

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path,nargs="?",default=ROOT/"tmp/remotion/release")
    parser.add_argument("--voice",type=Path,default=ROOT/"tmp/chatkhu/comparison/verified-full/assets/tts.wav")
    args=parser.parse_args();root=args.directory
    report=json.loads((root/"water-cycle.render.json").read_text())
    video=root/"water-cycle.mp4"
    assert hashlib.sha256(video.read_bytes()).hexdigest()==report["sha256"]
    original=ROOT/"tmp/chatkhu/comparison/verified-full/C.mp4"
    source_report=json.loads(original.with_suffix(".render.json").read_text())
    assert hashlib.sha256(original.read_bytes()).hexdigest()==source_report["sha256"]
    assert hashlib.sha256((root/"C-original.mp4").read_bytes()).hexdigest()==source_report["sha256"]
    with wave.open(str(args.voice),"rb") as wav:
        assert wav.getframerate()==24000 and wav.getsampwidth()==2 and wav.getnchannels()==1
        source=array.array("h",wav.readframes(wav.getnframes()))
    raw=subprocess.run(["ffmpeg","-nostdin","-v","error","-i",str(video),"-vn","-ar","24000","-ac","1","-f","s16le","-"],
        check=True,capture_output=True,timeout=30).stdout
    offset=round(report["audio_offset_seconds"]*24000)
    target=array.array("h",raw)[offset:offset+len(source)]
    assert len(source)==len(target)
    xx=yy=xy=0
    for a,b in zip(source[::8],target[::8]):xx+=a*a;yy+=b*b;xy+=a*b
    correlation=xy/math.sqrt(xx*yy)
    assert correlation>.98,"Expected original waveform plus documented offset, with only AAC/resampling loss"
    audit=report.get("frame_audit",[])
    if audit:
        assert audit[0]["sha256"]==audit[-1]["sha256"] and audit[0]["sha256"]!=audit[1]["sha256"]
        assert audit[0]["layout"][0]["particles"]!=audit[1]["layout"][0]["particles"]
        assert audit[0]["layout"][0]["particles"]==audit[-1]["layout"][0]["particles"]
        kinds={p["kind"] for a in audit for layer in a["layout"] for p in layer["particles"]}
        assert {"vapor","condensed-water","rain","runoff"}<=kinds
        assert all(c["inside"] and c["text_fits"] for c in report["layout"]["checks"])
    result={"media":report["media"],"original_c_unchanged":True,"audio_offset_seconds":report["audio_offset_seconds"],
        "source_audio_seconds":len(source)/24000,"correlation_after_offset":round(correlation,6),
        "alignment_note":"Waveform preservation only; not phoneme alignment or a subjective listening review.",
        "deterministic_png_verified":bool(audit),"animation_types_verified":sorted(kinds) if audit else [],"external_api_calls":0}
    (root/"verification.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    for seconds in [2.5,4.5,8,10,14.5,15.5,18,19,25]:
        subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-ss",str(seconds),"-i",str(video),"-frames:v","1",str(root/f"frame-{seconds}.png")],check=True,timeout=15)
    (root/"comparison.html").write_text('''<!doctype html><html lang="ko"><meta charset="utf-8"><title>AHA! 렌더러 비교</title>
<style>body{background:#f9f7ff;color:#2d2345;font-family:system-ui;margin:30px}main{display:flex;gap:30px;flex-wrap:wrap}video{width:300px;max-width:85vw;aspect-ratio:9/16;border-radius:22px;background:#2d2345}h1{color:#7b5cf0}p{max-width:700px;line-height:1.7}</style>
<h1>AHA! 물의 순환 · 렌더러 비교</h1><p>같은 이미지·음성 원본을 재사용했습니다. Remotion은 음성을1초 늦게 시작하며 조정 가능한 자막 큐를 사용합니다. 외부 AI 호출은 없습니다.</p>
<main><section><h2>기존 C · SVG + AI 배경</h2><video controls preload="metadata" src="C-original.mp4"></video></section>
<section><h2>Remotion · 개념 애니메이션</h2><video controls preload="metadata" src="water-cycle.mp4"></video></section></main></html>''')
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":main()
