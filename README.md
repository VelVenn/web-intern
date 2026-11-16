# TCP GLM 拥塞控制实验

项目在 ns-3.49 中运行 Reno、CUBIC 和 GLM 控制的 Reno，研究发送端观测驱动的参数选择如何影响 TCP 传输。GLM 根据 RTT、重传和确认速率选择窗口保留比例，TCP 在拥塞事件中使用这个比例计算慢开始阈值 `ssthresh`。

[技术说明](docs/DESIGN.md)定义拓扑、控制机制、配置字段与评价指标；[验证报告](docs/VALIDATION.md)给出实验条件、实测结果和完整复现步骤。

**准备构建环境。** 在项目根目录执行下文命令。需要可编译 C++23 的编译器、CMake 3.25 及以上、Ninja、uv，以及已安装的 ns-3.49。ns-3 的安装需要包含头文件、库和 `ns3Config.cmake`。应用和 ns-3 应使用一致的编译器、C++ 标准库与 CPU 架构。

Python 版本由 [.python-version](.python-version)固定，依赖声明在 [pyproject.toml](pyproject.toml)，具体版本由 [uv.lock](uv.lock)锁定。构建入口会安装所需 Python、同步 `.venv`、配置 CMake 并生成 `build/tcp-sim`：

```bash
bash scripts/build.sh
```

如果 ns-3 使用自定义安装前缀，将终端变量 `NS3_PREFIX` 设置为该前缀后执行：

```bash
bash scripts/build.sh -DCMAKE_PREFIX_PATH="$NS3_PREFIX"
```

CMake FetchContent 获取 nlohmann/json 3.12.0，并验证发布包 SHA-256。首次获取依赖需要网络访问。Python 解释器与缓存采用 uv 的标准管理方式，C++ 构建产物位于 `build`。

**读取配置，再选择场景。** JSON 文件描述网络、连接和统计区间；省略字段由 [配置模型](python/tcp_lab/config.py)补齐。`run` 会把包含默认值的完整配置保存为输出目录中的 `config.json`，可据此核查实际使用的参数。

四个示例共用哑铃拓扑：端点经独立的 1 Gbit/s 接入链路连接两个路由器，中间瓶颈为 20 Mbit/s。两段接入链路的单向时延各为 1 ms，瓶颈单向时延为 20 ms，基础传播 RTT 为 44 ms。默认瓶颈 FIFO 容量为 110000 字节，TCP MSS 为 1448 字节。

| 配置 | 显式设置与行为 | 运行目的 |
| --- | --- | --- |
| [smoke.json](configs/smoke.json) | 一条 Reno 连接在 1 s 启动、3 s 停止提供新数据，仿真至 12 s；关闭启动偏移；分别统计 `[1,3)` 与 `[3,12)` | 检查连接建立、持续发送、停止供给后的数据交付，以及字节计数 |
| [protocol.json](configs/protocol.json) | Reno 初始窗口为 1 MSS，阈值为 32 MSS；关闭 SACK，每段立即确认，使用经典恢复；丢弃正向瓶颈接收序列中从零计数的第 150 号数据包；开启详细事件和 PCAP | 观察慢开始、拥塞避免、重复 ACK、快重传与快恢复 |
| [glm-check.json](configs/glm-check.json) | 一条 GLM 连接在 1 s 启动、5 s 停止供给，仿真至 7 s；按包随机丢弃概率为 0.005；每个完整 1 s 观测窗口触发一次模型请求 | 核查模型决策及其实际参与的阈值计算 |
| [competition-check.json](configs/competition-check.json) | Reno、CUBIC、GLM 各一条连接同时在 1 s 启动，4 s 停止供给，仿真至 7 s | 观察三条连接竞争同一方向瓶颈时的带宽分配 |

`stop_s` 表示应用停止提交新数据，已进入 TCP 缓冲区的数据继续传输。`end_s` 决定整个仿真何时结束。短场景可能在截止时仍有待交付数据，该数量记录在 `network.json` 的 `pending_bytes` 中。

**运行基本传输并分析交付结果。** `--output` 指定一个尚未存在的运行目录；重复实验使用新的目录名称。以下两条命令先执行仿真，再从原始事件计算指标和图表：

```bash
uv run --locked tcp-lab run configs/smoke.json --output results/quickstart/smoke
uv run --locked tcp-lab analyze results/quickstart/smoke
```

检查 `status.json` 的 `status` 是否为 `complete`，这表示仿真正常执行至截止时间。随后读取 `network.json`：这个基本传输场景应当完整交付，`sent_bytes`、`received_bytes`、`acked_bytes` 一致，`pending_bytes` 为 0。`tx_bytes` 包含重传，`retrans_bytes` 单独记录重传有效载荷。

`metrics.json` 的 `intervals` 对应配置中的统计区间，`goodput_bps` 为每条连接的应用有效吞吐量，`total_goodput_bps` 为其总和。`curves.png` 和 `curves.pdf` 展示窗口、阈值、吞吐量、平滑 RTT 与比例变化。

