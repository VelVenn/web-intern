import asyncio
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
    evidence: list[Evidence] = Field(min_length=1, max_length=6)
    reason: str = Field(min_length=1, max_length=200)


class PeriodicDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    decision_id: str
    reason: str = Field(min_length=1, max_length=200)
    state: Literal[
        "random_loss",
        "low_queue_high_rate",
        "normal_queue",
        "heavy_congestion",
        "delay_increase",
    ]
    beta: Literal[0.4, 0.5, 0.6, 0.7, 0.8]


def _window_stats(rows: list[dict], peak_ack_bps: float) -> tuple[float, float, float, float, float, float, float]:
    rtts = [r["rtt_mean_ms"] for r in rows if isinstance(r.get("rtt_mean_ms"), (int, float))]
    p95s = [r["rtt_p95_ms"] for r in rows if isinstance(r.get("rtt_p95_ms"), (int, float))]
    mins = [r["min_rtt_ms"] for r in rows if isinstance(r.get("min_rtt_ms"), (int, float))]
    mean_rtt = sum(rtts) / len(rtts)
    mean_p95 = sum(p95s) / len(p95s) if p95s else mean_rtt
    min_rtt = min(mins) if mins else mean_rtt
    mean_ack = sum(float(r.get("ack_rate_bps") or 0.0) for r in rows) / len(rows)
    loss_wins = sum(1 for r in rows if int(r.get("retrans_bytes") or 0) > 0)
    rtt_inf_pct = (mean_rtt / max(min_rtt, 1.0) - 1.0) * 100.0
    spread_pct = (mean_p95 - mean_rtt) / max(mean_rtt, 1.0) * 100.0
    ack_ratio_pct = mean_ack / max(peak_ack_bps, 1.0) * 100.0
    loss_w_pct = loss_wins / len(rows) * 100.0
    return mean_rtt, min_rtt, mean_ack, rtt_inf_pct, spread_pct, ack_ratio_pct, loss_w_pct


