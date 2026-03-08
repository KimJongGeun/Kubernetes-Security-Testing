"""
입출력 보안 필터

Garak 스캔 결과를 기반으로 만든 탐지 패턴들.
- 입력: 프롬프트 인젝션, 탈옥 시도, 인코딩 우회 탐지
- 출력: 민감 정보 노출, 유해 콘텐츠 탐지
"""

import re

# --- 입력 필터 패턴 ---

# 프롬프트 인젝션: 기존 지시를 무시하라는 패턴
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|directions?)",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)",
    r"forget\s+(all\s+)?(previous|prior|your)\s+(instructions?|prompts?|rules?)",
    r"override\s+(your|all|the)\s+(instructions?|rules?|guidelines?)",
    r"new\s+instructions?\s*:",
    r"system\s*prompt\s*:",
    r"you\s+are\s+now\s+(a|an|the)\s+",
    r"act\s+as\s+(a|an|if)\s+",
    r"pretend\s+(you\s+are|to\s+be)\s+",
]

# 탈옥 시도: DAN, 역할 탈출 패턴
JAILBREAK_PATTERNS = [
    r"do\s+anything\s+now",
    r"\bDAN\b",
    r"jailbreak",
    r"developer\s+mode",
    r"bypass\s+(your\s+)?(safety|filter|restriction|guideline)",
    r"without\s+(any\s+)?(restriction|filter|safety|limit)",
    r"no\s+(ethical|moral|safety)\s+(guideline|restriction|filter)",
]

# 인코딩 우회: base64, rot13 등으로 숨긴 명령
ENCODING_PATTERNS = [
    r"base64\s*(decode|encode)",
    r"rot13",
    r"decode\s+this\s*:",
    r"hex\s*(decode|encode)",
]


def check_input(prompt: str) -> dict:
    """입력 프롬프트를 검증한다. 위험하면 blocked=True."""
    text = prompt.lower()

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text):
            return {"blocked": True, "reason": "prompt_injection"}

    for pattern in JAILBREAK_PATTERNS:
        if re.search(pattern, text):
            return {"blocked": True, "reason": "jailbreak_attempt"}

    for pattern in ENCODING_PATTERNS:
        if re.search(pattern, text):
            return {"blocked": True, "reason": "encoding_bypass"}

    return {"blocked": False, "reason": None}


# --- 출력 필터 패턴 ---

# 민감 정보: 주민번호, 카드번호, 이메일 등
SENSITIVE_PATTERNS = {
    "주민등록번호": r"\d{6}\s*-\s*[1-4]\d{6}",
    "카드번호": r"\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}",
    "전화번호": r"01[016789][\s-]\d{3,4}[\s-]\d{4}",
}

# 유해 응답 키워드
HARMFUL_PATTERNS = [
    r"i\s+hate\s+humans?",
    r"kill\s+all\s+humans?",
    r"here\s+is\s+(the\s+)?(malware|virus|exploit|ransomware)",
    r"import\s+subprocess.*shell\s*=\s*True",
]


def check_output(text: str) -> dict:
    """LLM 출력을 검증한다. 민감 정보는 마스킹, 유해 콘텐츠는 표시."""
    actions = []
    filtered_text = text

    # 민감 정보 마스킹
    for name, pattern in SENSITIVE_PATTERNS.items():
        if re.search(pattern, filtered_text):
            filtered_text = re.sub(pattern, "[MASKED]", filtered_text)
            actions.append(f"masked:{name}")

    # 유해 콘텐츠 탐지
    lower_text = filtered_text.lower()
    for pattern in HARMFUL_PATTERNS:
        if re.search(pattern, lower_text):
            actions.append("harmful_content_detected")
            break

    return {"text": filtered_text, "actions": actions}
