import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Flow(StrictModel):
    algorithm: Literal["reno", "cubic", "glm", "fixed"] = "reno"
    beta: Literal[0.4, 0.5, 0.6, 0.7, 0.8] = 0.5
    start_s: float = Field(default=1, ge=0)
    stop_s: float = Field(default=180, gt=0)
    access_delay_ms: float = Field(default=1, gt=0)
    reverse: bool = False

    @model_validator(mode="after")
    def ordered(self):
        if self.stop_s <= self.start_s:
            raise ValueError("连接停止时间必须晚于启动时间")
        return self


class Change(StrictModel):
    time_s: float = Field(gt=0)
    rate_mbps: float | None = Field(default=None, gt=0)
    delay_ms: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def has_action(self):
        if self.rate_mbps is None and self.delay_ms is None:
            raise ValueError("网络变化必须指定容量或传播时延")
        return self


class Scenario(StrictModel):
    name: str = Field(default="stable", pattern=r"^[A-Za-z0-9_-]+$")
    seed: int = Field(default=73, ge=1, le=2147483647)
    run: int = Field(default=1, ge=1)
    end_s: float = Field(default=210, gt=0)
    rate_mbps: float = Field(default=20, gt=0)
    delay_ms: float = Field(default=20, gt=0)
    queue_bytes: int = Field(default=110000, ge=1500)
    error_rate: float = Field(default=0, ge=0, le=1)
    start_jitter_s: float = Field(default=0.1, ge=0, le=0.1)
    decision_delay_s: float = Field(default=0, ge=0, le=1)
    sample_s: float = Field(default=0.1, gt=0)
    initial_cwnd: int = Field(default=10, ge=1)
    initial_ssthresh: int = Field(default=4294967295, ge=2896, le=4294967295)
    sack: bool = True
    delayed_ack: int = Field(default=2, ge=1, le=2)
    recovery: Literal["prr", "classic"] = "prr"
    pcap: bool = False
    packet_events: bool = False
    drop_indices: list[int] = Field(default_factory=list)
    outage_start_s: float | None = Field(default=None, gt=0)
    outage_end_s: float | None = Field(default=None, gt=0)
    ablation: Literal["none", "rtt_history", "retransmission", "feedback"] = "none"
    flows: list[Flow] = Field(default_factory=lambda: [Flow()], min_length=1, max_length=32)
    changes: list[Change] = Field(default_factory=list)
    evaluation: list[tuple[float, float]] = Field(default_factory=lambda: [(20, 180)])

    @model_validator(mode="after")
    def consistency(self):
        if any(f.stop_s >= self.end_s or f.start_s + self.start_jitter_s >= f.stop_s
               for f in self.flows):
            raise ValueError("连接时间与仿真截止时间冲突")
        if any(not 0 <= a < b <= self.end_s for a, b in self.evaluation):
            raise ValueError("评价区间必须位于仿真范围内")
        times = [c.time_s for c in self.changes]
        if times != sorted(set(times)) or any(t >= self.end_s for t in times):
            raise ValueError("网络变化时间必须严格递增并早于截止时间")
        if any(i < 0 for i in self.drop_indices):
            raise ValueError("丢弃序号必须非负")
        if self.drop_indices and (self.error_rate or self.outage_start_s is not None):
            raise ValueError("确定性丢弃场景需要独立的错误模型")
        if (self.outage_start_s is None) != (self.outage_end_s is None):
            raise ValueError("中断场景必须同时指定开始和结束时间")
        if self.outage_start_s is not None:
            if not self.outage_start_s < self.outage_end_s < self.end_s:
                raise ValueError("中断时间区间无效")
        return self


def load_scenario(path: Path) -> Scenario:
    return Scenario.model_validate_json(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")
