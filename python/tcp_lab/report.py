import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t

from .config import write_json


def confidence(values: list[float]) -> dict:
    samples = np.array(values, dtype=float)
    mean = float(samples.mean())
    radius = (float(t.ppf(0.975, len(samples) - 1) * samples.std(ddof=1) / np.sqrt(len(samples)))
              if len(samples) > 1 else None)
    return {"n": len(samples), "mean": mean,
            "lower95": mean - radius if radius is not None else None,
            "upper95": mean + radius if radius is not None else None}


def report(directory: Path) -> Path:
    rows, statuses = [], []
    for file in sorted(directory.rglob("status.json")):
        status = json.loads(file.read_text())
        statuses.append({"directory": str(file.parent.relative_to(directory)), **status})
        if status["status"] != "complete" or not (file.parent / "metrics.json").exists():
            continue
        config = json.loads((file.parent / "config.json").read_text())
        metrics = json.loads((file.parent / "metrics.json").read_text())
        for interval in metrics["intervals"]:
            rows.append({"case": config["name"], "run": config["run"],
                "start_s": interval["start_s"], "end_s": interval["end_s"],
                "goodput_mbps": interval["total_goodput_bps"] / 1e6,
                "jain": interval["jain"], "rtt_p95_ms": interval["rtt_ms"]["p95"]})
    if not rows:
        raise ValueError("没有可汇总的完整运行指标")
    frame = pd.DataFrame(rows)
    frame.to_csv(directory / "runs.csv", index=False)
    summary = []
    for (case, start, end), values in frame.groupby(["case", "start_s", "end_s"]):
        result = {"case": case, "start_s": start, "end_s": end}
        for metric in ("goodput_mbps", "jain", "rtt_p95_ms"):
            sample = values[metric].dropna().tolist()
            result[metric] = confidence(sample) if sample else None
        summary.append(result)
    paired = []
    names = set(frame["case"])
    for name in sorted(names):
        if not name.endswith(("-cubic", "-glm")):
            continue
        baseline = name.rsplit("-", 1)[0] + "-reno"
        if baseline not in names:
            continue
        left = frame[frame["case"] == name]
        right = frame[frame["case"] == baseline]
        for (start, end), group in left.groupby(["start_s", "end_s"]):
            reference = right[(right.start_s == start) & (right.end_s == end)]
            common = set(group.run) & set(reference.run)
            if not common:
                continue
            values = {"case": name, "baseline": baseline, "start_s": start, "end_s": end,
                      "unpaired_runs": sorted(set(group.run) ^ set(reference.run))}
            for metric in ("goodput_mbps", "jain", "rtt_p95_ms"):
                x = group.set_index("run")[metric].to_dict()
                y = reference.set_index("run")[metric].to_dict()
                valid = sorted(i for i in common if pd.notna(x[i]) and pd.notna(y[i]))
                values[metric] = paired_difference({i: x[i] for i in valid}, {i: y[i] for i in valid}) if valid else None
            paired.append(values)
    attempts = [json.loads(path.read_text()) for path in directory.rglob("transport.json")]
    api = {"attempts": len(attempts), "transport_completed": sum(a["completed"] for a in attempts),
           "transport_failed": sum(not a["completed"] for a in attempts)}
    write_json(directory / "summary.json", {
        "runs": statuses, "statistics": summary, "paired": paired, "api": api,
    })
    plot_comparison(frame, directory)
    return directory / "summary.json"


def paired_difference(left: dict[int, float], right: dict[int, float]) -> dict:
    if left.keys() != right.keys():
        raise ValueError("配对比较要求相同的独立运行编号")
    return confidence([left[run] - right[run] for run in sorted(left)])


def plot_comparison(frame: pd.DataFrame, directory: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    summary = frame.groupby("case").goodput_mbps.mean()
    fig, axis = plt.subplots(figsize=(10, max(3, 0.3 * len(summary))))
    axis.barh(summary.index, summary.values)
    axis.set_xlabel("Mean goodput over reported intervals (Mbit/s)")
    fig.tight_layout()
    fig.savefig(directory / "comparison.png", dpi=160)
    fig.savefig(directory / "comparison.pdf")
    plt.close(fig)
