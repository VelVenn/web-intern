import asyncio
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from .client import Action, GlmClient, PROMPT
from .config import Scenario, write_json
from .runtime import ROOT, api_key, digest, source_digest


async def run_scenario(config: Scenario, directory: Path, *, binary: Path | None = None,
                       key_file: Path | None = None, replay: Path | None = None) -> Path:
    directory = directory.resolve()
    binary = (binary or Path(os.environ.get("TCP_LAB_BINARY", ROOT / "build/tcp-sim"))).resolve()
    binary_hash = digest(binary)
    directory.mkdir(parents=True, exist_ok=False)
    settings = config.model_dump(mode="json")
    write_json(directory / "config.json", settings)
    status = {"status": "running", "mode": "replay" if replay else "live"}
    write_json(directory / "status.json", status)
    metadata = {
        "platform": platform.platform(), "architecture": platform.machine(),
        "python": sys.version, "binary_sha256": binary_hash,
        "project_source_sha256": source_digest(),
        "uv_lock_sha256": digest(ROOT / "uv.lock"),
        "uv": subprocess.check_output(["uv", "--version"], text=True).strip(),
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "seed": config.seed, "run": config.run,
        "random_streams": {"error": 1000, "starts": list(range(2000, 2000 + len(config.flows)))},
    }
    write_json(directory / "metadata.json", metadata)
    (directory / "prompt.txt").write_text(PROMPT, encoding="utf-8")
    client = None
    process = None
    replay_rows = []
    count = 0
    completed = False
    with (directory / "stderr.log").open("w", encoding="utf-8") as stderr, \
            (directory / "decisions.jsonl").open("w", encoding="utf-8") as decisions:
        try:
            if replay:
                recorded = json.loads((replay / "config.json").read_text())
                if recorded != settings:
                    raise ValueError("重放配置必须与原始运行完全一致")
                replay_rows = [json.loads(line) for line in (replay / "decisions.jsonl").read_text().splitlines()]
            elif any(f.algorithm == "glm" for f in config.flows):
                client = GlmClient(api_key(key_file))
            environment = {k: v for k, v in os.environ.items() if k != "ZHIPU_API_KEY"}
            process = await asyncio.create_subprocess_exec(
                str(binary), str(directory / "config.json"), str(directory),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=stderr, env=environment, limit=1024 * 1024,
            )
            async with asyncio.timeout(120):
                ready = json.loads(await process.stdout.readline())
            if ready.get("type") != "ready" or ready.get("protocol") != 1:
                raise ValueError("仿真初始化协议错误")
            metadata.update(ready)
            write_json(directory / "metadata.json", metadata)
            while True:
                async with asyncio.timeout(120):
                    line = await process.stdout.readline()
                if not line:
                    raise RuntimeError(f"仿真提前退出，详见 {directory / 'stderr.log'}")
                message = json.loads(line)
                if message.get("protocol") != 1:
                    raise ValueError("仿真协议版本错误")
                if message["type"] == "complete":
                    break
                if message["type"] != "observation":
                    raise ValueError("收到非预期的仿真消息")
                observation = message["observation"]
                if replay:
                    row = replay_rows[count]
                    if row["observation"] != observation:
                        raise ValueError(f"重放观测不一致：{observation['decision_id']}")
                    action = Action.model_validate(row["action"])
                else:
                    action = await client.decide(
                        observation, directory / "api" / observation["decision_id"], config.ablation)
                record = {"observation": observation, "action": action.model_dump()}
                decisions.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                decisions.flush()
                process.stdin.write((json.dumps({"protocol": 1, "type": "action",
                                                "action": action.model_dump()}) + "\n").encode())
                await process.stdin.drain()
                count += 1
            async with asyncio.timeout(30):
                code = await process.wait()
            if code != 0:
                raise RuntimeError(f"仿真退出码 {code}，详见 {directory / 'stderr.log'}")
            if replay and count != len(replay_rows):
                raise ValueError("重放结束时存在未使用的决策")
            completed = True
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()
            if client:
                await client.close()
            status.update(status="complete" if completed else "failed", decisions=count,
                          returncode=process.returncode if process else None)
            write_json(directory / "status.json", status)
    return directory