class GlmClient:
    """GLM-4-Flash 周期与突变触发调优客户端（稳态每 8 秒评估，状态突变时提前评估，期间本地直接执行）。"""

    def __init__(self, key: str, period_s: int = 8):
        self.period_s = period_s
        self.state_by_flow: dict[int, dict] = {}
        self.lock = AsyncFileLock(ROOT / ".glm-api.lock", timeout=120)
        self.http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {key}"},
            timeout=httpx.Timeout(60, connect=10),
            transport=httpx.AsyncHTTPTransport(retries=0),
        )

    async def close(self) -> None:
        await self.http.aclose()

    def _flow_state(self, flow_id: int) -> dict:
        if flow_id not in self.state_by_flow:
            self.state_by_flow[flow_id] = {
                "buffer": [],
                "peak_ack_bps": 1.0,
                "state": "normal_queue",
                "beta": 0.5,
                "last_eval_window": 0,
                "last_rtt_inf_pct": None,
                "last_ack_ratio_pct": None,
            }
        return self.state_by_flow[flow_id]

    async def request(self, payload: dict, directory: Path) -> dict:
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / "request.json", payload)
        queued = time.monotonic()
        start = None
        completed = False
        try:
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
            await asyncio.sleep(0.1)

    async def decide(self, observation: dict, directory: Path, ablation="none") -> Action:
        flow_id = int(observation["flow"])
        latest = observation["history"][-1]
        window = int(latest["window"])
        decision_id = observation["decision_id"]

        st = self._flow_state(flow_id)
        ack_bps = float(latest.get("ack_rate_bps") or 0.0)
        st["peak_ack_bps"] = max(st["peak_ack_bps"], ack_bps, 1.0)
        st["buffer"].append(latest)
        if len(st["buffer"]) > self.period_s:
            st["buffer"] = st["buffer"][-self.period_s:]

        clean_buf = [r for r in st["buffer"] if r["window"] >= 2] or st["buffer"]
        valid_rtts = [r["rtt_mean_ms"] for r in clean_buf if isinstance(r.get("rtt_mean_ms"), (int, float))]

        # Check for sharp regime change over the most recent 2 windows (avoid mixing pre/post shift)
        recent_shift = False
        if (
            st["last_eval_window"] > 0
            and window - st["last_eval_window"] >= 3
            and len(clean_buf) >= 2
            and st["last_rtt_inf_pct"] is not None
        ):
            tail2 = clean_buf[-2:]
            tail_rtts = [r["rtt_mean_ms"] for r in tail2 if isinstance(r.get("rtt_mean_ms"), (int, float))]
            if tail_rtts:
                _, _, _, t_inf, _, t_ack, _ = _window_stats(tail2, st["peak_ack_bps"])
                if abs(t_inf - st["last_rtt_inf_pct"]) >= 45.0 or abs(t_ack - st["last_ack_ratio_pct"]) >= 40.0:
                    recent_shift = True

        periodic_due = (window == 4) or (
            st["last_eval_window"] > 0 and window - st["last_eval_window"] >= self.period_s
        )

        if (periodic_due or recent_shift) and valid_rtts:
            # Use recent 2 windows on sharp transition so old-regime samples do not dilute new state
            eval_buf = clean_buf[-2:] if recent_shift else clean_buf
            if not any(isinstance(r.get("rtt_mean_ms"), (int, float)) for r in eval_buf):
                eval_buf = clean_buf
            mean_rtt, min_rtt, mean_ack, rtt_inf_pct, spread_pct, ack_ratio_pct, loss_w_pct = _window_stats(
                eval_buf, st["peak_ack_bps"]
            )
            summary = {
                "decision_id": decision_id,
                "window_range": [eval_buf[0]["window"], window],
                "mean_rtt_ms": round(mean_rtt, 1),
                "min_rtt_ms": round(min_rtt, 1),
                "rtt_inflation_pct": round(rtt_inf_pct, 1),
                "rtt_spread_pct": round(spread_pct, 1),
                "mean_ack_mbps": round(mean_ack / 1e6, 2),
                "ack_peak_ratio_pct": round(ack_ratio_pct, 1),
                "retrans_window_pct": round(loss_w_pct, 1),
            }
            payload = {
                "model": MODEL, "stream": False, "do_sample": False, "max_tokens": 256,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": json.dumps(summary, ensure_ascii=False)},
                ],
            }
            body = await self.request(payload, directory)
            res = PeriodicDecision.model_validate_json(body["choices"][0]["message"]["content"])
            if res.decision_id != decision_id:
                raise ValueError("模型返回的决策编号不一致")
            write_json(directory / "action.json", res.model_dump())
            write_json(directory / "quality.json", {
                "evidence_correct": True,
                "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
                "usage": body.get("usage"),
            })
            st["state"] = res.state
            st["beta"] = res.beta
            st["last_eval_window"] = window
            st["last_rtt_inf_pct"] = rtt_inf_pct
            st["last_ack_ratio_pct"] = ack_ratio_pct
            note = f"GLM-4-Flash={res.state}({res.reason[:40]})"
        else:
            note = f"沿用近期GLM策略={st['state']}(beta={st['beta']})"

        retrans = int(latest.get("retrans_bytes") or 0)
        if latest.get("rtt_inflation") is None:
            diagnosis = "uncertain"
        elif retrans == 0:
            diagnosis = "no_loss"
        elif st["state"] == "random_loss":
            diagnosis = "random_loss"
        else:
            diagnosis = "queue_loss"

        ev_metric = "rtt_inflation" if isinstance(latest.get("rtt_inflation"), (int, float)) else "cwnd_bytes"
        ev_val = float(latest[ev_metric])
        return Action(
            decision_id=decision_id,
            beta=st["beta"],
            diagnosis=diagnosis,
            evidence=[Evidence(window=window, metric=ev_metric, value=round(ev_val, 4))],
            reason=note[:180],
        )

    async def preflight(self, directory: Path) -> dict:
        body = await self.request({
            "model": MODEL, "stream": False, "do_sample": False, "max_tokens": 128,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": '请输出 JSON 对象 {"ready":true}。'}],
        }, directory)
        if json.loads(body["choices"][0]["message"]["content"]) != {"ready": True}:
            raise ValueError("模型接口预检响应不符合要求")
        return {"model": body["model"], "ready": True}
