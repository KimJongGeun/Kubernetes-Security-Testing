import time
import logging

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from filters import check_input, check_output

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("llm-proxy")

OLLAMA_URL = "http://ollama.ollama.svc.cluster.local:11434"

app = FastAPI(title="LLM Security Proxy")


class ChatRequest(BaseModel):
    model: str = "llama3.2:1b"
    prompt: str
    stream: bool = False


class ChatResponse(BaseModel):
    response: str
    blocked: bool = False
    block_reason: str | None = None
    risk_score: int = 0
    filtered: bool = False
    filter_actions: list[str] = []
    latency_ms: float = 0


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(req: ChatRequest):
    start = time.time()

    # 입력 검증
    input_result = check_input(req.prompt)
    if input_result["blocked"]:
        logger.warning(
            f"BLOCKED input: reason={input_result['reason']}, "
            f"score={input_result['score']}, "
            f"prompt={req.prompt[:100]}"
        )
        return ChatResponse(
            response="",
            blocked=True,
            block_reason=input_result["reason"],
            risk_score=input_result["score"],
            latency_ms=(time.time() - start) * 1000,
        )

    # 점수가 있지만 차단은 안 된 경우 로그
    if input_result["score"] > 0:
        logger.info(
            f"LOW RISK input: score={input_result['score']}, "
            f"details={input_result['details']}"
        )

    # LLM 호출
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": req.model, "prompt": req.prompt, "stream": False},
            )
            resp.raise_for_status()
            llm_response = resp.json().get("response", "")
    except httpx.HTTPError as e:
        logger.error(f"LLM request failed: {e}")
        return JSONResponse(status_code=502, content={"error": "LLM request failed"})

    # 출력 검증
    output_result = check_output(llm_response)
    final_response = output_result["text"]
    filter_actions = output_result["actions"]

    if filter_actions:
        logger.warning(f"FILTERED output: actions={filter_actions}")

    latency = (time.time() - start) * 1000
    logger.info(f"request processed: model={req.model}, latency={latency:.0f}ms, filtered={bool(filter_actions)}")

    return ChatResponse(
        response=final_response,
        risk_score=input_result["score"],
        filtered=bool(filter_actions),
        filter_actions=filter_actions,
        latency_ms=latency,
    )
