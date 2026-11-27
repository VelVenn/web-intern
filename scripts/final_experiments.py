"""Run the clean 3-algorithm Topic 2 suite (reno, cubic, glm + fixed beta reference) in results/final/."""

import argparse
import asyncio
import json
from pathlib import Path
import shutil

from tcp_lab.analysis import analyze
from tcp_lab.config import Change, Flow, Scenario, load_scenario
from tcp_lab.runner import run_scenario
from tcp_lab.runtime import ROOT

OUT = ROOT / "results" / "final"
KEY_FILE = ROOT / "zhipu-api-key.txt"


def build_cases() -> dict[str, list[tuple[str, Scenario]]]:
    groups: dict[str, list[tuple[str, Scenario]]] = {"local": [], "glm": []}

    # 实验一：Reno 四阶段核验 + Reno vs CUBIC 稳态对比
    protocol_cfg = load_scenario(ROOT / "configs" / "protocol.json")
    groups["local"].append(("exp1-protocol-reno", protocol_cfg))
    for alg in ("reno", "cubic"):
        groups["local"].append((
            f"exp1-zoom-{alg}",
            Scenario(
                name=f"exp1-zoom-{alg}", seed=73, run=1, end_s=35,
                rate_mbps=20, delay_ms=20, queue_bytes=110000, start_jitter_s=0.0,
                flows=[Flow(algorithm=alg, start_s=1, stop_s=30)], evaluation=[(5, 30)],
            ),
        ))

    # 实验二：无线随机丢包（0.5% / 1.0%，各 3 次重复）
    for er, tag in ((0.005, "loss5"), (0.01, "loss10")):
        for alg in ("reno", "cubic", "glm"):
            bucket = "glm" if alg == "glm" else "local"
            for run in (1, 2, 3):
                groups[bucket].append((
                    f"exp2-{tag}-{alg}-{run:02d}",
                    Scenario(
                        name=f"exp2-{tag}-{alg}", seed=73, run=run, end_s=55,
                        rate_mbps=20, delay_ms=20, queue_bytes=110000, error_rate=er,
                        start_jitter_s=0.1, flows=[Flow(algorithm=alg, start_s=1, stop_s=50)],
                        evaluation=[(10, 50)],
                    ),
                ))

    # 实验三：纯带宽三档动态变化（14M 1×BDP 适中缓冲 -> 40M 扩容浅缓冲 -> 3M 深缓冲拥塞，75 KB 队列，20 ms 时延）
    exp3_changes = [
        Change(time_s=28, rate_mbps=40),
        Change(time_s=55, rate_mbps=3),
    ]
    exp3_eval = [(8, 27), (33, 54), (60, 81)]
    for alg in ("reno", "cubic", "glm"):
        bucket = "glm" if alg == "glm" else "local"
        for run in (1, 2, 3):
            groups[bucket].append((
                f"exp3-cap-{alg}-{run:02d}",
                Scenario(
                    name=f"exp3-cap-{alg}", seed=73, run=run, end_s=85,
                    rate_mbps=14, delay_ms=20, queue_bytes=75000, error_rate=0.0,
                    start_jitter_s=0.1, flows=[Flow(algorithm=alg, start_s=1, stop_s=82)],
                    changes=exp3_changes, evaluation=exp3_eval,
                ),
            ))
    for beta in (0.4, 0.6, 0.7, 0.8):
        for run in (1, 2, 3):
            groups["local"].append((
                f"exp3-cap-fixed{int(beta * 10)}-{run:02d}",
                Scenario(
                    name=f"exp3-cap-fixed{int(beta * 10)}", seed=73, run=run, end_s=85,
                    rate_mbps=14, delay_ms=20, queue_bytes=75000, error_rate=0.0,
                    start_jitter_s=0.1, flows=[Flow(algorithm="fixed", beta=beta, start_s=1, stop_s=82)],
                    changes=exp3_changes, evaluation=exp3_eval,
                ),
            ))

    # 实验四：路由切换传播时延增加（20 ms -> 40 ms，55 KB 队列，含误判拥塞参照 fixed 0.4）
    for alg in ("reno", "cubic", "glm"):
        bucket = "glm" if alg == "glm" else "local"
        for run in (1, 2, 3):
            groups[bucket].append((
                f"exp4-prop-{alg}-{run:02d}",
                Scenario(
                    name=f"exp4-prop-{alg}", seed=73, run=run, end_s=65,
                    rate_mbps=20, delay_ms=20, queue_bytes=55000, start_jitter_s=0.1,
                    flows=[Flow(algorithm=alg, start_s=1, stop_s=60)],
                    changes=[Change(time_s=25, delay_ms=40)],
                    evaluation=[(8, 25), (30, 60)],
                ),
            ))
    for run in (1, 2, 3):
        groups["local"].append((
            f"exp4-prop-fixed4-{run:02d}",
            Scenario(
                name="exp4-prop-fixed4", seed=73, run=run, end_s=65,
                rate_mbps=20, delay_ms=20, queue_bytes=55000, start_jitter_s=0.1,
                flows=[Flow(algorithm="fixed", beta=0.4, start_s=1, stop_s=60)],
                changes=[Change(time_s=25, delay_ms=40)],
                evaluation=[(8, 25), (30, 60)],
            ),
        ))

    # 实验五：三流稳态公平性（同构 3×Reno/3×CUBIC/3×GLM + 异构 2×Reno+1×CUBIC / 2×Reno+1×GLM / 三方混合）
    for run in (1, 2, 3):
        groups["glm"].append((
            f"exp5-homo-glm-{run:02d}",
            Scenario(
                name="exp5-homo-glm", seed=73, run=run, end_s=55,
                rate_mbps=20, delay_ms=20, queue_bytes=110000, start_jitter_s=0.1,
                flows=[Flow(algorithm="glm", start_s=1, stop_s=50) for _ in range(3)],
                evaluation=[(10, 50)],
            ),
        ))
        groups["glm"].append((
            f"exp5-reno-glm-{run:02d}",
            Scenario(
                name="exp5-reno-glm", seed=73, run=run, end_s=55,
                rate_mbps=20, delay_ms=20, queue_bytes=110000, start_jitter_s=0.1,
                flows=[
                    Flow(algorithm="reno", start_s=1, stop_s=50),
                    Flow(algorithm="reno", start_s=1, stop_s=50),
                    Flow(algorithm="glm", start_s=1, stop_s=50),
                ],
                evaluation=[(10, 50)],
            ),
        ))
        groups["glm"].append((
            f"exp5-mixed-glm-{run:02d}",
            Scenario(
                name="exp5-mixed-glm", seed=73, run=run, end_s=55,
                rate_mbps=20, delay_ms=20, queue_bytes=110000, start_jitter_s=0.1,
                flows=[
                    Flow(algorithm="reno", start_s=1, stop_s=50),
                    Flow(algorithm="cubic", start_s=1, stop_s=50),
                    Flow(algorithm="glm", start_s=1, stop_s=50),
                ],
                evaluation=[(10, 50)],
            ),
        ))
        groups["local"].append((
            f"exp5-reno-cubic-{run:02d}",
            Scenario(
                name="exp5-reno-cubic", seed=73, run=run, end_s=55,
                rate_mbps=20, delay_ms=20, queue_bytes=110000, start_jitter_s=0.1,
                flows=[
                    Flow(algorithm="reno", start_s=1, stop_s=50),
                    Flow(algorithm="reno", start_s=1, stop_s=50),
                    Flow(algorithm="cubic", start_s=1, stop_s=50),
                ],
                evaluation=[(10, 50)],
            ),
        ))
    for alg in ("reno", "cubic"):
        for run in (1, 2, 3):
            groups["local"].append((
                f"exp5-homo-{alg}-{run:02d}",
                Scenario(
                    name=f"exp5-homo-{alg}", seed=73, run=run, end_s=55,
                    rate_mbps=20, delay_ms=20, queue_bytes=110000, start_jitter_s=0.1,
                    flows=[Flow(algorithm=alg, start_s=1, stop_s=50) for _ in range(3)],
                    evaluation=[(10, 50)],
                ),
            ))

    return groups


