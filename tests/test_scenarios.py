import asyncio
import json

import pytest

from tcp_lab.analysis import analyze, events
from tcp_lab.config import Change, Flow, Scenario
from tcp_lab.matrix import cases, generate
from tcp_lab.runner import run_scenario


@pytest.mark.integration
def test_error_model_labels_and_dynamic_rtt(run_dir):
    config = Scenario(name="labels", end_s=6, error_rate=0.01, start_jitter_s=0,
        flows=[Flow(stop_s=4)], changes=[Change(time_s=3, delay_ms=40)], evaluation=[(2, 5)])
    output = asyncio.run(run_scenario(config, run_dir / "labels"))
    data = list(events(output, {"error_drop", "observation", "network_change"}))
    assert sum(e["type"] == "error_drop" for e in data) > 0
    observations = [e for e in data if e["type"] == "observation"]
    assert observations[-1]["history"][-1]["srtt_ms"] > 80


@pytest.mark.integration
def test_reference_capacity(run_dir):
    config = next(case for case in cases() if case.name == "reference-20")
    output = asyncio.run(run_scenario(config, run_dir / "reference"))
    network = json.loads((output / "network.json").read_text())
    assert network["error_drops"] == 0
    assert all(q["dropped"] == 0 for q in network["queues"])
    metrics = analyze(output)
    assert 18e6 < metrics["intervals"][0]["total_goodput_bps"] < 20e6


@pytest.mark.integration
def test_late_arrival_and_reverse_flow(run_dir):
    config = Scenario(name="arrival", end_s=8, start_jitter_s=0,
        flows=[Flow(stop_s=5), Flow(algorithm="cubic", reverse=True, start_s=3, stop_s=5)],
        evaluation=[(2, 6)])
    output = asyncio.run(run_scenario(config, run_dir / "arrival"))
    metrics = analyze(output)["intervals"][0]
    assert any(segment["active"] == [0] for segment in metrics["fairness_segments"])
    assert any(segment["active"] == [0, 1] for segment in metrics["fairness_segments"])
    assert all(value > 0 for value in metrics["utilization"])


def test_saved_full_matrix(run_dir):
    manifest = generate(run_dir / "matrix", 20)
    data = json.loads(manifest.read_text())
    assert len(data["cases"]) == len(cases()) * 20
    assert {row["run"] for row in data["cases"]} == set(range(1, 21))
    assert all((manifest.parent / row["config"]).is_file() for row in data["cases"])
