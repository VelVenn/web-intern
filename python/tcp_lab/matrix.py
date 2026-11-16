import json
from itertools import combinations, permutations
from pathlib import Path

from .config import Change, Flow, Scenario, load_scenario, write_json
from .runner import run_scenario


def cases() -> list[Scenario]:
    scenarios = []
    algorithms = ["reno", "cubic", "glm"]
    for algorithm in algorithms:
        base = dict(flows=[Flow(algorithm=algorithm)])
        for capacity in (5, 20, 50):
            scenarios.append(Scenario(name=f"stable-{capacity}-{algorithm}", rate_mbps=capacity, **base))
        scenarios.append(Scenario(name=f"capacity-{algorithm}", **base,
            changes=[Change(time_s=60, rate_mbps=5), Change(time_s=120, rate_mbps=20)],
            evaluation=[(20, 60), (80, 120), (140, 180)]))
        for probability in (0.001, 0.005, 0.01):
            scenarios.append(Scenario(name=f"loss-{probability * 1000:g}-{algorithm}",
                                      error_rate=probability, **base))
        for size in (2, 4, 8):
            scenarios.append(Scenario(name=f"homogeneous-{size}-{algorithm}",
                flows=[Flow(algorithm=algorithm) for _ in range(size)]))
        scenarios.append(Scenario(name=f"rtt-homogeneous-{algorithm}",
            flows=[Flow(algorithm=algorithm, access_delay_ms=d) for d in (1, 21)]))
        scenarios.append(Scenario(name=f"arrivals-{algorithm}",
            flows=[Flow(algorithm=algorithm) for _ in range(4)] +
                  [Flow(algorithm=algorithm, start_s=60, stop_s=120) for _ in range(4)],
            evaluation=[(20, 60), (80, 120), (140, 180)]))
        for factor in (0.25, 1, 4):
            scenarios.append(Scenario(name=f"queue-{factor:g}-{algorithm}".replace(".", "_"),
                                      queue_bytes=int(110000 * factor), **base))
        scenarios.append(Scenario(name=f"propagation-{algorithm}", **base,
            changes=[Change(time_s=60, delay_ms=40)], evaluation=[(20, 60), (80, 180)]))
        scenarios.append(Scenario(name=f"reverse-{algorithm}",
            flows=[Flow(algorithm=algorithm), Flow(algorithm="cubic", reverse=True, start_s=60, stop_s=120)],
            evaluation=[(20, 60), (80, 120), (140, 180)]))

    for pair in combinations(algorithms, 2):
        for order in permutations(pair):
            tag = "-".join(order)
            scenarios.append(Scenario(name=f"mixed-{tag}", flows=[Flow(algorithm=a) for a in order]))
            for delays in ((1, 21), (21, 1)):
                scenarios.append(Scenario(name=f"rtt-{tag}-{delays[0]}",
                    flows=[Flow(algorithm=a, access_delay_ms=d) for a, d in zip(order, delays)]))
    for order in permutations(algorithms):
        scenarios.append(Scenario(name="mixed-" + "-".join(order),
                                  flows=[Flow(algorithm=a) for a in order]))
    for delay in (0, 0.1, 0.5, 1):
        scenarios.append(Scenario(name=f"delay-{int(delay * 1000)}", decision_delay_s=delay,
            flows=[Flow(algorithm="glm")],
            changes=[Change(time_s=60, rate_mbps=5), Change(time_s=120, rate_mbps=20)],
            evaluation=[(20, 60), (80, 120), (140, 180)]))
    for beta in (0.4, 0.5, 0.6, 0.7, 0.8):
        for varying in (False, True):
            scenarios.append(Scenario(name=f"fixed-{int(beta * 10)}-{'capacity' if varying else 'stable'}",
                flows=[Flow(algorithm="fixed", beta=beta)],
                changes=[Change(time_s=60, rate_mbps=5), Change(time_s=120, rate_mbps=20)] if varying else [],
                evaluation=[(20, 60), (80, 120), (140, 180)] if varying else [(20, 180)]))
    for ablation in ("none", "rtt_history", "retransmission", "feedback"):
        scenarios.append(Scenario(name=f"ablation-{ablation}", ablation=ablation,
            flows=[Flow(algorithm="glm")], error_rate=0.005,
            changes=[Change(time_s=60, rate_mbps=5), Change(time_s=120, rate_mbps=20)],
            evaluation=[(20, 60), (80, 120), (140, 180)]))
    for capacity in (5, 20, 50):
        scenarios.append(Scenario(name=f"reference-{capacity}", rate_mbps=capacity,
            end_s=20, initial_cwnd=1000, initial_ssthresh=1448000, queue_bytes=16777216,
            start_jitter_s=0, flows=[Flow(stop_s=10)], evaluation=[(4, 10)]))
    return scenarios


def generate(directory: Path, repeats: int) -> Path:
    if repeats < 1:
        raise ValueError("重复次数必须为正数")
    directory.mkdir(parents=True, exist_ok=False)
    records = []
    for case in cases():
        for run in range(1, repeats + 1):
            config = case.model_copy(update={"run": run})
            name = f"{case.name}-{run:02d}.json"
            write_json(directory / name, config.model_dump(mode="json"))
            records.append({"config": name, "name": case.name, "run": run, "status": "planned"})
    manifest = directory / "manifest.json"
    write_json(manifest, {"repeats": repeats, "cases": records})
    return manifest


async def run_suite(manifest: Path, directory: Path, key_file: Path | None):
    from .analysis import analyze

    entries = json.loads(manifest.read_text())["cases"]
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "suite.json", entries)
    for entry in entries:
        case = load_scenario(manifest.parent / entry["config"])
        output = directory / f"{case.name}-{case.run:02d}"
        entry["status"] = "running"
        entry["directory"] = output.name
        write_json(directory / "suite.json", entries)
        done = False
        try:
            await run_scenario(case, output, key_file=key_file)
            analyze(output)
            done = True
        finally:
            entry["status"] = "complete" if done else "failed"
            write_json(directory / "suite.json", entries)
        print(f"完成 {output.name}", flush=True)
