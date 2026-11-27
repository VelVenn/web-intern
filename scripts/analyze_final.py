"""Aggregate metrics and generate clean 3-algorithm (Reno, CUBIC, GLM-4-Flash) figures in results/final/."""

from collections import Counter
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FINAL = ROOT / "results" / "final"
FIGDIR = FINAL / "figures"
FIGDIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["PingFang SC", "Hiragino Sans GB", "Heiti SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["axes.spines.top"] = False
plt.rcParams["axes.spines.right"] = False
plt.rcParams["font.size"] = 10.5

COLORS = {
    "reno": "#2563EB",   # blue
    "cubic": "#EA580C",  # orange
    "glm": "#7C3AED",    # purple
}
LABELS = {
    "reno": "Reno (固定 0.5)",
    "cubic": "CUBIC (固定 0.7)",
    "glm": "AI 策略 (GLM-4-Flash)",
}
SHORT = {
    "reno": "Reno",
    "cubic": "CUBIC",
    "glm": "GLM-4-Flash",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def mean_std(vals: list[float]) -> tuple[float, float]:
    if not vals:
        return 0.0, 0.0
    m = statistics.mean(vals)
    s = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return m, s


def read_beta_counts(run_dir: Path) -> Counter:
    counts = Counter()
    dec = run_dir / "decisions.jsonl"
    if dec.exists() and dec.stat().st_size > 0:
        for line in dec.read_text(encoding="utf-8").splitlines():
            counts[json.loads(line)["action"]["beta"]] += 1
    return counts


def count_api_calls(run_dir: Path) -> tuple[int, list[float]]:
    lats = []
    api_dir = run_dir / "api"
    if api_dir.exists():
        for p in sorted(api_dir.glob("*/transport.json")):
            d = load_json(p)
            if d.get("wall_seconds") is not None:
                lats.append(float(d["wall_seconds"]))
    return len(lats), lats


def collect_stats() -> dict:
    stats: dict = {}

    # Exp 1a: Reno 4-phase
    d = FINAL / "exp1-protocol-reno"
    net = load_json(d / "network.json")
    evs = [json.loads(line) for line in (d / "events.jsonl").read_text().splitlines()]
    drop_t = next(e["time_s"] for e in evs if e["type"] == "error_drop")
    retrans_t = next(e["time_s"] for e in evs if e["type"] == "retransmission")
    rec_t = next(e["time_s"] for e in evs if e["type"] == "congestion" and e["name"] == "CA_RECOVERY")
    open_t = next(e["time_s"] for e in evs if e["type"] == "congestion" and e["name"] == "CA_OPEN" and e["time_s"] > rec_t)
    th = next(e for e in evs if e["type"] == "threshold_compute")
    stats["exp1_protocol"] = {
        "sent_bytes": net["flows"][0]["sent_bytes"],
        "received_bytes": net["flows"][0]["received_bytes"],
        "retrans_bytes": net["flows"][0]["retrans_bytes"],
        "drop_s": round(drop_t, 4),
        "retrans_s": round(retrans_t, 4),
        "recovery_enter_s": round(rec_t, 4),
        "recovery_exit_s": round(open_t, 4),
        "cwnd_at_loss_mss": round(th["cwnd_bytes"] / 1448, 2),
        "ssthresh_after_loss_mss": round(th["ssthresh_bytes"] / 1448, 2),
        "queue_drops": sum(q["dropped"] for q in net["queues"]),
        "error_drops": net["error_drops"],
    }

    # Exp 1b: Reno vs CUBIC zoom
    stats["exp1_zoom"] = {}
    for alg in ("reno", "cubic"):
        m = load_json(FINAL / f"exp1-zoom-{alg}" / "metrics.json")
        iv = m["intervals"][0]
        stats["exp1_zoom"][alg] = {
            "goodput_mbps": round(iv["total_goodput_bps"] / 1e6, 3),
            "rtt_median_ms": round(iv["rtt_ms"]["median"], 2),
            "rtt_p95_ms": round(iv["rtt_ms"]["p95"], 2),
            "queue_drop_pct": round((m["queue_drop_rates"].get("0_disc") or 0) * 100, 4),
        }

    # Exp 2: Random Loss
    stats["exp2_random_loss"] = {}
    for tag in ("loss5", "loss10"):
        stats["exp2_random_loss"][tag] = {}
        for alg in ("reno", "cubic", "glm"):
            gps, rtt_m, rtt_95, retrans_pct, api_cnts, api_waits = [], [], [], [], [], []
            betas = Counter()
            for r in (1, 2, 3):
                rd = FINAL / f"exp2-{tag}-{alg}-{r:02d}"
                m = load_json(rd / "metrics.json")
                net = load_json(rd / "network.json")
                iv = m["intervals"][0]
                gps.append(iv["total_goodput_bps"] / 1e6)
                rtt_m.append(iv["rtt_ms"]["median"])
                rtt_95.append(iv["rtt_ms"]["p95"])
                f0 = net["flows"][0]
                retrans_pct.append(f0["retrans_bytes"] / f0["tx_bytes"] * 100)
                cnt, lats = count_api_calls(rd)
                api_cnts.append(cnt)
                api_waits.append(sum(lats))
                betas.update(read_beta_counts(rd))
            gm, gs = mean_std(gps)
            stats["exp2_random_loss"][tag][alg] = {
                "goodput_mean": round(gm, 3),
                "goodput_std": round(gs, 3),
                "rtt_median_mean": round(statistics.mean(rtt_m), 2),
                "rtt_p95_mean": round(statistics.mean(rtt_95), 2),
                "retrans_pct_mean": round(statistics.mean(retrans_pct), 3),
                "api_calls_mean": round(statistics.mean(api_cnts), 1),
                "api_wait_s_mean": round(statistics.mean(api_waits), 2),
                "beta_counts": {str(k): v for k, v in sorted(betas.items())},
            }

    # Exp 3: Bandwidth Change (20->5->20, 55KB) + fixed beta reference
    stats["exp3_capacity"] = {}
    for alg in ("reno", "cubic", "glm", "fixed4", "fixed5", "fixed6", "fixed7", "fixed8"):
        phase_gp = [[], [], []]
        phase_rtt = [[], [], []]
        qdrops, api_cnts = [], []
        for r in (1, 2, 3):
            rd = FINAL / f"exp3-cap-{alg}-{r:02d}"
            m = load_json(rd / "metrics.json")
            for idx in range(3):
                iv = m["intervals"][idx]
                phase_gp[idx].append(iv["total_goodput_bps"] / 1e6)
                phase_rtt[idx].append(iv["rtt_ms"]["median"])
            qdrops.append((m["queue_drop_rates"].get("0_disc") or 0) * 100)
            cnt, _ = count_api_calls(rd)
            api_cnts.append(cnt)
        stats["exp3_capacity"][alg] = {
            "phases": [
                {
                    "goodput_mean": round(mean_std(phase_gp[i])[0], 3),
                    "goodput_std": round(mean_std(phase_gp[i])[1], 3),
                    "rtt_median_mean": round(mean_std(phase_rtt[i])[0], 2),
                }
                for i in range(3)
            ],
            "queue_drop_pct_mean": round(statistics.mean(qdrops), 4),
            "api_calls_mean": round(statistics.mean(api_cnts), 1),
        }

    # Exp 4: Delay Shift (20ms -> 40ms)
    stats["exp4_delay_shift"] = {}
    for alg in ("reno", "cubic", "glm"):
        phase_gp = [[], []]
        phase_rtt = [[], []]
        api_cnts = []
        for r in (1, 2, 3):
            rd = FINAL / f"exp4-prop-{alg}-{r:02d}"
            m = load_json(rd / "metrics.json")
            for idx in range(2):
                iv = m["intervals"][idx]
                phase_gp[idx].append(iv["total_goodput_bps"] / 1e6)
                phase_rtt[idx].append(iv["rtt_ms"]["median"])
            cnt, _ = count_api_calls(rd)
            api_cnts.append(cnt)
        stats["exp4_delay_shift"][alg] = {
            "phases": [
                {
                    "goodput_mean": round(mean_std(phase_gp[i])[0], 3),
                    "goodput_std": round(mean_std(phase_gp[i])[1], 3),
                    "rtt_median_mean": round(mean_std(phase_rtt[i])[0], 2),
                }
                for i in range(2)
            ],
            "api_calls_mean": round(statistics.mean(api_cnts), 1),
        }

    # Exp 5: 3-Flow Fairness
    stats["exp5_fairness"] = {}
    for group in ("mixed-glm", "homo-reno", "homo-cubic"):
        flow_rates = [[], [], []]
        flow_shares = [[], [], []]
        jains, totals, rtts, api_cnts = [], [], [], []
        for r in (1, 2, 3):
            rd = FINAL / f"exp5-{group}-{r:02d}"
            m = load_json(rd / "metrics.json")
            iv = m["intervals"][0]
            totals.append(iv["total_goodput_bps"] / 1e6)
            jains.append(iv["jain"])
            rtts.append(iv["rtt_ms"]["median"])
            for i in range(3):
                flow_rates[i].append(iv["goodput_bps"][str(i)] / 1e6)
                flow_shares[i].append(iv["shares"][str(i)] * 100)
            cnt, _ = count_api_calls(rd)
            api_cnts.append(cnt)
        stats["exp5_fairness"][group] = {
            "total_goodput_mean": round(statistics.mean(totals), 3),
            "jain_mean": round(mean_std(jains)[0], 4),
            "jain_std": round(mean_std(jains)[1], 4),
            "rtt_median_mean": round(statistics.mean(rtts), 2),
            "flow_goodput_mean": [round(mean_std(flow_rates[i])[0], 3) for i in range(3)],
            "flow_share_mean": [round(mean_std(flow_shares[i])[0], 2) for i in range(3)],
            "flow_share_std": [round(mean_std(flow_shares[i])[1], 2) for i in range(3)],
            "api_calls_mean": round(statistics.mean(api_cnts), 1),
        }

    # GLM-4-Flash API latency across all 15 runs
    lats, run_calls = [], []
    for rd in sorted(FINAL.glob("*-glm-*")):
        if rd.is_dir():
            cnt, l_list = count_api_calls(rd)
            if cnt > 0:
                run_calls.append(cnt)
                lats.extend(l_list)
    if lats:
        q = np.quantile(lats, [0.5, 0.95])
        stats["glm_api"] = {
            "runs": len(run_calls),
            "total_calls": len(lats),
            "calls_per_run_mean": round(statistics.mean(run_calls), 1),
            "wait_s_per_run_mean": round(sum(lats) / len(run_calls), 2),
            "median_s": round(float(q[0]), 2),
            "p95_s": round(float(q[1]), 2),
            "mean_s": round(float(np.mean(lats)), 2),
        }

    (FINAL / "summary_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def plot_fig1_protocol(stats: dict) -> None:
    d = FINAL / "exp1-protocol-reno"
    df = pd.read_csv(d / "samples.csv")
    p = stats["exp1_protocol"]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.5, 6.6))

    sub1 = df[(df.time_s >= 0.95) & (df.time_s <= 15.5)]
    ax1.plot(sub1.time_s, sub1.cwnd_bytes / 1448, color=COLORS["reno"], lw=1.8, label="拥塞窗口 cwnd")
    ax1.plot(sub1.time_s, sub1.ssthresh_bytes / 1448, color=COLORS["cubic"], lw=1.5, ls="--", label="慢开始阈值 ssthresh")
    ax1.set_ylabel("窗口大小 (MSS)")
    ax1.set_title("TCP Reno 单流完整窗口演化过程 (1–15.5 s)")
    ax1.legend(loc="upper left")
    ax1.grid(alpha=0.25)

    evs = [json.loads(line) for line in (d / "events.jsonl").read_text().splitlines()]
    cw_t, cw_v, ss_v = [], [], []
    for e in evs:
        if e["type"] == "cwnd" and 1.0 <= e["time_s"] <= 2.05:
            cw_t.append(e["time_s"])
            cw_v.append(e["value"] / 1448)
            ss_v.append(e["ssthresh"] / 1448)
    ax2.step(cw_t, cw_v, where="post", color=COLORS["reno"], lw=2.0, label="cwnd (精确事件轨迹)")
    ax2.step(cw_t, ss_v, where="post", color=COLORS["cubic"], lw=1.6, ls="--", label="ssthresh")

    ss_exit = next(t for t, v in zip(cw_t, cw_v) if v >= 32)
    ax2.axvspan(1.0, ss_exit, color="#DCFCE7", alpha=0.75)
    ax2.axvspan(ss_exit, p["drop_s"], color="#DBEAFE", alpha=0.6)
    ax2.axvspan(p["drop_s"], p["recovery_exit_s"], color="#FEE2E2", alpha=0.75)
    ax2.axvspan(p["recovery_exit_s"], 2.05, color="#DBEAFE", alpha=0.45)

    ax2.axvline(p["drop_s"], color="#DC2626", ls="--", lw=1.2, label=f"第150号包丢弃 ({p['drop_s']:.3f} s)")
    ax2.axvline(p["retrans_s"], color="#16A34A", ls=":", lw=1.6, label=f"快重传触发 ({p['retrans_s']:.3f} s)")
    ax2.axvline(p["recovery_exit_s"], color="#4B5563", ls="-.", lw=1.2, label=f"退出快恢复 ({p['recovery_exit_s']:.3f} s)")

    ax2.text((1.0 + ss_exit) / 2, 40.8, "慢开始\n(指数增长)", ha="center", va="top", fontsize=9.2, color="#166534")
    ax2.text((ss_exit + p["drop_s"]) / 2, 40.8, "拥塞避免", ha="center", va="top", fontsize=9.2, color="#1E40AF")
    ax2.text((p["drop_s"] + p["recovery_exit_s"]) / 2, 40.8, "快重传/\n快恢复", ha="center", va="top", fontsize=8.8, color="#991B1B")
    ax2.text(1.77, 40.8, "拥塞避免 (线性增长)", ha="center", va="top", fontsize=9.2, color="#1E40AF")

    ax2.set_xlim(1.0, 2.05)
    ax2.set_ylim(0, 42.5)
    ax2.set_xlabel("仿真时间 (s)")
    ax2.set_ylabel("窗口大小 (MSS)")
    ax2.set_title("四阶段局部放大 (1.0–2.05 s)")
    ax2.legend(loc="lower right", fontsize=8.8, ncol=2)
    ax2.grid(alpha=0.25)

    fig.tight_layout()
    fig.savefig(FIGDIR / "fig1_protocol_phases.png", dpi=200)
    plt.close(fig)


def plot_fig2_reno_vs_cubic() -> None:
    fig, ax = plt.subplots(figsize=(9.5, 4.3))
    for alg in ("reno", "cubic"):
        df = pd.read_csv(FINAL / f"exp1-zoom-{alg}" / "samples.csv")
        sub = df[(df.time_s >= 3.0) & (df.time_s <= 25.0)]
        ax.plot(sub.time_s, sub.cwnd_bytes / 1448, color=COLORS[alg], lw=1.9, label=LABELS[alg])
    ax.axhline(76.0, color="#6B7280", ls=":", lw=1.2, label="链路带宽时延积 BDP (≈76 MSS)")
    ax.set_xlim(3.0, 25.0)
    ax.set_ylim(50, 165)
    ax.set_xlabel("仿真时间 (s)")
    ax.set_ylabel("拥塞窗口 cwnd (MSS)")
    ax.set_title("相同瓶颈条件下 Reno 与 CUBIC 稳态拥塞窗口曲线对比 (20 Mbit/s, RTT=44 ms)")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig2_reno_vs_cubic_zoom.png", dpi=200)
    plt.close(fig)


def plot_fig3_random_loss_metrics(stats: dict) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.6, 4.5))
    algs = ["reno", "cubic", "glm"]
    x = np.arange(2)
    w = 0.24

    # Left: Goodput
    for idx, alg in enumerate(algs):
        means = [stats["exp2_random_loss"][tag][alg]["goodput_mean"] for tag in ("loss5", "loss10")]
        stds = [stats["exp2_random_loss"][tag][alg]["goodput_std"] for tag in ("loss5", "loss10")]
        bars = ax1.bar(
            x + (idx - 1.0) * w, means, w, yerr=stds, capsize=3,
            color=COLORS[alg], alpha=0.92, label=LABELS[alg],
        )
        for b, m, s in zip(bars, means, stds):
            ax1.text(b.get_x() + b.get_width() / 2, m + s + 0.16, f"{m:.2f}", ha="center", va="bottom", fontsize=9.0)
    ax1.set_xticks(x)
    ax1.set_xticklabels(["0.5% 随机丢包", "1.0% 随机丢包"])
    ax1.set_ylim(0, 9.6)
    ax1.set_ylabel("稳态有效吞吐量 (Mbit/s)")
    ax1.set_title("(a) 随机丢包下的平均有效吞吐量 (3 次重复)")
    ax1.legend(loc="upper right", fontsize=8.8)
    ax1.grid(axis="y", alpha=0.25)

    # Right: RTT P95 (bars) + RTT median (markers) + 44ms base RTT line
    for idx, alg in enumerate(algs):
        p95s = [stats["exp2_random_loss"][tag][alg]["rtt_p95_mean"] for tag in ("loss5", "loss10")]
        meds = [stats["exp2_random_loss"][tag][alg]["rtt_median_mean"] for tag in ("loss5", "loss10")]
        pos = x + (idx - 1.0) * w
        bars = ax2.bar(pos, p95s, w, color=COLORS[alg], alpha=0.85, label=f"{SHORT[alg]} P95")
        ax2.scatter(pos, meds, color="#111827", s=34, zorder=5, marker="D",
                    label="中位 RTT (均约 46 ms)" if idx == 0 else None)
        for b, v in zip(bars, p95s):
            ax2.text(b.get_x() + b.get_width() / 2, v + 1.2, f"{v:.1f}", ha="center", va="bottom", fontsize=8.8)
    ax2.axhline(44.0, color="#6B7280", ls="--", lw=1.2, label="无排队基础 RTT (44 ms)")
    ax2.set_xticks(x)
    ax2.set_xticklabels(["0.5% 随机丢包", "1.0% 随机丢包"])
    ax2.set_ylim(0, 95)
    ax2.set_ylabel("端到端往返时延 RTT (ms)")
    ax2.set_title("(b) 随机丢包下的中位 RTT 与 P95 尾时延对比")
    ax2.legend(loc="upper left", ncol=2, fontsize=8.3)
    ax2.grid(axis="y", alpha=0.25)

    fig.tight_layout()
    fig.savefig(FIGDIR / "fig3_random_loss_metrics.png", dpi=200)
    plt.close(fig)


