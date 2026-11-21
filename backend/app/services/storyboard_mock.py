"""Deterministic storyboard fixtures; no API calls or claims of AI analysis."""
from copy import deepcopy

from ..providers.base import StoryboardInput
from ..storyboard_schema import StoryboardSpec


def node(id, label, detail, x, y, color="violet"):
    return {"id":id,"label":label,"detail":detail,"x":x,"y":y,"color":color}


def edge(id, source, target, label):
    return {"id":id,"source":source,"target":target,"label":label}


def function_graph(supply=False):
    if supply:
        curves=[{"id":"demand","label":"수요 P=9-Q","coefficients":[9.,-1.],"color":"violet"},
                {"id":"supply","label":"공급 P=1+Q","coefficients":[1.,1.],"color":"pink"}]
        markers=[{"id":"equilibrium","label":"균형 (4,5)","point":{"x":4.,"y":5.},"color":"yellow"}]
        return {"type":"function_graph","x_label":"수량 Q","y_label":"가격 P","x_range":{"min":0.,"max":8.},
                "y_range":{"min":0.,"max":10.},"curves":curves,"markers":markers,"connectors":[],"marker_keyframes":[]}
    return {"type":"function_graph","x_label":"x","y_label":"f(x)","x_range":{"min":0.,"max":3.},
        "y_range":{"min":0.,"max":6.},"curves":[{"id":"parabola","label":"f(x)=x²","coefficients":[0.,0.,1.],"color":"violet"}],
        "markers":[{"id":"p","label":"P(1,1)","point":{"x":1.,"y":1.},"color":"violet","curve_id":"parabola"},
                   {"id":"q","label":"Q(2,4)","point":{"x":2.,"y":4.},"color":"pink","curve_id":"parabola"},
                   {"id":"tangent_anchor","label":"접선 위의 점","point":{"x":2.,"y":3.},"color":"yellow"}],
        "connectors":[{"id":"secant","start_marker":"p","end_marker":"q","label":"할선","extend":True,"color":"pink"},
                      {"id":"tangent","start_marker":"p","end_marker":"tangent_anchor","label":"접선","extend":True,"color":"yellow"}],
        "marker_keyframes":[{"at_seconds":5.,"marker_id":"q","point":{"x":1.01,"y":1.0201}}]}


def water_cycle():
    return {"type":"process_diagram","flow":"cycle",
        "nodes":[node("water","지표의 물","바다·호수 등에 물이 모여 있어요.",.25,.8,"blue"),
                 node("vapor","증발","태양 에너지로 물이 수증기가 되어 이동해요.",.25,.2),
                 node("cloud","응결","수증기가 식으며 작은 물방울 등이 모여요.",.75,.2),
                 node("rain","강수","물방울·얼음 입자가 비나 눈으로 내려요.",.75,.8)],
        "edges":[edge("evaporate","water","vapor","증발"),edge("condense","vapor","cloud","응결"),
                 edge("precipitate","cloud","rain","강수"),edge("collect","rain","water","유출·집수")]}


def binary_search():
    values=[str(n) for n in [1,3,5,7,9,11,13]]
    states=[{**node("full","전체 범위","중앙값 7과 목표 11을 비교해요.",.5,.15),"items":values,"highlight_indices":[3],"active_range":{"low":0,"high":6}},
            {**node("right","오른쪽 절반","목표가 더 크므로 오른쪽 범위에서 중앙값 11을 봐요.",.5,.5,"blue"),"items":values,"highlight_indices":[5],"active_range":{"low":4,"high":6}},
            {**node("found","찾음","목표 11과 중앙값이 같아 탐색을 마쳐요.",.5,.85,"green"),"items":values,"highlight_indices":[5],"active_range":{"low":5,"high":5}}]
    return {"type":"state_transition","states":states,
            "transitions":[edge("go_right","full","right","11 > 7"),edge("match","right","found","11 = 11")],
            "initial_state":"full","steps":[{"at_seconds":0.,"state_id":"full","caption":"정렬된 배열에서 시작해요."},
                {"at_seconds":3.,"state_id":"right","caption":"검사할 범위를 절반으로 줄여요."},
                {"at_seconds":6.,"state_id":"found","caption":"목표값을 찾았어요."}]}


def comparison():
    return {"type":"comparison","left_title":"평균변화율","right_title":"미분계수",
            "rows":[{"id":"points","aspect":"기준","left":"서로 다른 두 점 사이","right":"한 점에서의 변화","emphasis":"none"},
                    {"id":"slope","aspect":"그래프","left":"할선의 기울기","right":"접선의 기울기","emphasis":"right"}]}


