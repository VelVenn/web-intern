# TCP GLM 拥塞控制实验

使用 ns-3.49 复现 Reno、CUBIC，并由 GLM-4-Flash 根据发送端观测选择窗口保留比例，在实际拥塞事件中调整 `ssthresh`。

**构建需要 C++23、CMake 3.25 及以上、Ninja、uv，以及安装好的 ns-3.49。** nlohmann/json 3.12.0 由 CMake FetchContent 下载并验证 SHA-256；Python 3.12.13 与项目依赖由 uv 管理。Linux 和 macOS 使用相同的构建入口：

```bash
bash scripts/build.sh
```

ns-3 安装在自定义位置时，通过 CMake 参数传入安装前缀：

```bash
bash scripts/build.sh -DCMAKE_PREFIX_PATH=/path/to/ns3/install
```

uv 根据 `.python-version` 选择解释器，使用已提交的 `uv.lock` 同步项目 `.venv`；CMake 将构建产物写入 `build`。也可以在项目根目录直接执行标准命令：

```bash
uv python install
uv lock --check
uv sync --locked
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE="$PWD/.venv/bin/python"
cmake --build build --parallel 2
```

**运行配置通过 JSON 提供。** `configs/smoke.json` 执行真实 TCP 传输，`configs/protocol.json` 验证经典恢复过程，`configs/glm-check.json` 执行真实模型决策。输出目录必须尚未存在。

```bash
uv run --locked tcp-lab run configs/smoke.json --output results/smoke
uv run --locked tcp-lab analyze results/smoke
uv run --locked tcp-lab run configs/protocol.json --output results/protocol
```

**模型使用 `glm-4-flash-250414`。** 密钥从 `ZHIPU_API_KEY` 环境变量读取；也可以通过 `--key-file` 指定本地密钥文件。该文件包含一行密钥，可以附带以 `#` 开头的注释。认证内容不进入日志和仿真子进程。

```bash
uv run --locked tcp-lab preflight --output results/preflight --key-file /path/to/private/key
uv run --locked tcp-lab run configs/glm-check.json --output results/glm --key-file /path/to/private/key
uv run --locked tcp-lab analyze results/glm
uv run --locked tcp-lab run configs/glm-check.json --output results/replay --replay results/glm
```

重放使用已完成运行的实际动作，逐次核验观测内容。独立实验重新请求模型。请求失败、超时、响应结构错误和动作越界会立即终止运行，运行目录保留失败状态及原始响应。

项目内的 API 请求通过 filelock 串行执行，多个命令共享 `.glm-api.lock`。排队时间和实际请求耗时分别记录。

**自动测试执行实际仿真。** 协议测试覆盖数据交付、快重传、快恢复、超时、固定比例、不同算法竞争、网络变化和统计分析。API 测试调用真实服务，并检查动作生效、延迟和精确重放。

```bash
uv run --locked pytest -m 'not api'
ctest --test-dir build --output-on-failure
uv run --locked ruff check .
```

配置 `ZHIPU_API_KEY` 后执行全部测试：

```bash
uv run --locked pytest
```

API 测试还支持通过 `ZHIPU_KEY_FILE` 环境变量指定密钥文件。要求 API 的测试缺少密钥时会失败。实际仿真测试数据保存在 `build/test-runs`，每次运行使用独立编号。

**完整实验矩阵包含每个配置 20 次独立重复。** 生成器覆盖稳定容量、容量变化、随机丢包、同类与混合竞争、不同 RTT、连接变化、队列容量、传播时延、反向流量、决策延迟、固定比例、输入消融及无损容量参考。

```bash
uv run --locked tcp-lab matrix --output results/matrix --runs 20
uv run --locked tcp-lab suite results/matrix/manifest.json --output results/experiments
uv run --locked tcp-lab report results/experiments
```

矩阵清单记录全部计划配置；批量执行写入每项的运行状态，遇到错误立即终止。汇总使用完整运行的指标，同时报告失败和未配对情况。单次运行的统计结果保留样本数量，独立重复用于置信区间。

**容量恢复时间需要无损参考结果。** 运行矩阵中的 `reference-5`、`reference-20`、`reference-50` 配置并分析，再传入容量变化运行：

```bash
uv run --locked tcp-lab analyze results/capacity --references results/reference-5 results/reference-20
```

分析器验证参考运行的丢包数量。未指定参考值时，恢复时间状态为 `reference_required`。模型一致性测试从实际运行中抽取 30 个观测，每个重复请求 5 次：

```bash
uv run --locked tcp-lab consistency results/development --output results/consistency --samples 30 --repeats 5
```

**源文件按职责组织。**

| 文件 | 职责 |
| --- | --- |
| `cpp/controllers.h`、`cpp/controllers.cc` | 标准算法观测与 `TcpGlmReno` 阈值计算 |
| `cpp/flow.h`、`cpp/flow.cc` | 发送、接收、确认、重传和连接观测 |
| `cpp/rtt-observer.h` | 记录 TCP 实际提交给 RTT 估计器的样本 |
| `cpp/network-monitor.h`、`cpp/network-monitor.cc` | 排队、误码与数据包归属 |
| `cpp/topology.cc` | 拓扑、接口、队列和网络条件变化 |
| `cpp/experiment.h`、`cpp/experiment.cc` | 决策时序、进程通信、采样与结束记录 |
| `python/tcp_lab/config.py` | 实验配置和约束 |
| `python/tcp_lab/client.py`、`prompt.txt` | GLM 请求、响应校验和提示词 |
| `python/tcp_lab/runner.py` | 仿真进程、运行状态、重放与版本记录 |
| `python/tcp_lab/matrix.py` | 配置矩阵与批量执行 |
| `python/tcp_lab/analysis.py`、`report.py` | 指标、图表、置信区间和配对比较 |
| `python/tcp_lab/consistency.py` | 实际观测的重复模型请求 |

每次运行保存 `config.json`、`metadata.json`、`status.json`、`events.jsonl`、`samples.csv` 和 `network.json`。模型运行额外保存 `prompt.txt`、`decisions.jsonl` 与 `api` 请求响应目录。分析输出 `metrics.json`、`curves.png` 和 `curves.pdf`。

`TcpLinuxReno` 通过 ns-3 的 C++ 仿真对象实现窗口算法。macOS 使用与 ns-3 库一致的编译器、标准库和 CPU 架构，并执行相同的构建与测试命令。真实平台的验证结果见 `docs/VALIDATION.md`。
