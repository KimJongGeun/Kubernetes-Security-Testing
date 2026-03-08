"""
입출력 보안 필터

점수 기반 탐지 시스템.
- 패턴마다 위험 점수를 부여하고, 합산 점수가 임계값을 넘으면 차단
- 이진 판단(차단/통과)이 아니라 점수로 판단하니까 오탐이 줄어든다
- 한글/영어 패턴 모두 탐지
"""

import re
import unicodedata


# =============================================================================
# 텍스트 정규화
# =============================================================================

# 유니코드 전각 문자 → 반각으로 변환 (ｉｇｎｏｒｅ → ignore)
# 유사 문자 치환 (а→a 키릴 문자 등)
HOMOGLYPH_MAP = str.maketrans({
    "\uff41": "a", "\uff42": "b", "\uff43": "c", "\uff44": "d", "\uff45": "e",
    "\uff46": "f", "\uff47": "g", "\uff48": "h", "\uff49": "i", "\uff4a": "j",
    "\uff4b": "k", "\uff4c": "l", "\uff4d": "m", "\uff4e": "n", "\uff4f": "o",
    "\uff50": "p", "\uff51": "q", "\uff52": "r", "\uff53": "s", "\uff54": "t",
    "\uff55": "u", "\uff56": "v", "\uff57": "w", "\uff58": "x", "\uff59": "y",
    "\uff5a": "z",
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",  # 키릴 문자
    "\u0441": "c", "\u0443": "y", "\u0445": "x",
    "\u200b": "",  # zero-width space 제거
    "\u200c": "",  # zero-width non-joiner 제거
    "\u200d": "",  # zero-width joiner 제거
    "\ufeff": "",  # BOM 제거
})


