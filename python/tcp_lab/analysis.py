import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from .config import write_json


def events(directory: Path, kinds: set[str] | None = None):
    with (directory / "events.jsonl").open(encoding="utf-8") as source:
        for line in source:
            value = json.loads(line)
            if kinds is None or value["type"] in kinds:
                yield value


def quantiles(values) -> dict:
    if not values:
        return {"median": None, "p95": None, "p99": None, "count": 0}
    q = np.quantile(values, [0.5, 0.95, 0.99])
    return dict(zip(("median", "p95", "p99"), map(float, q))) | {"count": len(values)}


def jain(values: list[float]) -> float | None:
    denominator = sum(x * x for x in values)
    return sum(values) ** 2 / (len(values) * denominator) if denominator else None


def interval_metrics(data: dict, flows: list[dict], start: float, end: float) -> dict:
    receivers = data["receive"]
    delivered = {f["flow"]: 0 for f in flows}
    for event in receivers:
        if start <= event["time_s"] < end:
            delivered[event["flow"]] += event["bytes"]
    rates = {str(i): size * 8 / (end - start) for i, size in delivered.items()}
    busy = [0.0, 0.0]
    for event in data["link_tx"]:
        overlap = max(0, min(end, event["time_s"] + event["duration_s"])
                      - max(start, event["time_s"]))
        busy[event["direction"]] += overlap
    rtt = [e["ms"] for e in data["rtt"] if start <= e["time_s"] < end]
    delays = defaultdict(list)
    for event in data["queue_delay"]:
        if start <= event["time_s"] < end:
            delays[event["queue"]].append(event["delay_s"] * 1000)

    # 在连接实际加入和完成时划分区间，保留活跃但无交付的连接。
    cuts = {start, end}
    for flow in flows:
        for time in (flow["start_s"], flow["completed_at_s"]):
            if time is not None and start < time < end:
                cuts.add(time)
    cuts = sorted(cuts)
    fairness = []
    for a, b in zip(cuts, cuts[1:]):
        active = [f["flow"] for f in flows if f["start_s"] <= a
                  and (f["completed_at_s"] is None or f["completed_at_s"] > a)]
        sizes = {i: 0 for i in active}
        for event in receivers:
            if a <= event["time_s"] < b and event["flow"] in sizes:
                sizes[event["flow"]] += event["bytes"]
        by_direction = {}
        for reverse in (False, True):
            competitors = [f["flow"] for f in flows if f["flow"] in active
                           and f["reverse"] == reverse]
            by_direction[str(int(reverse))] = jain([sizes[i] for i in competitors])
        fairness.append({"start_s": a, "end_s": b, "active": active,
                         "jain": by_direction["0"], "direction_jain": by_direction})
    defined = [f for f in fairness if f["jain"] is not None]
    weight = sum(f["end_s"] - f["start_s"] for f in defined)
    mean_jain = (sum((f["end_s"] - f["start_s"]) * f["jain"] for f in defined) / weight
                 if weight else None)
    return {
        "start_s": start, "end_s": end, "goodput_bps": rates,
        "total_goodput_bps": sum(rates.values()),
        "shares": {i: value / sum(rates.values()) if sum(rates.values()) else None
                   for i, value in rates.items()},
        "utilization": [value / (end - start) for value in busy],
        "jain": mean_jain, "fairness_segments": fairness,
        "rtt_ms": quantiles(rtt),
        "queue_delay_ms": {name: quantiles(values) for name, values in delays.items()},
    }


def diagnose(directory: Path, data: dict) -> dict:
    matrix = defaultdict(lambda: defaultdict(int))
    rows = []
    decisions = directory / "decisions.jsonl"
    for line in decisions.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        observation, action = record["observation"], record["action"]
        end = observation["time_s"]
        flow = observation["flow"]
        queue = any(e["flow"] == flow and end - 1 <= e["time_s"] < end
                    for e in data["queue_drop"])
        error = any(e["flow"] == flow and end - 1 <= e["time_s"] < end
                    for e in data["error_drop"])
        actual = ("mixed_loss" if queue and error else "queue_loss" if queue else
                  "random_loss" if error else "no_loss")
        predicted = action["diagnosis"]
        matrix[actual][predicted] += 1
        rows.append({"decision_id": action["decision_id"], "actual": actual,
                     "predicted": predicted, "correct": actual == predicted})
    total = len(rows)
    answered = sum(row["predicted"] != "uncertain" for row in rows)
    correct = sum(row["correct"] for row in rows)
    return {"count": total, "accuracy": correct / total if total else None,
            "coverage": answered / total if total else None,
            "answered_accuracy": correct / answered if answered else None,
            "confusion": dict(matrix), "decisions": rows}


