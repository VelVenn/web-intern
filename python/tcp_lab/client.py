import asyncio
import copy
import hashlib
import json
import time
from importlib.resources import files
from pathlib import Path
from typing import Literal

import httpx
from filelock import AsyncFileLock
from pydantic import BaseModel, ConfigDict, Field

from .config import write_json
from .runtime import ROOT


MODEL = "glm-4-flash-250414"
ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
PROMPT = files("tcp_lab").joinpath("prompt.txt").read_text(encoding="utf-8")


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    window: int
    metric: str
    value: float


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    decision_id: str
    beta: Literal[0.4, 0.5, 0.6, 0.7, 0.8]
    diagnosis: Literal["queue_loss", "random_loss", "mixed_loss", "no_loss", "uncertain"]
    evidence: list[Evidence] = Field(min_length=1, max_length=2)
    reason: str = Field(min_length=1, max_length=200)


def model_input(observation: dict, ablation: str) -> dict:
    value = copy.deepcopy(observation)
    value["missing_features"] = []
    if ablation == "rtt_history":
        for row in value["history"][:-1]:
            for field in ("rtt_mean_ms", "rtt_p95_ms", "min_rtt_ms", "srtt_ms", "rtt_inflation"):
                row[field] = None
        value["missing_features"].append("rtt_history")
    if ablation == "retransmission":
        for row in value["history"]:
            row["retrans_bytes"] = None
            row["retransmission_ratio"] = None
        value["missing_features"].append("retransmission")
    if ablation == "feedback":
        value["previous_action"] = None
        value["missing_features"].append("feedback")
    return value


def evidence_correct(action: Action, observation: dict) -> bool:
    rows = {row["window"]: row for row in observation["history"]}
    for item in action.evidence:
        actual = rows.get(item.window, {}).get(item.metric)
        if not isinstance(actual, (int, float)) or abs(actual - item.value) > 1e-6:
            return False
    return True


class GlmClient:
    def __init__(self, key: str):
        self.lock = AsyncFileLock(ROOT / ".glm-api.lock", timeout=120)
        self.http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {key}"},
            timeout=httpx.Timeout(60, connect=10),
            transport=httpx.AsyncHTTPTransport(retries=0),
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def request(self, payload: dict, directory: Path) -> dict:
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / "request.json", payload)
        queued = time.monotonic()
        start = None
        completed = False
        try:
            # 同一项目的独立命令共享账户并发额度。
            async with self.lock:
                start = time.monotonic()
                async with asyncio.timeout(60):
                    response = await self.http.post(ENDPOINT, json=payload)
            (directory / "response.txt").write_text(response.text, encoding="utf-8")
            response.raise_for_status()
            body = response.json()
            if body["model"] != MODEL:
                raise ValueError("服务端返回的模型标识与配置不一致")
            if body["choices"][0]["finish_reason"] != "stop":
                raise ValueError("模型响应未完整结束")
            completed = True
            return body
        finally:
            write_json(directory / "transport.json", {
                "completed": completed,
                "queue_seconds": (start if start is not None else time.monotonic()) - queued,
                "wall_seconds": time.monotonic() - start if start is not None else None,
            })
            # 释放锁后给其他命令获取锁的机会。
            await asyncio.sleep(0.1)

    async def decide(self, observation: dict, directory: Path, ablation="none") -> Action:
        value = model_input(observation, ablation)
        payload = {
            "model": MODEL, "stream": False, "do_sample": False, "max_tokens": 512,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": PROMPT},
                         {"role": "user", "content": json.dumps(value, ensure_ascii=False)}],
        }
        body = await self.request(payload, directory)
        action = Action.model_validate_json(body["choices"][0]["message"]["content"])
        if action.decision_id != observation["decision_id"]:
            raise ValueError("模型返回的决策编号不一致")
        write_json(directory / "action.json", action.model_dump())
        write_json(directory / "quality.json", {
            "evidence_correct": evidence_correct(action, value),
            "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
            "usage": body.get("usage"),
        })
        return action

    async def preflight(self, directory: Path) -> dict:
        body = await self.request({
            "model": MODEL, "stream": False, "do_sample": False, "max_tokens": 128,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": '请输出 JSON 对象 {"ready":true}。'}],
        }, directory)
        if json.loads(body["choices"][0]["message"]["content"]) != {"ready": True}:
            raise ValueError("模型接口预检响应不符合要求")
        return {"model": body["model"], "ready": True}