def is_complete(directory: Path) -> bool:
    status_file = directory / "status.json"
    metrics_file = directory / "metrics.json"
    if not status_file.exists() or not metrics_file.exists():
        return False
    return json.loads(status_file.read_text()).get("status") == "complete"


async def run_group(part: str, max_retries: int = 2) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = build_cases()[part]
    print(f"=== Running part '{part}': {len(cases)} runs ===", flush=True)
    for idx, (folder, cfg) in enumerate(cases, 1):
        target = OUT / folder
        if is_complete(target):
            print(f"[{idx}/{len(cases)}] SKIP (complete) {folder}", flush=True)
            continue
        for attempt in range(1, max_retries + 2):
            if target.exists():
                shutil.rmtree(target)
            try:
                key = KEY_FILE if any(f.algorithm == "glm" for f in cfg.flows) else None
                await run_scenario(cfg, target, key_file=key)
                m = analyze(target)
                gp = [round(iv["total_goodput_bps"] / 1e6, 2) for iv in m["intervals"]]
                print(f"[{idx}/{len(cases)}] DONE {folder}: goodput={gp} Mbps", flush=True)
                break
            except Exception as exc:
                print(f"[{idx}/{len(cases)}] ERROR {folder} (attempt {attempt}): {exc}", flush=True)
                if attempt > max_retries:
                    raise
                await asyncio.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", choices=["local", "glm"], required=True)
    args = parser.parse_args()
    asyncio.run(run_group(args.part))


if __name__ == "__main__":
    main()