def plot_fig4_random_loss_cwnd_beta() -> None:
    fig, axes = plt.subplots(3, 1, figsize=(10.2, 7.8), sharex=True, gridspec_kw={"height_ratios": [1.25, 1.25, 0.85]})

    for row_idx, (tag, title, ymax) in enumerate((
        ("loss5", "(a) 0.5% 随机丢包下的拥塞窗口演化 (1–50 s)", 62),
        ("loss10", "(b) 1.0% 随机丢包下的拥塞窗口演化 (1–50 s)", 44),
    )):
        ax = axes[row_idx]
        for alg in ("reno", "cubic", "glm"):
            df = pd.read_csv(FINAL / f"exp2-{tag}-{alg}-01" / "samples.csv")
            sub = df[(df.time_s >= 1) & (df.time_s <= 50)]
            eval_sub = df[(df.time_s >= 10) & (df.time_s <= 50)]
            mean_v = eval_sub.cwnd_bytes.mean() / 1448
            ax.plot(
                sub.time_s, sub.cwnd_bytes / 1448,
                color=COLORS[alg], lw=1.5, alpha=0.9,
                label=f"{SHORT[alg]} (稳态均值 {mean_v:.1f} MSS)",
            )
        ax.axvline(10, color="#6B7280", ls="--", lw=1.0, alpha=0.7)
        ax.set_ylim(0, ymax)
        ax.text(2.3, ymax * 0.92, "↑ 慢开始启动峰值", fontsize=8.0, color="#4B5563", va="top",
                bbox=dict(facecolor="white", alpha=0.82, edgecolor="none", pad=1.0))
        ax.set_ylabel("cwnd (MSS)")
        ax.set_title(title)
        ax.legend(loc="upper right", ncol=3, fontsize=8.6)
        ax.grid(alpha=0.25)

    # Bottom: GLM-4-Flash dynamic beta from flow start (1-50 s)
    df_g = pd.read_csv(FINAL / "exp2-loss5-glm-01" / "samples.csv")
    sub_g = df_g[(df_g.time_s >= 1) & (df_g.time_s <= 50)]
    axes[2].step(sub_g.time_s, sub_g.beta, where="post", color=COLORS["glm"], lw=2.0, label="GLM-4-Flash 动态 β")
    axes[2].axhline(0.5, color=COLORS["reno"], ls=":", lw=1.3, label="Reno 固定 0.5")
    axes[2].axhline(0.7, color=COLORS["cubic"], ls=":", lw=1.3, label="CUBIC 固定 0.7")
    axes[2].axvline(10, color="#6B7280", ls="--", lw=1.0, alpha=0.7)
    axes[2].set_xlim(1, 50)
    axes[2].set_ylim(0.34, 0.92)
    axes[2].set_yticks([0.4, 0.5, 0.6, 0.7, 0.8])
    axes[2].set_ylabel("保留比例 β")
    axes[2].set_xlabel("仿真时间 (s)  （虚线 t=10 s 起为稳态评估区间）")
    axes[2].set_title("(c) GLM-4-Flash 在随机丢包下的保留比例 β 动态变化 (1–50 s)")
    axes[2].legend(loc="lower left", ncol=3, fontsize=8.6)
    axes[2].grid(alpha=0.25)

    fig.tight_layout()
    fig.savefig(FIGDIR / "fig4_random_loss_cwnd_beta.png", dpi=200)
    plt.close(fig)