def timeline():
    return {"type":"timeline","time_unit":"step","events":[
        {"id":"before","position":1.,"time_label":"처음","title":"출발 상태","detail":"변화가 일어나기 전을 확인해요."},
        {"id":"during","position":2.,"time_label":"변화 중","title":"변화 과정","detail":"원인과 과정을 순서대로 살펴봐요."},
        {"id":"after","position":3.,"time_label":"이후","title":"결과","detail":"처음 상태와 비교해요."}]}


def text_explanation(heading="핵심 정리", unknown=False):
    return {"type":"text_explanation","heading":heading,
            "paragraphs":["자료의 정의와 조건을 먼저 확인하고 핵심 개념을 한 문장으로 정리해요." if unknown else "그림에서 본 변화와 핵심 개념을 연결해 다시 설명해 보세요."],
            "fallback_reason":"mock에서 구체적인 지식을 추측하지 않고 확인할 항목을 안내해요." if unknown else "마지막 장면에서는 새 도형보다 짧은 문장으로 개념을 정리해요."}


def generate_mock_storyboard(request: StoryboardInput) -> StoryboardSpec:
    query=(request.concept+" "+request.question).lower()
    unknown=False
    if any(word in query for word in ["미분", "할선", "접선", "derivative"]):
        topic="미분계수의 기하학적 의미"
        visuals=[function_graph(),function_graph(),comparison(),text_explanation()]
        captions=["두 점을 이으면 할선이에요", "h를 작게 하면 기울기가 가까워져요", "두 점 사이와 한 점에서의 차이", "0을 대입하는 대신 극한을 보아요"]
        narrations=["함수 위에서 서로 다른 두 점을 이으면 할선이 돼요. 할선의 기울기는 두 점 사이의 평균변화율이에요.",
                    "예제에서 고정한 점은 P(1,1)이에요. 다른 점을 가까이 옮기면 할선의 기울기 2+h는 2에 가까워져요.",
                    "평균변화율은 두 점 사이를 보고 미분계수는 한 점에서의 변화를 봐요. 그래프에서는 접선의 기울기와 연결돼요.",
                    "h가 영인 값을 식에 대입해 나누지는 않아요. 영이 아닌 h가 영에 가까워질 때의 극한이 미분계수예요."]
        assumptions=["예시는 f(x)=x², a=1로 한정해요."]
    elif any(word in query for word in ["물의 순환", "물 순환", "water cycle"]):
        topic="물의 순환"
        visuals=[water_cycle(),water_cycle(),water_cycle(),text_explanation()]
        captions=["물은 지구에서 순환해요", "증발과 응결", "강수와 지표의 이동", "태양 에너지와 중력을 연결해요"]
        narrations=["바다와 땅의 물은 한곳에만 머물지 않아요. 물은 증발과 응결, 강수와 이동을 거치며 순환해요.",
                    "태양 에너지를 받은 물의 일부는 수증기가 돼요. 수증기가 식으면 작은 물방울이나 얼음 입자가 만들어질 수 있어요.",
                    "구름의 물은 비나 눈으로 지표에 내려와요. 내린 물은 땅으로 스며들거나 지표를 따라 흘러 다시 모여요.",
                    "태양 에너지는 증발을 돕고 중력은 물의 이동에 관여해요. 네 과정을 순서대로 연결하며 물의 순환을 떠올려 보세요."]
        assumptions=["증산·지하수 저장 등은 생략한 기본 순환 모형이에요."]
    elif any(word in query for word in ["수요", "공급", "supply", "demand"]):
        topic="수요와 공급"
        visuals=[function_graph(True),function_graph(True),{"type":"comparison","left_title":"수요","right_title":"공급","rows":[
            {"id":"relation","aspect":"가격과 수량","left":"다른 조건이 같으면 가격이 오를수록 수요량은 줄어드는 관계","right":"다른 조건이 같으면 가격이 오를수록 공급량은 늘어나는 관계","emphasis":"none"}]},text_explanation()]
        captions=["시장의 두 관계를 보아요", "두 곡선이 만나는 균형", "수요량과 공급량을 비교해요", "다른 조건이 같다는 가정을 기억해요"]
        narrations=["수요와 공급은 가격과 수량의 관계를 나타내요. 다른 조건은 같다고 두고 가격이 변할 때를 살펴봐요.",
                    "설명용 모형에서 두 곡선은 수량 사, 가격 오에서 만나요. 이 점은 이 모형의 수요량과 공급량이 같은 균형점이에요.",
                    "가격이 오르면 수요량과 공급량은 서로 다른 방향으로 변하는 기본 관계를 보일 수 있어요. 곡선의 뜻을 구분해 보세요.",
                    "이 그래프의 계수는 실제 시장 통계가 아니에요. 다른 조건이 바뀌면 곡선 자체가 이동할 수 있다는 점도 기억해요."]
        assumptions=["P=9-Q, P=1+Q는 실제 통계가 아닌 설명용 선형 모형이에요.","다른 조건은 같다고 가정해요."]
    elif any(word in query for word in ["이진 탐색", "이진탐색", "binary search"]):
        topic="이진 탐색 알고리즘"
        visuals=[binary_search(),binary_search(),binary_search(),text_explanation()]
        captions=["정렬된 자료에서 시작해요", "중앙값과 목표를 비교해요", "탐색 범위를 절반으로 줄여요", "남은 범위에서 비교를 반복해요"]
        narrations=["이진 탐색은 정렬된 자료에서 목표를 찾는 방법이에요. 자료가 정렬되어 있다는 조건을 먼저 확인해요.",
                    "예제 배열에서 목표는 십일이에요. 중앙값 칠보다 크므로 중앙을 포함한 왼쪽 부분은 다음 탐색에서 제외해요.",
                    "오른쪽 범위의 중앙값은 십일이에요. 목표와 같으므로 찾았다고 판단해요. 매번 검사할 범위를 줄이는 것이 핵심이에요.",
                    "중앙값과 목표를 비교하고 필요한 절반만 남겨요. 값이 같으면 찾고 범위가 없어지면 목표가 없다고 판단해요."]
        assumptions=["정렬된 배열 [1,3,5,7,9,11,13]과 목표 11을 사용하는 설명용 예제예요."]
    else:
        topic=(request.concept or request.question)[:80]
        unknown=True
        visuals=[text_explanation("먼저 정의를 확인해요",True),text_explanation("조건과 맥락을 확인해요",True),text_explanation("자료에서 근거를 찾아요",True),text_explanation("추가 설명이 필요해요",True)]
        captions=["개념의 정의", "질문에서 어려운 지점", "학습 자료의 근거", "다음에 확인할 내용"]
        narrations=["이 입력은 mock의 네 가지 개념 예시에 없어요. 검증하지 않은 정의를 만들지 않고 확인할 내용을 안내해요."]*4
        assumptions=["입력한 개념의 구체적인 사실을 mock에서 분석하지 않았어요."]
    sources=[]
    if request.material.pages:
        page=request.material.pages[0]
        sources=[{"id":"material_1","page":page["page"],"quote":page["text"][:160]}]
        assumptions.append("mock의 자료 인용은 발췌 표시이며 의미적 관련성을 확인한 결과가 아니에요.")
    assumptions.append("mock 템플릿이며 AI 생성·성취도 진단·실제 음성 길이 측정 결과가 아니에요.")
    scenes=[]
    for i in range(4):
        scenes.append({"id":f"scene_{i+1}","start_seconds":round(request.target_duration_seconds*i/4,1),
            "end_seconds":round(request.target_duration_seconds*(i+1)/4,1),
            "screen":{"title":captions[i],"bullets":["mock 학습 예시"],"formulas":["2+h → 2"] if topic.startswith("미분") else []},
            "narration_ko":narrations[i],"visualization":deepcopy(visuals[i]),"cues":[],"source_ids":["material_1"] if sources and i==0 else []})
    return StoryboardSpec.model_validate({"schema_version":"storyboard-1","topic":topic,"learning_objectives":[f"{topic}의 핵심 관계를 설명해요." if not unknown else "필요한 정의와 추가 맥락을 확인해요."],
        "student_level":request.student_level,"difficult_point":(request.question or request.concept)[:280],
        "duration_seconds":request.target_duration_seconds,"video":{"aspect_ratio":"9:16","width":1080,"height":1920,"fps":30},
        "scenes":scenes,"material_usage":"used" if sources else "unavailable","sources":sources,"assumptions":assumptions,
        "review_status":"needs_context" if unknown else "ready_for_review","limitations":["mock에서 해당 개념의 사실·자료 의미를 분석하지 않았어요."] if unknown else ["한국어 내레이션의 실제 발화 길이는 아직 측정하지 않았어요."]})
