import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from tcp_lab.analysis import events
from tcp_lab.config import Flow, Scenario
from tcp_lab.runner import run_scenario
from tcp_lab.runtime import ROOT


@pytest.mark.api
@pytest.mark.parametrize("delay", [0.1, 0.5, 1.0])
def test_real_delayed_decisions(run_dir, delay):
    key_file = Path(os.environ["ZHIPU_KEY_FILE"]) if "ZHIPU_KEY_FILE" in os.environ else None
    config = Scenario(name="delay", end_s=5, decision_delay_s=delay,
        error_rate=0.005, start_jitter_s=0, flows=[Flow(algorithm="glm", stop_s=3)],
        evaluation=[(2, 4)])
    output = asyncio.run(run_scenario(config, run_dir / "delayed", key_file=key_file))
    records = [json.loads(line) for line in (output / "decisions.jsonl").read_text().splitlines()]
    observations = {r["observation"]["decision_id"]: r["observation"] for r in records}
    actions = list(events(output, {"action"}))
    assert actions
    for action in actions:
        assert abs(action["time_s"] - observations[action["decision_id"]]["time_s"] - delay) < 1e-8
    if delay == 1:
        assert observations["0-2"]["previous_action"]["decision_id"] == "0-1"


@pytest.mark.integration
def test_missing_executable_fails_before_run_creation(run_dir):
    config = Scenario(end_s=5, flows=[Flow(stop_s=3)], evaluation=[(1, 3)])
    output = run_dir / "missing"
    with pytest.raises(FileNotFoundError):
        asyncio.run(run_scenario(config, output, binary=run_dir / "absent-simulator"))
    assert not output.exists()


@pytest.mark.api
def test_real_api_serializes_independent_processes(run_dir):
    async def invoke(directory):
        arguments = [sys.executable, "-m", "tcp_lab.cli", "preflight", "--output", str(directory)]
        if "ZHIPU_KEY_FILE" in os.environ:
            arguments.extend(["--key-file", os.environ["ZHIPU_KEY_FILE"]])
        process = await asyncio.create_subprocess_exec(*arguments, cwd=ROOT,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()
        assert process.returncode == 0, stderr.decode()
        assert json.loads(stdout)["ready"]
        return json.loads((directory / "transport.json").read_text())

    async def parallel():
        return await asyncio.gather(invoke(run_dir / "a"), invoke(run_dir / "b"))

    records = asyncio.run(parallel())
    assert max(row["queue_seconds"] for row in records) > 0.1
    assert all(row["completed"] for row in records)