def _load_exp3_stats() -> dict:
    out = {}
    for name in ("fixed4", "reno", "fixed6", "fixed7", "fixed8", "cubic", "glm"):
        runs = sorted(FINAL.glob(f"exp3-cap-{name}-*"))
        phases = []
        for idx in range(3):
            gps, rtts = [], []
            for r in runs:
                m = json.loads((r / "metrics.json").read_text(encoding="utf-8"))
                iv = m["intervals"][idx]
                gps.append(iv["total_goodput_bps"] / 1e6)
                rtts.append(iv["rtt_ms"]["median"])
            phases.append({"goodput_mean": float(np.mean(gps)), "rtt_median_mean": float(np.mean(rtts))})
        qdrops = [
            list(json.loads((r / "metrics.json").read_text(encoding="utf-8"))["queue_drop_rates"].values())[0] * 100
            for r in runs
        ]
        out[name] = {"phases": phases, "queue_drop_pct_mean": float(np.mean(qdrops))}
    return out


def plot_fig5_capacity_change() -> None:
    """3.3.1: 三档纯带宽下固定 β (0.4~0.8) 标定与 GLM-4-Flash 关键指标对比。"""
    cap = _load_exp3_stats()
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.3))

    keys = ["fixed4", "reno", "fixed6", "fixed7", "fixed8", "glm"]
    labels = ["固定\n0.4", "固定\n0.5", "固定\n0.6", "固定\n0.7", "固定\n0.8", "GLM-\n4-Flash"]
    bx = np.arange(len(keys))

    # (a) Stage 1: 14 Mbit/s median RTT
    s1_rtts = [cap[k]["phases"][0]["rtt_median_mean"] for k in keys]
    c1 = ["#CBD5E1", "#2563EB", "#9CA3AF", "#9CA3AF", "#9CA3AF", COLORS["glm"]]
    b1 = axes[0].bar(bx, s1_rtts, width=0.56, color=c1, alpha=0.92)
    b1[0].set_hatch("//")
    for idx, (b, v) in enumerate(zip(b1, s1_rtts)):
        axes[0].text(b.get_x() + b.get_width() / 2, v + 0.6, f"{v:.0f}", ha="center", va="bottom",
                     fontsize=8.8, fontweight="bold" if idx in (1, 5) else "normal",
                     color=COLORS["glm"] if idx == 5 else ("#2563EB" if idx == 1 else "#374151"))
    axes[0].axhline(72.0, color="#2563EB", ls="--", lw=1.1, alpha=0.65)
    axes[0].set_xticks(bx)
    axes[0].set_xticklabels(labels, fontsize=8.5)
    axes[0].set_ylim(60, 86.5)
    axes[0].set_ylabel("中位 RTT (ms)")
    axes[0].set_title("(a) 阶段一（14 Mbit/s）中位 RTT 对比", fontsize=10.0)
    axes[0].grid(axis="y", alpha=0.25)

    # (b) Stage 2: 40 Mbit/s throughput
    s2_gps = [cap[k]["phases"][1]["goodput_mean"] for k in keys]
    c2 = ["#9CA3AF", "#9CA3AF", "#9CA3AF", "#2563EB", "#9CA3AF", COLORS["glm"]]
    b2 = axes[1].bar(bx, s2_gps, width=0.56, color=c2, alpha=0.92)
    for idx, (b, v) in enumerate(zip(b2, s2_gps)):
        axes[1].text(b.get_x() + b.get_width() / 2, v + 0.14, f"{v:.2f}", ha="center", va="bottom",
                     fontsize=8.8, fontweight="bold" if idx in (3, 5) else "normal",
                     color=COLORS["glm"] if idx == 5 else ("#2563EB" if idx == 3 else "#374151"))
    axes[1].axhline(38.38, color="#2563EB", ls="--", lw=1.1, alpha=0.65)
    axes[1].set_xticks(bx)
    axes[1].set_xticklabels(labels, fontsize=8.5)
    axes[1].set_ylim(31.5, 40.0)
    axes[1].set_ylabel("稳态有效吞吐量 (Mbit/s)")
    axes[1].set_title("(b) 阶段二（40 Mbit/s）有效吞吐量对比", fontsize=10.0)
    axes[1].grid(axis="y", alpha=0.25)

    # (c) Stage 3: 3 Mbit/s median RTT
    s3_rtts = [cap[k]["phases"][2]["rtt_median_mean"] for k in keys]
    c3 = ["#2563EB", "#9CA3AF", "#9CA3AF", "#9CA3AF", "#9CA3AF", COLORS["glm"]]
    b3 = axes[2].bar(bx, s3_rtts, width=0.56, color=c3, alpha=0.92)
    for idx, (b, v) in enumerate(zip(b3, s3_rtts)):
        axes[2].text(b.get_x() + b.get_width() / 2, v + 1.2, f"{v:.0f}", ha="center", va="bottom",
                     fontsize=8.8, fontweight="bold" if idx in (0, 5) else "normal",
                     color=COLORS["glm"] if idx == 5 else ("#2563EB" if idx == 0 else "#374151"))
    axes[2].axhline(200.0, color="#2563EB", ls="--", lw=1.1, alpha=0.65)
    axes[2].set_xticks(bx)
    axes[2].set_xticklabels(labels, fontsize=8.5)
    axes[2].set_ylim(180, 244)
    axes[2].set_ylabel("中位 RTT (ms)")
    axes[2].set_title("(c) 阶段三（3 Mbit/s）中位 RTT 对比", fontsize=10.0)
    axes[2].grid(axis="y", alpha=0.25)

    fig.tight_layout()
    fig.savefig(FIGDIR / "fig5_capacity_change.png", dpi=200)
    plt.close(fig)


