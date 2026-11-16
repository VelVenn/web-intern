import argparse
import asyncio
import json
from pathlib import Path

from .client import GlmClient
from .config import load_scenario
from .runner import run_scenario
from .runtime import api_key


async def preflight(args):
    client = GlmClient(api_key(args.key_file))
    try:
        print(json.dumps(await client.preflight(args.output), ensure_ascii=False))
    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(description="ns-3 TCP 与 GLM 参数调优实验")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="执行一个完整配置")
    run.add_argument("config", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--key-file", type=Path)
    run.add_argument("--binary", type=Path)
    run.add_argument("--replay", type=Path)
    probe = commands.add_parser("preflight", help="验证真实模型接口")
    probe.add_argument("--output", type=Path, required=True)
    probe.add_argument("--key-file", type=Path)
    analysis = commands.add_parser("analyze", help="分析运行数据并生成图表")
    analysis.add_argument("directory", type=Path)
    analysis.add_argument("--references", type=Path, nargs="*", default=[])
    matrix = commands.add_parser("matrix", help="生成完整实验配置")
    matrix.add_argument("--output", type=Path, required=True)
    matrix.add_argument("--runs", type=int, default=20)
    suite = commands.add_parser("suite", help="依次运行实验矩阵")
    suite.add_argument("manifest", type=Path)
    suite.add_argument("--output", type=Path, required=True)
    suite.add_argument("--key-file", type=Path)
    summary = commands.add_parser("report", help="汇总独立运行与置信区间")
    summary.add_argument("directory", type=Path)
    consistency = commands.add_parser("consistency", help="重复请求实际观测样本")
    consistency.add_argument("directory", type=Path)
    consistency.add_argument("--output", type=Path, required=True)
    consistency.add_argument("--key-file", type=Path)
    consistency.add_argument("--samples", type=int, default=30)
    consistency.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    if args.command == "run":
        output = asyncio.run(run_scenario(load_scenario(args.config), args.output,
            key_file=args.key_file, binary=args.binary, replay=args.replay))
        print(output)
    elif args.command == "preflight":
        asyncio.run(preflight(args))
    elif args.command == "analyze":
        from .analysis import analyze
        print(json.dumps(analyze(args.directory, args.references), ensure_ascii=False, indent=2))
    elif args.command == "matrix":
        from .matrix import generate
        print(generate(args.output, args.runs))
    elif args.command == "suite":
        from .matrix import run_suite
        asyncio.run(run_suite(args.manifest, args.output, args.key_file))
    elif args.command == "report":
        from .report import report
        print(report(args.directory))
    elif args.command == "consistency":
        from .consistency import evaluate
        asyncio.run(evaluate(args.directory, args.output, args.key_file, args.samples, args.repeats))


if __name__ == "__main__":
    main()