def normalize_text(text: str) -> str:
    """유니코드 정규화 + 전각/유사문자 변환 + 보이지 않는 문자 제거."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(HOMOGLYPH_MAP)
    return text


# =============================================================================
# 입력 필터 — 점수 기반 탐지
# =============================================================================

# (패턴, 점수, 카테고리)
# 점수 기준:
#   10 — 거의 확실한 공격 (이게 정상 요청일 가능성이 거의 없음)
#    7 — 높은 위험 (정상 요청에서도 나올 수 있지만 드묾)
#    5 — 중간 위험 (문맥에 따라 다름)
#    3 — 낮은 위험 (단독으로는 차단하면 안 됨, 다른 패턴과 합산)

INPUT_RULES = [
    # --- 프롬프트 인젝션 (영어) ---
    (r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|directions?|context)",
     10, "injection"),
    (r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)",
     10, "injection"),
    (r"forget\s+(all\s+)?(previous|prior|your)\s+(instructions?|prompts?|rules?|context)",
     10, "injection"),
    (r"override\s+(your|all|the)\s+(instructions?|rules?|guidelines?|programming)",
     10, "injection"),
    (r"(reveal|show|print|display|output)\s+(your\s+)?(system\s*prompt|initial\s*instructions?|hidden\s*instructions?)",
     10, "injection"),
    (r"what\s+(is|are)\s+your\s+(system\s*prompt|initial\s*instructions?|hidden\s*prompt)",
     7, "injection"),
    (r"new\s+instructions?\s*:",
     7, "injection"),
    (r"system\s*prompt\s*:",
     7, "injection"),
    (r"---+\s*(new|actual|real)\s*(instructions?|task|prompt)",
     10, "injection"),
    (r"(<<|>>)\s*(system|instructions?|prompt)",
     7, "injection"),

    # --- 프롬프트 인젝션 (한글) ---
    (r"(이전|위의|기존|앞의|앞선)\s*(지시|명령|프롬프트|지침|규칙|설정)(을|를|은|는)?\s*(무시|잊어|잊고|버리고|버려|따르지)",
     10, "injection_ko"),
    (r"(시스템|숨겨진|초기|원래)\s*(프롬프트|지시|명령|설정)(을|를)?\s*(알려|보여|출력|공개|말해)",
     10, "injection_ko"),
    (r"(새로운|다른|진짜)\s*(지시|명령|역할)\s*:",
     7, "injection_ko"),
    (r"(지금부터|이제부터)\s*(너는|당신은|넌)\s*.{0,10}(이다|입니다|야|이야|역할)",
     7, "injection_ko"),
    (r"(원래|본래|실제)\s*(목적|역할|기능)(을|를)?\s*(무시|잊|변경|바꿔)",
     10, "injection_ko"),

    # --- 탈옥 (영어) ---
    (r"do\s+anything\s+now",
     10, "jailbreak"),
    (r"\bDAN\s+(mode|prompt|jailbreak)\b",
     10, "jailbreak"),
    (r"\bjailbreak\b",
     7, "jailbreak"),
    (r"developer\s+mode\s*(enabled|activated|on)",
     10, "jailbreak"),
    (r"bypass\s+(your\s+)?(safety|filter|restriction|guideline|guard)",
     10, "jailbreak"),
    (r"without\s+(any\s+)?(restriction|filter|safety|limit|guard|censorship)",
     7, "jailbreak"),
    (r"no\s+(ethical|moral|safety)\s+(guideline|restriction|filter|constraint)",
     7, "jailbreak"),
    (r"(enable|activate|switch\s+to)\s+(unrestricted|unfiltered|uncensored)\s+mode",
     10, "jailbreak"),

    # --- 탈옥 (한글) ---
    (r"(제한|필터|안전장치|가드레일|검열)(을|를)?\s*(해제|비활성|무시|끄고|꺼|없이|제거)",
     10, "jailbreak_ko"),
    (r"(탈옥|jailbreak)\s*(모드|프롬프트|해줘|해)",
     10, "jailbreak_ko"),
    (r"(제한|규칙|윤리)\s*(없이|무시하고|상관없이)\s*(대답|응답|답변)",
     7, "jailbreak_ko"),

    # --- 인코딩 우회 ---
    (r"(base64|rot13|hex|url)\s*(decode|encode|디코딩|인코딩)",
     5, "encoding"),
    (r"decode\s+this\s*:",
     5, "encoding"),
    (r"convert\s+(from|to)\s+(base64|hex|binary|rot13)",
     5, "encoding"),
    (r"(base64|rot13|hex|url)\s*(변환|디코딩|해독)",
     5, "encoding_ko"),

    # --- 역할 사칭 (높은 오탐 가능성이라 점수 낮게) ---
    # "act as a translator"같은 정상 요청이 많으니까 단독으로는 차단 안 함
    (r"you\s+are\s+now\s+(a|an|the)\s+",
     3, "role_play"),
    (r"act\s+as\s+(a|an|if)\s+",
     3, "role_play"),
    (r"pretend\s+(you\s+are|to\s+be)\s+",
     3, "role_play"),
    (r"(너는|당신은)\s*(이제|지금부터)\s*.{0,20}(이다|입니다|야|이야|처럼|인척)",
     3, "role_play_ko"),

    # --- 역할 사칭 + 위험 키워드 조합이면 점수 올림 ---
    (r"(act\s+as|pretend|you\s+are\s+now).{0,30}(no\s+filter|no\s+restrict|unrestrict|uncensor|evil|malicious)",
     10, "role_play_dangerous"),
    (r"(역할|인척).{0,20}(필터\s*없|제한\s*없|악의|악성)",
     10, "role_play_dangerous_ko"),

    # --- 간접 인젝션 (문서/데이터에 숨긴 명령) ---
    (r"(nevermind|never\s*mind)[\.\s]*(ignore|disregard|forget)",
     10, "indirect_injection"),
    (r"(actually|wait|stop)[\.,\s]+(ignore|disregard|forget)\s+(everything|all|previous|that)",
     10, "indirect_injection"),
    (r"forget\s+everything\s+and\s+",
     10, "indirect_injection"),
    (r"<\s*(system|instruction|prompt)\s*>",
     7, "tag_injection"),
    (r"\[/?INST\]|\[SYSTEM\]",
     7, "tag_injection"),
    (r"\[INST\][\s\S]{0,50}(ignore|bypass|disable|무시|해제)",
     10, "tag_injection"),

    # --- 민감 정보 요청 ---
    (r"(tell|give|show|reveal)\s+me\s+(the\s+)?(password|api\s*key|secret|token|credential|private\s*key)",
     7, "sensitive_request"),
    (r"(비밀번호|API\s*키|시크릿|토큰|인증\s*키|개인\s*키)(를|을)?\s*(알려|보여|말해|출력)",
     7, "sensitive_request_ko"),
]

BLOCK_THRESHOLD = 7  # 이 점수 이상이면 차단


def check_input(prompt: str) -> dict:
    """
    입력 프롬프트를 점수 기반으로 검증한다.
    각 패턴의 점수를 합산하고, 같은 카테고리는 최고 점수만 취한다.
    """
    normalized = normalize_text(prompt)
    text_lower = normalized.lower()
    # 한글 패턴은 원본으로도 매칭 (lower()가 한글에는 영향 없지만 명시적으로)
    text_original = normalized

    category_scores = {}  # 카테고리별 최고 점수
    matched_rules = []

    for pattern, score, category in INPUT_RULES:
        # 한글 패턴은 원본 텍스트에도 매칭, 영어는 소문자 변환된 텍스트에 매칭
        target = text_original if category.endswith("_ko") else text_lower
        match = re.search(pattern, target, re.IGNORECASE)
        if match:
            matched_rules.append({
                "pattern": category,
                "matched": match.group(),
                "score": score,
            })
            # 같은 카테고리에서 최고 점수만 취함
            base_category = category.rstrip("_ko")
            if base_category not in category_scores or score > category_scores[base_category]:
                category_scores[base_category] = score

    total_score = sum(category_scores.values())

    if total_score >= BLOCK_THRESHOLD:
        # 가장 높은 점수의 카테고리를 주요 사유로
        top_category = max(category_scores, key=category_scores.get)
        return {
            "blocked": True,
            "reason": top_category,
            "score": total_score,
            "details": matched_rules,
        }

    return {
        "blocked": False,
        "reason": None,
        "score": total_score,
        "details": matched_rules,
    }


# =============================================================================
# 출력 필터
# =============================================================================

# 민감 정보 패턴 (한국 기준)
SENSITIVE_PATTERNS = {
    "주민등록번호": r"\d{6}\s*-\s*[1-4]\d{6}",
    "카드번호": r"\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}",
    "전화번호": r"01[016789][\s-]?\d{3,4}[\s-]?\d{4}",
    "이메일": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "계좌번호": r"\d{3,4}-\d{2,6}-\d{4,6}",
    "여권번호": r"[A-Z]{1,2}\d{7,8}",
    "운전면허번호": r"\d{2}-\d{2}-\d{6}-\d{2}",
}

# 유해 응답 패턴 (영어 + 한글)
HARMFUL_OUTPUT_PATTERNS = [
    r"i\s+hate\s+humans?",
    r"kill\s+all\s+humans?",
    r"here\s+(is|are)\s+(the\s+)?(malware|virus|exploit|ransomware|backdoor)",
    r"import\s+subprocess.*shell\s*=\s*True",
    r"rm\s+-rf\s+/",
    r"DROP\s+TABLE",
    r"인간(을|를)?\s*(죽|혐오|증오|제거)",
    r"(악성코드|바이러스|랜섬웨어|백도어)(를|을)?\s*(만들|작성|생성)",
]

# 시스템 정보 유출 탐지
SYSTEM_LEAK_PATTERNS = [
    r"(my|the)\s+(system\s*prompt|initial\s*instructions?)\s+(is|are|says?)\s*:",
    r"(시스템|초기)\s*(프롬프트|지시)(는|은)\s*:",
    r"(as\s+an?\s+ai|i\s+am\s+programmed\s+to)",
]


def check_output(text: str) -> dict:
    """LLM 출력을 검증한다. 민감 정보는 마스킹, 유해 콘텐츠와 시스템 유출은 표시."""
    actions = []
    filtered_text = text

    # 민감 정보 마스킹
    for name, pattern in SENSITIVE_PATTERNS.items():
        if re.search(pattern, filtered_text):
            filtered_text = re.sub(pattern, "[MASKED]", filtered_text)
            actions.append(f"masked:{name}")

    # 유해 콘텐츠 탐지
    lower_text = filtered_text.lower()
    for pattern in HARMFUL_OUTPUT_PATTERNS:
        if re.search(pattern, lower_text, re.IGNORECASE):
            actions.append("harmful_content_detected")
            break

    # 시스템 프롬프트 유출 탐지
    for pattern in SYSTEM_LEAK_PATTERNS:
        if re.search(pattern, lower_text, re.IGNORECASE):
            actions.append("system_prompt_leak")
            break

    return {"text": filtered_text, "actions": actions}
