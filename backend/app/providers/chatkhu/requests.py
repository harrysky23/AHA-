"""Versioned water-cycle test requests, restricted to documented parameters."""
import base64
from pathlib import Path

from .contracts import ChatKHUError

PROMPT_VERSION = "aha-water-visual-v1"
STYLE = ("Educational editorial illustration for Korean high-school learners. Consistent AHA visual style: "
         "soft violet, warm yellow sunlight, gentle pink accents, clean rounded forms, clear depth and calm movement. "
         "No text, letters, labels, numbers, equations, arrows, logos or watermarks. ")
ILLUSTRATION = (STYLE + "A vertical 9:16 landscape with an ocean below, mountains on one side, clouds in the sky and a visible sun. "
                "Show a scientifically plausible simplified water-cycle setting. Leave uncluttered space for later SVG labels.")
ANIMATION = (STYLE + "Keep the composition, shapes and colors of the reference illustration. "
             "Animate subtle vapor rising from the sun-warmed ocean and slow horizontal cloud drift. "
             "Keep mountains and coastline stable. Do not show boiling oceans or liquid water floating in the air.")
NARRATION = ("태양 에너지를 받은 바다의 물 일부는 수증기가 되어 공기 중으로 이동해요. "
             "수증기가 식으면 작은 물방울이나 얼음 입자가 생기고, 구름을 이룰 수 있어요. "
             "구름의 물은 비나 눈으로 내려와 땅과 강을 거쳐 다시 바다로 모이며 순환해요.")


def image_request(settings):
    return {"model": settings.image_model, "prompt": ILLUSTRATION, "number_of_images": 1, "aspect_ratio": "9:16"}


def image_data_url(path: Path):
    if path.stat().st_size > 8*1024**2:
        raise ChatKHUError("input_too_large", "검증용 입력 이미지는 최대 8MiB예요.")
    raw = path.read_bytes()
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif raw.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ChatKHUError("invalid_input_image", "PNG·JPEG·WebP 입력 이미지가 필요해요.")
    return f"data:{mime};base64,"+base64.b64encode(raw).decode()


def video_request(settings, image: Path | None = None, *, text_only=False):
    if image is None and not text_only:
        raise ChatKHUError("input_image_required", "이미지 생성 결과를 확인한 후 --input-image로 지정해 주세요. 텍스트 생성은 별도 승인한 --text-only만 가능해요.")
    parameters = {"aspect_ratio": "9:16"}
    if settings.video_model == "fal-ai/kling-video/v3":
        parameters.update(duration=3, mode="standard", generate_audio=False)
    else:
        parameters.update(duration=5, resolution="720p")
    result = {"model": settings.video_model, "prompt": ANIMATION, "parameters": parameters}
    if image:
        result["input_urls"] = [image_data_url(image)]
    return result


def tts_request(settings):
    # instructions is documented only for 3.8, so do not send it to 3.1.
    return {"model": settings.tts_model, "input": NARRATION, "voice": "Aoede"}


def public_request(payload):
    result = dict(payload)
    if "input_urls" in result:
        from hashlib import sha256
        result["input_urls"] = [{"type": "local_image_data_url", "sha256": sha256(value.encode()).hexdigest(),
                                "encoded_bytes": len(value)} for value in result["input_urls"]]
    return result