def plot_fig6_fixed_beta_tradeoff(stats: dict | None = None) -> None:
    """3.3.2: Reno、CUBIC 与 GLM-4-Flash 在 14 -> 40 -> 3 Mbit/s 下的窗口、RTT 与 β 曲线对比。"""
    fig, axes = plt.subplots(3, 1, figsize=(10.6, 8.0), sharex=True, gridspec_kw={"height_ratios": [1.3, 1.15, 0.85]})
    for alg in ("reno", "cubic", "glm"):
        df = pd.read_csv(FINAL / f"exp3-cap-{alg}-01" / "samples.csv")
        sub = df[(df.time_s >= 3) & (df.time_s <= 82)]
        axes[0].plot(sub.time_s, sub.cwnd_bytes / 1448, color=COLORS[alg], lw=1.5, alpha=0.9, label=SHORT[alg])
        axes[1].plot(sub.time_s, sub.srtt_ms, color=COLORS[alg], lw=1.5, alpha=0.9, label=SHORT[alg])
        if alg == "glm":
            axes[2].step(sub.time_s, sub.beta, where="post", color=COLORS[alg], lw=2.1, label="GLM-4-Flash 动态 β")

    axes[2].axhline(0.5, color=COLORS["reno"], ls=":", lw=1.3, label="Reno 固定 0.5")
    axes[2].axhline(0.7, color=COLORS["cubic"], ls=":", lw=1.3, label="CUBIC 固定 0.7")

    for ax in axes:
        ax.axvline(28, color="#374151", ls="--", lw=1.1)
        ax.axvline(55, color="#374151", ls="--", lw=1.1)
        ax.grid(alpha=0.25)

    axes[0].text(15.5, 206, "阶段一：14 Mbit/s (常规 1×BDP)", ha="center", fontsize=9.4, fontweight="bold")
    axes[0].text(41.5, 206, "阶段二：40 Mbit/s (扩容浅缓冲)", ha="center", fontsize=9.4, fontweight="bold", color="#1D4ED8")
    axes[0].text(68.5, 206, "阶段三：3 Mbit/s (深缓冲拥塞)", ha="center", fontsize=9.4, fontweight="bold", color="#B91C1C")
    axes[0].set_ylim(10, 224)
    axes[0].set_ylabel("cwnd (MSS)")
    axes[0].legend(loc="lower left", ncol=3, fontsize=9.0)
    axes[0].set_title("带宽三档变化 (14 → 40 → 3 Mbit/s, 队列 75 KB) 下三种算法的窗口、时延与 β 演化")

    axes[1].set_ylim(38, 265)
    axes[1].set_ylabel("平滑 RTT (ms)")
    axes[1].legend(loc="upper left", ncol=3, fontsize=9.0)

    axes[2].set_xlim(3, 82)
    axes[2].set_ylim(0.34, 0.86)
    axes[2].set_yticks([0.4, 0.5, 0.6, 0.7, 0.8])
    axes[2].set_ylabel("窗口保留比例 β")
    axes[2].set_xlabel("仿真时间 (s)")
    axes[2].legend(loc="upper left", ncol=3, fontsize=8.8)

    fig.tight_layout()
    fig.savefig(FIGDIR / "fig6_fixed_beta_tradeoff.png", dpi=200)
    plt.close(fig)


