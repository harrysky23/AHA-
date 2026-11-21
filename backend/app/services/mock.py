"""Phase 1's fixed Math II example. No question analysis or external calls."""
from ..schemas import LessonSpec
from .materials import MaterialContext


def generate_mock(concept: str, question: str, material: MaterialContext) -> LessonSpec:
    need, initial, level = "두 점 사이의 기울기와 한 점에서의 미분계수 연결", 1.2, "foundation"
    explanation = "평균변화율은 두 점 P와 Q를 잇는 할선의 기울기예요. Q를 P에 가까이 옮기면 할선은 접선에 가까워지고 기울기 2+h는 2로 수렴해요. 슬라이더로 그 과정을 확인해 보세요."
    quotes = [{"page": material.pages[0]["page"], "quote": material.pages[0]["text"][:160]}] if material.pages else []
    assumptions = ["시각화는 f(x)=x², a=1로 제한해요.", "mock은 질문에 관계없이 동일한 고정 수학 예제를 사용하며 AI 분석·학습 수준 진단이 아니에요."]
    if material.pages:
        explanation += " 업로드 자료의 발췌문도 아래에 표시했어요. mock은 자료의 의미나 관련성을 분석하지 않아요."
        assumptions.append("PDF 인용은 추출 내용의 표시이며, mock에서 자료와 질문의 의미적 관련성을 확인하지 않아요.")
    else:
        assumptions.append("읽을 수 있는 자료가 없어 질문만 사용해요.")
    return LessonSpec.model_validate({
        "schema_version": "1", "scope": "supported", "title": "할선에서 접선으로 · " + need,
        "analysis": {"learning_level": level, "level_reason": "고정 예제의 기본 설명 수준이며, 질문이나 성취도를 분석한 결과가 아니에요.",
            "student_need": need, "core_concepts": ["평균변화율", "미분계수", "극한"], "prerequisites": ["두 점 사이의 기울기", "이차함수 그래프"]},
        "explanation": explanation,
        "steps": [{"title":"두 점을 이어요", "explanation":"P(1,1)와 Q(1+h,(1+h)²)를 잇는 직선을 보세요."},
                  {"title":"질문의 핵심을 확인해요", "explanation":explanation},
                  {"title":"양쪽에서 가까이 가요", "explanation":"h를 양수와 음수에서 각각 0에 가까이 옮겨 보세요. h=0에서 나누지 않고 극한을 생각해요."}],
        "visualization": {"type":"secant_tangent_x2", "function":"x_squared", "a":1.,
            "variable":{"name":"h", "label":"두 점 사이의 x 변화량", "min":-1.2, "max":1.2, "step":.0001, "initial":initial}},
        "examples": [{"h":initial, "secant_slope":2+initial, "tangent_slope":2., "explanation":"h≠0에서 할선 기울기는 2+h예요."}],
        "quiz": [{"kind":"secant_slope", "h":-.1 if initial<0 else .1, "answer":1.9 if initial<0 else 2.1, "explanation":"할선 기울기는 2+h이므로 h를 더해요."},
                 {"kind":"undefined_at_zero", "h":0., "answer":None, "explanation":"h=0이면 분모가 0이어서 할선 기울기는 정의되지 않아요."}],
        "source_quotes":quotes, "assumptions":assumptions,
    })
