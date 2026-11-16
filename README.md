# TCP GLM 拥塞控制实验

项目使用 ns-3.49 运行 Reno、CUBIC 和 GLM 控制的 Reno。GLM 根据 RTT、重传和确认速率选择窗口保留比例，TCP 在拥塞事件中使用该比例计算慢开始阈值 `ssthresh`。

[DESIGN](docs/DESIGN.md)说明拓扑、控制机制、配置字段和指标；[VALIDATION](docs/VALIDATION.md)记录实验条件、已有结果及对应的复现流程。

## 1. 安装与构建

需要可编译 C++23 的编译器、CMake 3.25 及以上、Ninja、uv，以及已安装的 ns-3.49。ns-3 安装应包含头文件、库和 `ns3Config.cmake`；应用与 ns-3 使用一致的编译器、C++ 标准库和 CPU 架构。下文命令均在项目根目录执行。

构建脚本根据 [.python-version](.python-version)安装 Python，使用 [uv.lock](uv.lock)同步项目 `.venv`，再配置并编译 C++ 程序：

```bash
bash scripts/build.sh
```

成功后生成 `build/tcp-sim`，Python 命令入口为 `uv run --locked tcp-lab`。nlohmann/json 3.12.0 由 CMake FetchContent 获取并校验 SHA-256，首次获取依赖需要网络访问。Python 依赖声明位于 [pyproject.toml](pyproject.toml)，解释器和缓存采用 uv 的标准管理方式。

自定义 ns-3 安装位置通过安装前缀传入。将 `NS3_PREFIX` 设置为自己的安装前缀后执行：

```bash
bash scripts/build.sh -DCMAKE_PREFIX_PATH="$NS3_PREFIX"
```

## 2. 理解并选择配置

JSON 文件定义网络条件、连接和统计区间，省略字段由 [配置模型](python/tcp_lab/config.py)补齐。每次运行把展开后的配置保存为输出目录中的 `config.json`，用于核查实际参数。

| 配置内容 | 作用 |
| --- | --- |
| `rate_mbps`、`delay_ms`、`queue_bytes` | 瓶颈速率、单向传播时延和队列容量 |
| `flows` | 每个对象定义一条连接，选择算法、启动和停止供给时间、接入时延及方向 |
| `changes` | 指定某个仿真时刻发生的瓶颈速率或时延变化 |
| `evaluation` | 指定指标统计区间，采用左闭右开形式 |
| `seed`、`run` | 固定随机配置并区分独立重复 |
| `end_s` | 整个仿真的截止时间 |

连接的 `stop_s` 表示停止向 TCP 提交新数据，已提交的数据继续传输。`end_s` 决定观察何时结束；截止时尚未交付的数据记录为 `pending_bytes`。全部字段、单位、默认值和约束见 DESIGN 的配置定义。

四个示例采用哑铃拓扑：每侧接入链路为 1 Gbit/s、单向 1 ms，共享瓶颈为 20 Mbit/s、单向 20 ms，基础传播 RTT 为 44 ms。默认瓶颈 FIFO 为 110000 字节，MSS 为 1448 字节。

| 示例配置 | 场景设置 | 用途与检查重点 |
| --- | --- | --- |
| [smoke.json](configs/smoke.json) | 一条 Reno 连接，1 至 3 s 提供数据，仿真至 12 s | 核对完整交付及提交、发送、接收、确认字节数 |
| [protocol.json](configs/protocol.json) | Reno 初始窗口 1 MSS、阈值 32 MSS；经典恢复、关闭 SACK、每段立即确认；队列 1000000 字节；丢弃正向接收序列中从零计数的第 150 号包；1 至 8 s 提供数据，仿真至 18 s | 观察窗口增长、重复 ACK、快重传与快恢复，保存详细事件和 PCAP |
| [glm-check.json](configs/glm-check.json) | 一条 GLM 连接，1 至 5 s 提供数据，仿真至 7 s；按包随机丢弃概率 0.005 | 检查模型响应、参数启用和实际阈值计算 |
| [competition-check.json](configs/competition-check.json) | Reno、CUBIC、GLM 各一条连接，1 至 4 s 提供数据，仿真至 7 s | 检查共享瓶颈中的各连接吞吐量、带宽份额与公平性 |

这些示例都关闭启动时间偏移。统计区间分别写在各自的 `evaluation` 字段中。

## 3. 运行单个场景与判读结果

### 3.1 基本运行与分析

`run` 读取配置并执行仿真，`analyze` 从已完成运行的原始事件计算指标和图表。`--output` 指定尚未存在的目录；重复运行时使用新目录。

```bash
uv run --locked tcp-lab run configs/smoke.json --output results/quickstart/smoke
uv run --locked tcp-lab analyze results/quickstart/smoke
```

运行其他示例时，替换配置文件，并为该次运行指定独立输出目录。输出按以下顺序查看：