def recovery(data: dict, config: dict, references: list[Path]) -> list[dict]:
    capacities = {}
    for directory in references:
        ref_config = json.loads((directory / "config.json").read_text())
        ref_network = json.loads((directory / "network.json").read_text())
        if ref_network["error_drops"] or any(q["dropped"] for q in ref_network["queues"]):
            raise ValueError("容量参考运行必须没有丢包")
        metrics = json.loads((directory / "metrics.json").read_text())
        capacities[ref_config["rate_mbps"]] = metrics["intervals"][0]["total_goodput_bps"]
    result = []
    changes = config["changes"]
    for index, change in enumerate(changes):
        if change["rate_mbps"] is None:
            continue
        start = change["time_s"]
        end = changes[index + 1]["time_s"] if index + 1 < len(changes) else min(f["stop_s"] for f in config["flows"])
        target = capacities.get(change["rate_mbps"])
        entry = {"time_s": start, "rate_mbps": change["rate_mbps"],
                 "reference_bps": target, "recovery_s": None}
        if target is None:
            entry["status"] = "reference_required"
            result.append(entry)
            continue
        times = np.arange(start + 1, end, 0.1)
        reception = data["receive"]
        packet_times = np.array([e["time_s"] for e in reception])
        sums = np.concatenate(([0], np.cumsum([e["bytes"] for e in reception])))
        valid_since = None
        for time in times:
            left, right = np.searchsorted(packet_times, [time - 1, time], side="left")
            rate = (sums[right] - sums[left]) * 8
            if rate >= target * 0.9:
                if valid_since is None:
                    valid_since = float(time)
                if time - valid_since >= 3 - 1e-8:
                    entry["recovery_s"] = valid_since - start
                    break
            else:
                valid_since = None
        entry["status"] = "recovered" if entry["recovery_s"] is not None else "not_reached"
        result.append(entry)
    return result


def analyze(directory: Path, references: list[Path] | None = None) -> dict:
    config = json.loads((directory / "config.json").read_text())
    status = json.loads((directory / "status.json").read_text())
    if status["status"] != "complete":
        raise ValueError("性能分析要求完整结束的运行")
    network = json.loads((directory / "network.json").read_text())
    for flow in network["flows"]:
        flow["reverse"] = config["flows"][flow["flow"]]["reverse"]
    kinds = {"receive", "rtt", "queue_delay", "queue_drop", "error_drop", "link_tx",
             "congestion", "threshold_compute", "action"}
    data = defaultdict(list)
    for event in events(directory, kinds):
        data[event["type"]].append(event)
    result = {"name": config["name"], "run": config["run"],
              "intervals": [interval_metrics(data, network["flows"], a, b)
                            for a, b in config["evaluation"]],
              "flows": network["flows"], "diagnosis": diagnose(directory, data),
              "recovery": recovery(data, config, references or []),
              "threshold_updates": len(data["threshold_compute"]),
              "model_activations": len(data["action"]),
              "rto_events": sum(e["name"] == "CA_LOSS" for e in data["congestion"]),
              "error_drop_rate": network["error_drops"] / network["error_checks"]
              if network["error_checks"] else None,
              "queue_drop_rates": {q["queue"]: q["dropped"] / (q["enqueued"] + q["dropped"])
                                   if q["enqueued"] + q["dropped"] else None
                                   for q in network["queues"]}}
    latencies = [json.loads(p.read_text())["wall_seconds"]
                 for p in sorted((directory / "api").glob("*/transport.json"))]
    result["api_latency_s"] = quantiles(latencies)
    qualities = [json.loads(p.read_text()) for p in sorted((directory / "api").glob("*/quality.json"))]
    result["evidence_accuracy"] = (sum(q["evidence_correct"] for q in qualities) / len(qualities)
                                   if qualities else None)
    write_json(directory / "metrics.json", result)
    plot_run(directory)
    return result


def plot_run(directory: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    frame = pd.read_csv(directory / "samples.csv")
    plt.rcParams["font.family"] = "DejaVu Sans"
    fig, axes = plt.subplots(4, 1, figsize=(11, 11), sharex=True)
    for flow, rows in frame.groupby("flow"):
        dt = rows.time_s.diff()
        axes[0].plot(rows.time_s, rows.cwnd_bytes / 1448, label=f"Flow {flow}")
        threshold = rows.ssthresh_bytes.where(rows.ssthresh_bytes < 1e8) / 1448
        axes[0].plot(rows.time_s, threshold, linestyle="--", alpha=0.5)
        axes[1].plot(rows.time_s, rows.received_bytes.diff() * 8 / dt / 1e6)
        axes[2].plot(rows.time_s, rows.srtt_ms)
        axes[3].step(rows.time_s, rows.beta, where="post")
    for axis, label in zip(axes, ["cwnd / ssthresh (MSS)", "Goodput (Mbit/s)", "SRTT (ms)", "Beta"]):
        axis.set_ylabel(label)
        axis.grid(alpha=0.2)
    axes[0].legend()
    axes[-1].set_xlabel("Simulation time (s)")
    fig.tight_layout()
    fig.savefig(directory / "curves.png", dpi=160)
    fig.savefig(directory / "curves.pdf")
    plt.close(fig)