def plot_fig7_delay_shift(stats: dict | None = None) -> None:
    fig = plt.figure(figsize=(12.2, 5.0))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.05, 1.38], height_ratios=[1.3, 0.9], hspace=0.14, wspace=0.25)
    ax_bar = fig.add_subplot(gs[:, 0])
    ax_cw = fig.add_subplot(gs[0, 1])
    ax_beta = fig.add_subplot(gs[1, 1], sharex=ax_cw)

    # Left: post-shift goodput bars (30-60 s) across 4 schemes
    keys = ["fixed4", "reno", "glm", "cubic"]
    labels = ["固定 0.4", "Reno\n(0.5)", "GLM-4-Flash", "CUBIC\n(0.7)"]
    cols = ["#9CA3AF", COLORS["reno"], COLORS["glm"], COLORS["cubic"]]
    means, stds = [], []
    for k in keys:
        vals = [
            json.loads((r / "metrics.json").read_text(encoding="utf-8"))["intervals"][1]["total_goodput_bps"] / 1e6
            for r in sorted(FINAL.glob(f"exp4-prop-{k}-*"))
        ]
        means.append(float(np.mean(vals)))
        stds.append(float(np.std(vals, ddof=1)))

    bx = np.arange(len(keys))
    bars = ax_bar.bar(bx, means, width=0.54, yerr=stds, capsize=3, color=cols, alpha=0.92)
    for b, m, s in zip(bars, means, stds):
        ax_bar.text(b.get_x() + b.get_width() / 2, m + s + 0.12, f"{m:.2f}", ha="center", va="bottom", fontsize=9.0)
    ax_bar.set_xticks(bx)
    ax_bar.set_xticklabels(labels, fontsize=8.8)
    ax_bar.set_ylim(15.0, 20.0)
    ax_bar.set_ylabel("跳变后稳态吞吐量 (Mbit/s, 30–60 s)")
    ax_bar.set_title("(a) 传播时延 20→40 ms 后有效吞吐量对比", fontsize=10.2)
    ax_bar.grid(axis="y", alpha=0.25)

    # Right top & bottom: cwnd and beta curves (10-60 s, representative run 01)
    for alg in ("reno", "cubic", "glm"):
        df = pd.read_csv(FINAL / f"exp4-prop-{alg}-01" / "samples.csv")
        sub = df[(df.time_s >= 10) & (df.time_s <= 60)]
        ax_cw.plot(sub.time_s, sub.cwnd_bytes / 1448, color=COLORS[alg], lw=1.5, alpha=0.9, label=SHORT[alg])
        if alg == "glm":
            ax_beta.step(sub.time_s, sub.beta, where="post", color=COLORS[alg], lw=2.0, label="GLM-4-Flash 动态 β")

    ax_beta.axhline(0.5, color=COLORS["reno"], ls=":", lw=1.3, label="Reno 固定 0.5")
    ax_beta.axhline(0.7, color=COLORS["cubic"], ls=":", lw=1.3, label="CUBIC 固定 0.7")

    for ax in (ax_cw, ax_beta):
        ax.axvline(25, color="#DC2626", ls="--", lw=1.2)
        ax.grid(alpha=0.25)

    ax_cw.text(
        25.8, 192, "t=25 s: 单向传播时延 20 ms → 40 ms", fontsize=8.8, color="#B91C1C",
        va="top", bbox=dict(facecolor="white", alpha=0.88, edgecolor="none", pad=1.5),
    )
    ax_cw.set_ylim(55, 200)
    ax_cw.set_ylabel("cwnd (MSS)")
    ax_cw.set_title("(b) 传播时延增加前后的窗口与保留比例 β 演化", fontsize=10.2)
    ax_cw.legend(loc="lower right", ncol=3, fontsize=8.6)
    plt.setp(ax_cw.get_xticklabels(), visible=False)

    ax_beta.set_xlim(10, 60)
    ax_beta.set_ylim(0.32, 0.90)
    ax_beta.set_yticks([0.4, 0.5, 0.6, 0.7, 0.8])
    ax_beta.set_ylabel("保留比例 β")
    ax_beta.set_xlabel("仿真时间 (s)")
    ax_beta.legend(loc="lower left", ncol=3, fontsize=8.3)

    fig.subplots_adjust(left=0.06, right=0.98, top=0.91, bottom=0.12)
    fig.savefig(FIGDIR / "fig7_delay_shift.png", dpi=200)
    plt.close(fig)