| 文件 | 读取内容 | 判读方法 |
| --- | --- | --- |
| `status.json` | `status`、`mode`、退出码 | `complete` 表示仿真正常结束；`failed` 时结合异常输出和 `stderr.log` 定位原因 |
| `config.json` | 展开后的所有参数 | 确认默认值、连接列表、变化事件和统计区间 |
| `network.json` | `flows` 数组中的字节计数与完成时间 | 基本传输场景应有 `sent_bytes = received_bytes = acked_bytes`、`pending_bytes = 0`；`tx_bytes` 包含重传，`retrans_bytes` 单独记录重传有效载荷 |
| `metrics.json` | `intervals` 中的吞吐量、RTT、份额和 Jain 指数 | 结合区间、连接数量及容量解释；三条同向活跃连接的 Jain 指数越接近 1，分配越均衡 |
| `events.jsonl`、`samples.csv` | 协议事件与周期采样 | 通过事件时间追踪窗口、重传、恢复和参数变化 |
| `curves.png`、`curves.pdf` | 窗口、阈值、吞吐量、平滑 RTT 与比例曲线 | 窗口实线和阈值虚线配合拥塞事件查看；初始化的大阈值保存在原始记录中 |

协议场景重点检查 `error_drop` 后的重复 `tcp_ack`、`retransmission`、`CA_RECOVERY` 和 `CA_OPEN`。`rto_value` 表示计时器数值变化，实际超时恢复由进入 `CA_LOSS` 识别。

### 3.2 模型调用与动作生效

GLM 场景需要在当前终端配置自己的 `ZHIPU_API_KEY`。客户端调用 `glm-4-flash-250414`，使用非流式 JSON 响应和 `do_sample=false`。预检检查认证、模型标识和输出格式，成功后返回 `ready: true`：

```bash
uv run --locked tcp-lab preflight --output results/quickstart/preflight
uv run --locked tcp-lab run configs/glm-check.json --output results/quickstart/glm
uv run --locked tcp-lab analyze results/quickstart/glm
```

也可通过 `--key-file` 指定自己的密钥文件；文件包含一行密钥，可以附带空行和以 `#` 开头的注释。认证内容不进入实验记录。

`decisions.jsonl` 保存观测和动作，`api` 目录保存逐次请求、响应和耗时。事件 `action` 表示比例启用，`threshold_compute` 表示一次实际阈值计算，二者通过 `decision_id` 关联。模型首次返回前使用比例 0.5。

项目内的请求通过 `.glm-api.lock` 串行执行，`transport.json` 分别记录排队和请求耗时。调用、解析或动作校验失败时，当前运行终止并记录失败状态。

### 3.3 重放控制过程

重放读取已完成运行的动作，并逐次核对观测。使用相同配置和匹配的仿真实现：

```bash
uv run --locked tcp-lab run configs/glm-check.json --output results/quickstart/replay --replay results/quickstart/glm
```

成功时，`status.json` 的模式为 `replay`、状态为 `complete`。同一实现下可核对原运行与重放的 `samples.csv`、`events.jsonl`；新一次模型实验通过正常 `run` 重新请求服务。

## 4. 批量实验与统计

`matrix` 将 96 个场景展开为配置，`--runs 20` 为每个场景生成运行编号 1 至 20，共 1920 项。`suite` 依次执行配置并分析每次运行，`report` 汇总已有指标。矩阵包含 GLM 场景，运行前需配置密钥。

```bash
uv run --locked tcp-lab matrix --output results/full-matrix --runs 20
uv run --locked tcp-lab suite results/full-matrix/manifest.json --output results/full-runs
uv run --locked tcp-lab report results/full-runs
```

`suite.json` 记录 `planned`、`running`、`complete` 和 `failed`；执行遇到错误即结束当前批次。`runs.csv` 保留每次运行的指标，`summary.json` 保存均值、95% 置信区间、配对差值和 API 请求统计。样本数为 1 时，置信区间为 `null`。

容量恢复时间需要额外提供无损参考运行。参考值生成、比较场景分析和模型一致性检查的完整顺序集中在 VALIDATION 第 5 节；实验矩阵各类场景的目的见 DESIGN。

## 5. 自动测试

非 API 测试执行实际网络场景，检查传输、协议恢复、网络变化和统计计算。CTest 调用同一组非 API 测试；Ruff 检查 Python 代码。

```bash
uv run --locked pytest -m 'not api'
ctest --test-dir build --output-on-failure
uv run --locked ruff check .
```

配置 `ZHIPU_API_KEY` 后，执行全部测试可覆盖真实模型请求、延迟生效、混合竞争、跨进程串行调用和精确重放：

```bash
uv run --locked pytest
```

API 测试也接受 `ZHIPU_KEY_FILE` 环境变量指定密钥文件。每次测试的实际仿真数据保存在 `build/test-runs` 的独立目录中。已完成测试的证据与结果见 VALIDATION 第 2 节。
