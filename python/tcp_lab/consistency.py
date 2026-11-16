from collections import Counter
from pathlib import Path

from .analysis import events
from .client import GlmClient
from .config import write_json
from .runtime import api_key


async def evaluate(source: Path, directory: Path, key_file: Path | None,
                   samples: int = 30, repeats: int = 5):
    if samples < 1 or repeats < 2:
        raise ValueError("样本数必须为正数，重复次数至少为 2")
    observed = []
    for event in events(source, {"observation"}):
        event.pop("type")
        observed.append(event)
    if len(observed) < samples:
        raise ValueError("实际观测样本数量不足")
    selected = [observed[i * len(observed) // samples] for i in range(samples)]
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "observations.json", selected)
    client = GlmClient(api_key(key_file))
    results = []
    completed = False
    requests = 0
    try:
        for index, observation in enumerate(selected):
            actions = []
            for repeat in range(repeats):
                action = await client.decide(observation, directory / f"sample-{index}-{repeat}")
                actions.append(action.model_dump())
                requests += 1
            results.append({"sample": index, "actions": actions,
                "beta_agreement": Counter(a["beta"] for a in actions).most_common(1)[0][1] / repeats,
                "diagnosis_agreement": Counter(a["diagnosis"] for a in actions).most_common(1)[0][1] / repeats})
            write_json(directory / "consistency.json", results)
        completed = True
    finally:
        await client.close()
        write_json(directory / "status.json", {
            "status": "complete" if completed else "failed",
            "samples": len(results), "requests": requests, "planned_requests": samples * repeats,
        })
