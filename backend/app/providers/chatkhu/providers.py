"""ChatKHU media providers with explicit approval for each generation."""
import base64
import binascii
from copy import deepcopy
import hashlib
import re
from pathlib import Path

from .artifacts import save_media, validate_media
from .contracts import ChatKHUError, MediaArtifact


def validate_request(kind, payload, settings):
    model = getattr(settings, {"image":"image_model", "video":"video_model", "tts":"tts_model"}[kind])
    if not isinstance(payload, dict) or payload.get("model") != model:
        raise ChatKHUError("invalid_request", "설정·승인한 모델과 요청 모델이 달라요.")
    allowed = {"image":{"model","prompt","number_of_images","aspect_ratio"},
               "video":{"model","prompt","parameters","input_urls"}, "tts":{"model","input","voice"}}[kind]
    if set(payload)-allowed:
        raise ChatKHUError("invalid_request", "확인하지 않은 API 필드를 전송하지 않아요.")
    text = payload.get("input" if kind == "tts" else "prompt")
    if not isinstance(text, str) or not 1 <= len(text) <= (4000 if kind == "tts" else 2000):
        raise ChatKHUError("invalid_request", "입력 텍스트 길이를 확인해 주세요.")
    if kind == "image" and (type(payload.get("number_of_images")) is not int or payload["number_of_images"] != 1
                            or payload.get("aspect_ratio") not in ("9:16", "16:9")):
        raise ChatKHUError("invalid_request", "이미지 1장과 9:16 또는 16:9 비율을 지정해 주세요.")
    if kind == "tts" and payload.get("voice") != "Aoede":
        raise ChatKHUError("invalid_request", "이번 검증은 Aoede 단일 화자만 사용해요.")
    if kind == "tts" and not re.search(r"[가-힣]", text):
        raise ChatKHUError("invalid_request", "한국어 내레이션을 입력해 주세요.")
    if kind == "video":
        params = payload.get("parameters")
        expected = ({"duration":3,"mode":"standard","generate_audio":False,"aspect_ratio":"9:16"}
                    if model == "fal-ai/kling-video/v3" else {"duration":5,"resolution":"720p","aspect_ratio":"9:16"})
        if not isinstance(params, dict) or params != expected or type(params.get("duration")) is not int:
            raise ChatKHUError("invalid_request", "검증 계획의 짧은 영상 파라미터와 요청이 달라요.")
        if "generate_audio" in params and type(params["generate_audio"]) is not bool:
            raise ChatKHUError("invalid_request", "generate_audio는 JSON 불리언이어야 해요.")
        images = payload.get("input_urls", [])
        if not isinstance(images, list) or len(images)>1 or any(not isinstance(i,str) or not i.startswith(("data:image/png;base64,","data:image/jpeg;base64,","data:image/webp;base64,")) for i in images):
            raise ChatKHUError("invalid_request", "입력은 검증한 로컬 이미지 1개의 데이터 URL만 허용해요.")


class _MediaProvider:
    kind = None

    def __init__(self, client, *, inspect=validate_media):
        self.client, self.inspect = client, inspect

    def generate(self, payload, output: Path, approval, cost):
        payload = deepcopy(payload)
        validate_request(self.kind, payload, self.client.settings)
        # Reject overwrite before spending credit; actual suffix is checked later.
        if any(output.with_suffix(ext).exists() for ext in [".png",".jpg",".webp",".mp4",".wav"]):
            raise ChatKHUError("output_exists", "기존 결과를 덮어쓰는 생성 요청은 보내지 않아요.")
        started = self.client.clock()
        data = self.client.generate(self.kind, payload, approval, cost)
        return self._finish(data, payload["model"], output, started)

    def _finish(self, data, model, output, started):
        operation_id = None
        source = {"kind":"pcm_bytes", "url_expiry":"not_applicable"}
        if self.kind == "tts":
            raw = data
        else:
            if self.kind == "video" or not isinstance(data.get("data"), list):
                data, operation_id = self.client.poll(self.kind, model, data)
            if self.kind == "image":
                items = data.get("data")
                if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
                    raise ChatKHUError("invalid_response", "이미지 1개 응답을 확인하지 못했어요.")
                location = items[0].get("url")
                if isinstance(location, str) and location.startswith("data:image/"):
                    source = {"kind":"inline_image", "url_expiry":"not_applicable"}
                    try:
                        header, encoded = location.split(",", 1)
                        if header not in {"data:image/png;base64","data:image/jpeg;base64","data:image/webp;base64"}:
                            raise ValueError()
                        raw = base64.b64decode(encoded, validate=True)
                        if len(raw)>24*1024**2:
                            raise ValueError()
                    except (ValueError, binascii.Error):
                        raise ChatKHUError("invalid_response", "이미지 인라인 데이터 형식을 확인하지 못했어요.") from None
                else:
                    source = {"kind":"downloaded_image", "url_expiry":"not_documented"}
                    raw = self.client.download(self.kind, model, location, operation_id)
            else:
                source = {"kind":"downloaded_video", "url_expiry":"not_documented"}
                raw = self.client.download(self.kind, model, data.get("video_uri"), operation_id)
        path, metadata = save_media(raw, self.kind, output, self.inspect)
        metadata = {**metadata, "source":source}
        self.client.event({"phase":"validated", "kind":self.kind, "source_url_expiry":source["url_expiry"], "size_bytes":path.stat().st_size})
        return MediaArtifact(self.kind, model, path, hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size,
            metadata, round(self.client.clock()-started,3), list(self.client.events))

    def resume(self, operation_id, output: Path):
        if self.kind == "tts":
            raise ChatKHUError("resume_unsupported", "동기 TTS는 작업 조회 재개를 지원하지 않아요. 재호출에는 새 승인이 필요해요.")
        model = getattr(self.client.settings, self.kind+"_model")
        return self._finish({"status":"processing", "operation_id":operation_id}, model, output, self.client.clock())


class ChatKHUImageProvider(_MediaProvider):
    kind = "image"


class ChatKHUVideoProvider(_MediaProvider):
    kind = "video"


class ChatKHUTTSProvider(_MediaProvider):
    kind = "tts"
