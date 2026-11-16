import asyncio
import json

import pytest

from tcp_lab.analysis import analyze
from tcp_lab.config import Flow, Scenario
from tcp_lab.report import report
from tcp_lab.runner import run_scenario


@pytest.mark.integration
def test_independent_runs_and_paired_report(run_dir):
    for algorithm in ("reno", "cubic"):
        for run in (1, 2):
            config = Scenario(name=f"stable-{algorithm}", run=run, end_s=5,
                flows=[Flow(algorithm=algorithm, stop_s=3)], evaluation=[(2, 4)])
            output = asyncio.run(run_scenario(config, run_dir / f"{algorithm}-{run}"))
            analyze(output)
    result = json.loads(report(run_dir).read_text())
    assert len(result["statistics"]) == 2
    assert all(row["goodput_mbps"]["n"] == 2 for row in result["statistics"])
    assert all(row["goodput_mbps"]["lower95"] <= row["goodput_mbps"]["mean"]
               <= row["goodput_mbps"]["upper95"] for row in result["statistics"])
    assert len(result["paired"]) == 1
    assert result["paired"][0]["goodput_mbps"]["n"] == 2
    assert (run_dir / "comparison.pdf").stat().st_size > 1000