def plot_fig8_fairness(stats: dict | None = None) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.8, 4.7), gridspec_kw={"width_ratios": [1.18, 1.0]})

    groups = [
        ("exp5-homo-reno", "3×Reno", COLORS["reno"]),
        ("exp5-homo-cubic", "3×CUBIC", COLORS["cubic"]),
        ("exp5-homo-glm", "3×GLM", COLORS["glm"]),
        ("exp5-reno-cubic", "2×Reno\n+CUBIC", COLORS["cubic"]),
        ("exp5-reno-glm", "2×Reno\n+GLM", COLORS["glm"]),
        ("exp5-mixed-glm", "Reno+CUBIC\n+GLM", "#4B5563"),
    ]
    j_means, j_stds, rtt_means = [], [], []
    all_shares = {}
    for prefix, _, _ in groups:
        runs = sorted(FINAL.glob(f"{prefix}-*"))
        js, rs = [], []
        sh = [[], [], []]
        for r in runs:
            iv = json.loads((r / "metrics.json").read_text(encoding="utf-8"))["intervals"][0]
            js.append(iv["jain"])
            rs.append(iv["rtt_ms"]["median"])
            for i in range(3):
                sh[i].append(iv["shares"][str(i)] * 100)
        j_means.append(float(np.mean(js)))
        j_stds.append(float(np.std(js, ddof=1)))
        rtt_means.append(float(np.mean(rs)))
        all_shares[prefix] = [float(np.mean(s)) for s in sh]

    # Left: Jain fairness (bars) + median RTT (markers on twinx) for all 6 groups
    x = np.arange(len(groups))
    bars = ax1.bar(x, j_means, width=0.52, yerr=j_stds, capsize=3,
                   color=[g[2] for g in groups], alpha=0.88)
    ax1.axvline(2.5, color="#6B7280", ls="--", lw=1.1)
    for b, jm, js in zip(bars, j_means, j_stds):
        ax1.text(b.get_x() + b.get_width() / 2, jm + js + 0.0016, f"{jm:.4f}",
                 ha="center", va="bottom", fontsize=8.0, fontweight="bold")
    ax1.text(1.0, 1.011, "同构三流竞争", ha="center", va="top", fontsize=8.8, color="#374151")
    ax1.text(4.0, 1.011, "异构三流竞争", ha="center", va="top", fontsize=8.8, color="#374151")
    ax1.set_xticks(x)
    ax1.set_xticklabels([g[1] for g in groups], fontsize=8.3)
    ax1.set_ylim(0.955, 1.015)
    ax1.set_ylabel("Jain 公平性指数")
    ax1.set_title("(a) 六组三流竞争的 Jain 公平性指数与中位 RTT", fontsize=10.0)
    ax1.grid(axis="y", alpha=0.25)

    ax1_r = ax1.twinx()
    ax1_r.spines["right"].set_visible(True)
    ax1_r.plot(x, rtt_means, "D-", color="#DC2626", lw=1.6, ms=5.2, label="共享队列中位 RTT (ms)")
    for xi, rv in zip(x, rtt_means):
        y_off = -1.6 if xi != 3 else 1.4
        va = "top" if xi != 3 else "bottom"
        ax1_r.text(
            xi, rv + y_off, f"{rv:.1f}", ha="center", va=va, fontsize=8.0, fontweight="bold",
            color="#B91C1C", bbox=dict(facecolor="white", alpha=0.90, edgecolor="none", pad=1.0),
        )
    ax1_r.set_ylabel("共享队列中位 RTT (ms)", color="#DC2626")
    ax1_r.tick_params(axis="y", colors="#DC2626")
    ax1_r.set_ylim(68, 92)
    ax1_r.legend(loc="lower left", fontsize=8.2)

    # Right: Per-flow shares in the 3 heterogeneous groups
    het_specs = [
        ("exp5-reno-cubic", "2×Reno + CUBIC", [COLORS["reno"], COLORS["reno"], COLORS["cubic"]]),
        ("exp5-reno-glm", "2×Reno + GLM", [COLORS["reno"], COLORS["reno"], COLORS["glm"]]),
        ("exp5-mixed-glm", "Reno + CUBIC + GLM", [COLORS["reno"], COLORS["cubic"], COLORS["glm"]]),
    ]
    gx = np.arange(len(het_specs))
    bw = 0.24
    for g_idx, (prefix, _, fcols) in enumerate(het_specs):
        sh = all_shares[prefix]
        for f_idx in range(3):
            pos = gx[g_idx] + (f_idx - 1) * bw
            ax2.bar(pos, sh[f_idx], width=bw * 0.92, color=fcols[f_idx], alpha=0.9)
            ax2.text(
                pos, sh[f_idx] + 0.9, f"{sh[f_idx]:.1f}%", ha="center", va="bottom", fontsize=7.9,
                bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=0.6),
            )

    # Custom legend for algorithm colors
    from matplotlib.patches import Patch
    ax2.axhline(33.33, color="#6B7280", ls="--", lw=1.2)
    legend_handles = [
        Patch(facecolor=COLORS["reno"], label="Reno"),
        Patch(facecolor=COLORS["cubic"], label="CUBIC"),
        Patch(facecolor=COLORS["glm"], label="GLM-4-Flash"),
        plt.Line2D([0], [0], color="#6B7280", ls="--", lw=1.2, label="理想均分 (33.3%)"),
    ]
    ax2.set_xticks(gx)
    ax2.set_xticklabels([s[1] for s in het_specs], fontsize=8.8)
    ax2.set_ylim(0, 50)
    ax2.set_ylabel("单流稳态带宽占比 (%)")
    ax2.set_title("(b) 异构三流共存时的各流稳态带宽分配", fontsize=10.0)
    ax2.legend(handles=legend_handles, loc="upper right", ncol=2, fontsize=8.2)
    ax2.grid(axis="y", alpha=0.25)

    fig.tight_layout()
    fig.savefig(FIGDIR / "fig8_fairness.png", dpi=200)
    plt.close(fig)


def main() -> None:
    stats = collect_stats()
    plot_fig1_protocol(stats)
    plot_fig2_reno_vs_cubic()
    plot_fig3_random_loss_metrics(stats)
    plot_fig4_random_loss_cwnd_beta()
    plot_fig5_capacity_change()
    plot_fig6_fixed_beta_tradeoff(stats)
    plot_fig7_delay_shift(stats)
    plot_fig8_fairness(stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
