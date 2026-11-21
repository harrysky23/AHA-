"""Locally owned, deterministic Phase 1 content. No AI or file extraction."""


def build_lesson(concept: str, question: str, output_format: str, material: dict | None) -> dict:
    return {
        "mode": "local_demo",
        "format": output_format,
        "title": "수학 II · 할선에서 접선으로",
        "request": {"concept": concept, "question": question},
        "material": material,
        "grounding": {
            "status": "not_analyzed" if material else "no_material",
            "message": (
                "파일 형식과 크기만 확인했어요. PDF 텍스트 추출·이미지 OCR은 아직 연결하지 않았어요."
                if material else "학습 자료 없이 기본 예제로 학습해요."
            ),
        },
        "notice": "Phase 1 로컬 예제입니다. 입력한 개념·질문과 관계없이 f(x)=x², a=1을 사용하며, 맞춤 설명이나 AI 생성 결과가 아닙니다.",
        "lesson": {
            "id": "secant-tangent",
            "viewer_url": "/lessons/secant-tangent",
            "function": "f(x)=x²",
            "point": [1, 1],
            "secant_formula": "2+h (h≠0)",
            "tangent_slope": 2,
        } if output_format == "html" else None,
        "video": {
            "url": "/static/media/derivative-explainer.mp4",
            "label": "기존 미분계수 예시 영상",
            "generated": False,
            "notice": "원본 시안에 포함된 가로형 예시 영상입니다. 요청한 자료로 새로 만든 9:16 숏츠가 아니며, 실제 숏츠 생성은 향후 연결합니다.",
        } if output_format == "shorts" else None,
    }