**观察经典协议阶段。** 该配置把初始增长和指定丢包安排在同一次真实 TCP 传输中，统计区间为 `[1,8)` 与 `[8,18)`，仿真截止时间为 18 s：

```bash
uv run --locked tcp-lab run configs/protocol.json --output results/quickstart/protocol
uv run --locked tcp-lab analyze results/quickstart/protocol
```

在 `events.jsonl` 中检查 `cwnd`、`error_drop`、`tcp_ack`、`retransmission` 和 `congestion`。指定丢包之后应出现重复 ACK、重传、`CA_RECOVERY` 和后续 `CA_OPEN`。PCAP 用于进一步检查真实报文；`rto_value` 记录计时器数值变化，实际超时恢复由 `CA_LOSS` 事件识别。

**连接 GLM 服务。** 在当前终端配置自己的 `ZHIPU_API_KEY`。客户端调用模型 `glm-4-flash-250414`，使用非流式 JSON 响应与 `do_sample=false`。接口预检发送一个格式检查请求，成功后输出模型标识和 `ready: true`：

```bash
uv run --locked tcp-lab preflight --output results/quickstart/preflight
uv run --locked tcp-lab run configs/glm-check.json --output results/quickstart/glm
uv run --locked tcp-lab analyze results/quickstart/glm
```

也可通过 `--key-file` 指定自己的密钥文件；文件内容为一行密钥，可以附带空行和以 `#` 开头的注释。认证内容不进入实验记录。

`decisions.jsonl` 保存观测和动作；`api` 保存逐次请求、响应、耗时和校验结果。检查事件中的 `action` 与 `threshold_compute`：前者表示比例启用，后者表示一次实际阈值计算，两者通过 `decision_id` 关联。模型首次返回前，GLM 连接使用比例 0.5。

项目内的请求通过 `.glm-api.lock` 串行执行。`transport.json` 分别记录排队时间与实际请求耗时。调用、解析或校验失败时运行状态变为 `failed`，具体原因可从异常输出、响应正文和 `stderr.log` 核查。

**重放已经完成的控制过程。** 重放读取同一次运行保存的动作，并逐次比较观测内容。需要相同配置及匹配的仿真实现：

```bash
uv run --locked tcp-lab run configs/glm-check.json --output results/quickstart/replay --replay results/quickstart/glm
uv run --locked tcp-lab analyze results/quickstart/replay
```

重放成功时，`status.json` 的模式为 `replay`、状态为 `complete`；同一实现下可比较两次运行的 `samples.csv` 和 `events.jsonl`。新一次模型实验通过正常 `run` 命令重新请求服务。

**比较共享瓶颈中的连接。** 竞争场景的三条连接使用相同接入参数，分别采用 Reno、CUBIC 和 GLM：

```bash
uv run --locked tcp-lab run configs/competition-check.json --output results/quickstart/competition
uv run --locked tcp-lab analyze results/quickstart/competition
```

结合每条连接的 `goodput_bps`、`shares` 和 `jain` 判断带宽分配。三条活跃连接的 Jain 指数位于 1/3 至 1，越接近 1 表示吞吐量越均衡。吞吐量总和用于检查资源利用程度。

**执行自动验证。** 非 API 测试运行真实网络场景，检查传输、恢复、网络变化和统计计算；CTest 调用同一组非 API 测试。Ruff 检查 Python 代码：

```bash
uv run --locked pytest -m 'not api'
ctest --test-dir build --output-on-failure
uv run --locked ruff check .
```

配置 `ZHIPU_API_KEY` 后，以下命令增加真实服务、延迟生效、混合竞争和精确重放测试：

```bash
uv run --locked pytest
```

API 测试也接受环境变量 `ZHIPU_KEY_FILE` 指定密钥文件。真实仿真测试的输入和结果保存在 `build/test-runs`，每次运行有独立编号。

**生成和执行实验矩阵。** `matrix` 将 96 个场景展开为 JSON 配置；`--runs 20` 为每个场景设置运行编号 1 至 20，共生成 1920 项配置。`suite` 依次执行这些配置并分析各次运行；`report` 汇总已完成的指标：

```bash
uv run --locked tcp-lab matrix --output results/full-matrix --runs 20
uv run --locked tcp-lab suite results/full-matrix/manifest.json --output results/full-runs
uv run --locked tcp-lab report results/full-runs
```

矩阵包含 GLM 场景，执行 `suite` 前需配置密钥。`suite.json` 区分 `planned`、`running`、`complete` 和 `failed`；执行遇到错误即结束本次批次。`runs.csv` 保留每次运行的指标，`summary.json` 包含均值、95% 置信区间、配对差值和 API 请求统计。单个样本的置信区间字段为 `null`。

容量恢复时间还需要独立的无损参考值。参考场景、具体文件名、生成顺序及 `--references` 的使用方法见[容量变化实验复现流程](docs/VALIDATION.md)。模型一致性检查也从该流程生成的实际观测中抽样。完整配置定义和各类场景的目的见[技术说明](docs/DESIGN.md)。
