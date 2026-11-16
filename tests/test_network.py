import asyncio
import json
from pathlib import Path

import pytest

from tcp_lab.analysis import analyze, events
from tcp_lab.config import Change, Flow, Scenario, load_scenario
from tcp_lab.matrix import cases
from tcp_lab.runner import run_scenario
from tcp_lab.runtime import ROOT


@pytest.mark.integration
def test_real_transfer(run_dir):
    config = load_scenario(ROOT / "configs/smoke.json")
    output = asyncio.run(run_scenario(config, run_dir / "transfer"))
    network = json.loads((output / "network.json").read_text())
    flow = network["flows"][0]
    assert flow["received_bytes"] > 10_000_000
    assert flow["received_bytes"] == flow["sent_bytes"] == flow["acked_bytes"]
    assert flow["tx_bytes"] - flow["retrans_bytes"] == flow["sent_bytes"]
    assert flow["pending_bytes"] == 0
    metrics = analyze(output)
    assert metrics["intervals"][0]["total_goodput_bps"] > 1_000_000
    assert all(0 <= u <= 1.000001 for row in metrics["intervals"] for u in row["utilization"])
    assert (output / "curves.pdf").stat().st_size > 1000


@pytest.mark.integration
def test_classic_recovery(run_dir):
    config = load_scenario(ROOT / "configs/protocol.json")
    output = asyncio.run(run_scenario(config, run_dir / "protocol"))
    data = list(events(output, {"cwnd", "congestion", "error_drop", "retransmission", "tcp_ack"}))
    drops = [e for e in data if e["type"] == "error_drop"]
    assert len(drops) == 1 and drops[0]["check_index"] == 150
    states = [e for e in data if e["type"] == "congestion"]
    recovery = next(e for e in states if e["name"] == "CA_RECOVERY")
    assert any(e["name"] == "CA_OPEN" and e["time_s"] > recovery["time_s"] for e in states)
    assert not any(e["name"] == "CA_LOSS" for e in states)
    retransmit = next(e for e in data if e["type"] == "retransmission")
    assert 0 < retransmit["time_s"] - drops[0]["time_s"] < 1
    acknowledgments = [e for e in data if e["type"] == "tcp_ack"
                       and e["time_s"] <= recovery["time_s"]]
    assert sum(e["ack"] == acknowledgments[-1]["ack"] for e in acknowledgments) >= 4
    windows = [e for e in data if e["type"] == "cwnd" and e["time_s"] < drops[0]["time_s"]]
    assert any(e["value"] >= 32 * 1448 for e in windows)
    slow_start = [e for e in windows if 1448 <= e["old"] < 32 * 1448]
    assert len(slow_start) >= 20
    assert all(e["value"] == e["old"] + 1448 for e in slow_start)
    assert any(e["value"] == e["old"] + 1448 and e["old"] >= 32 * 1448 for e in windows)
    assert list(output.glob("*.pcap"))


@pytest.mark.integration
def test_timeout_and_network_changes(run_dir):
    config = Scenario(name="timeout", end_s=12, start_jitter_s=0,
        flows=[Flow(stop_s=5)], outage_start_s=2, outage_end_s=4,
        changes=[Change(time_s=6, rate_mbps=5), Change(time_s=8, delay_ms=40)],
        evaluation=[(1, 5), (5, 12)])
    output = asyncio.run(run_scenario(config, run_dir / "timeout"))
    data = list(events(output, {"congestion", "cwnd", "network_change", "receive"}))
    losses = [e for e in data if e["type"] == "congestion" and e["name"] == "CA_LOSS"]
    assert losses
    assert any(e["type"] == "cwnd" and e["value"] == 1448
               and e["time_s"] >= losses[0]["time_s"] for e in data)
    assert len([e for e in data if e["type"] == "network_change"]) == 2
    assert any(e["type"] == "receive" and e["time_s"] > 4 for e in data)


@pytest.mark.integration
@pytest.mark.parametrize("beta", [0.4, 0.5, 0.6, 0.7, 0.8])
def test_fixed_threshold_from_real_loss(run_dir, beta):
    config = Scenario(name="fixed", end_s=5, start_jitter_s=0,
        flows=[Flow(algorithm="fixed", beta=beta, stop_s=3)], evaluation=[(2, 4)])
    output = asyncio.run(run_scenario(config, run_dir / "fixed"))
    thresholds = list(events(output, {"threshold_compute"}))
    assert thresholds
    for row in thresholds:
        assert row["ssthresh_bytes"] == max(2, int(beta * row["cwnd_bytes"] / 1448)) * 1448


@pytest.mark.integration
def test_cubic_competition_and_reproducibility(run_dir):
    config = Scenario(name="competition", end_s=7,
        flows=[Flow(algorithm="cubic", stop_s=5), Flow(algorithm="reno", stop_s=5)],
        evaluation=[(2, 5)])
    first = asyncio.run(run_scenario(config, run_dir / "first"))
    second = asyncio.run(run_scenario(config, run_dir / "second"))
    assert (first / "network.json").read_bytes() == (second / "network.json").read_bytes()
    assert (first / "samples.csv").read_bytes() == (second / "samples.csv").read_bytes()
    metrics = analyze(first)["intervals"][0]
    assert len(metrics["goodput_bps"]) == 2
    assert all(v > 0 for v in metrics["goodput_bps"].values())
    assert 0.5 <= metrics["jain"] <= 1


def test_entire_matrix_is_valid():
    matrix = cases()
    assert len({case.name for case in matrix}) == len(matrix)
    for case in matrix:
        assert Scenario.model_validate(case.model_dump()) == case
    assert {case.ablation for case in matrix} == {"none", "feedback", "retransmission", "rtt_history"}


@pytest.mark.api
def test_real_glm_and_exact_replay(run_dir):
    import os
    key_file = Path(os.environ["ZHIPU_KEY_FILE"]) if "ZHIPU_KEY_FILE" in os.environ else None
    config = load_scenario(ROOT / "configs/glm-check.json")
    live = asyncio.run(run_scenario(config, run_dir / "live", key_file=key_file))
    replay = asyncio.run(run_scenario(config, run_dir / "replay", replay=live))
    assert (live / "samples.csv").read_bytes() == (replay / "samples.csv").read_bytes()
    assert (live / "events.jsonl").read_bytes() == (replay / "events.jsonl").read_bytes()
    assert json.loads((live / "status.json").read_text())["decisions"] > 0
    applied = [e for e in events(live, {"threshold_compute"}) if e["decision_id"] != "initial"]
    assert applied
    assert any((live / "api").glob("*/response.txt"))


@pytest.mark.api
def test_real_mixed_glm_competition(run_dir):
    import os
    key_file = Path(os.environ["ZHIPU_KEY_FILE"]) if "ZHIPU_KEY_FILE" in os.environ else None
    config = load_scenario(ROOT / "configs/competition-check.json")
    output = asyncio.run(run_scenario(config, run_dir / "competition", key_file=key_file))
    metrics = analyze(output)
    assert all(flow["received_bytes"] > 0 for flow in metrics["flows"])
    assert all(1 / 3 <= interval["jain"] <= 1 for interval in metrics["intervals"])
    assert metrics["model_activations"] > 0
    actions = list(events(output, {"action"}))
    assert all(action["flow"] == 2 for action in actions)
