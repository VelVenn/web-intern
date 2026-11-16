# TCP 控制实验的验证与复现

验证使用真实 ns-3 TCP 传输和 GLM API 请求，检查数据交付、协议恢复、模型动作生效和统计计算。记录的环境为 Ubuntu 26.04.1 x86_64、GCC 15.2.0、CMake 4.2.3、Ninja 1.13.2、ns-3.49、uv 0.12.1 和 Python 3.12.13。Linux 已执行实际构建与运行，macOS 实机验证状态为待执行。

下文命令均在项目根目录执行。需要 C++23 编译器、CMake 3.25 及以上、Ninja、uv 和安装好的 ns-3.49。构建脚本根据 `.python-version` 安装解释器，使用 `uv.lock` 同步 `.venv`，通过 CMake FetchContent 获取并校验 nlohmann/json 3.12.0：

```bash
bash scripts/build.sh
uv lock --check
```

自定义 ns-3 安装位置通过 `bash scripts/build.sh -DCMAKE_PREFIX_PATH="$NS3_PREFIX"` 传入，其中 `NS3_PREFIX` 为自己的安装前缀。GLM 步骤需要在终端配置自己的 `ZHIPU_API_KEY`，模型标识固定为 `glm-4-flash-250414`。各个 `--output` 目录必须尚未存在；重复复现时统一更换输出目录前缀。

[技术说明](DESIGN.md)提供完整字段定义，[使用说明](../README.md)介绍四个入门配置。以下实验各自列出所需条件、步骤和结果判定。

**基本传输验证字节交付。** [smoke.json](../configs/smoke.json)建立一条 Reno 连接，在 1 s 启动、3 s 停止提交新数据，继续运行至 12 s。瓶颈为 20 Mbit/s、单向传播时延 20 ms、FIFO 110000 字节；接入链路为 1 Gbit/s、单向时延 1 ms。关闭启动时间偏移，统计区间为 `[1,3)` 和 `[3,12)`。

```bash
uv run --locked tcp-lab run configs/smoke.json --output results/reproduce-transfer
uv run --locked tcp-lab analyze results/reproduce-transfer
```

运行生成完整配置、事件、周期采样和字节统计。分析生成 `metrics.json`、`curves.png` 和 `curves.pdf`。读取 `network.json`，应满足以下关系：

- `sent_bytes = received_bytes = acked_bytes`，说明应用提交的数据已交付并确认。
- `tx_bytes - retrans_bytes = sent_bytes`，用于核对完整传输中的首次发送字节数。
- `pending_bytes = 0`，说明截止时待交付数据已经清空。

已记录的实测中，三项提交、接收、确认计数均为 21,150,176 字节。独立 CMake 构建目录编译出的程序也完成了相同场景的交付。`status=complete` 表示仿真正常结束；交付是否完成由上述字节计数判定。

**确定性丢包验证经典恢复过程。** [protocol.json](../configs/protocol.json)将 Reno 初始窗口设为 1 MSS，阈值设为 32 MSS，MSS 为 1448 字节。关闭 SACK，每段立即确认，恢复算法为 `TcpClassicRecovery`，队列为 1000000 字节。正向瓶颈接收端丢弃从零计数的第 150 号包，包序列包含握手包。连接在 1 至 8 s 提供数据，仿真至 18 s，开启逐包事件和 PCAP。

```bash
uv run --locked tcp-lab run configs/protocol.json --output results/reproduce-protocol
uv run --locked tcp-lab analyze results/reproduce-protocol
```

| 验证内容 | 检查事件或数据 | 已记录结果 |
| --- | --- | --- |
| 慢开始与拥塞避免 | `cwnd` 从 1 MSS 增长，达到阈值后继续按 Reno 增长 | 自动测试通过 |
| 指定丢包 | `error_drop.check_index` 为 150 | 一个指定包被丢弃 |
| 快重传 | 同一 ACK 序号重复出现，重传发生在最小 1 s 超时之前 | 自动测试通过 |
| 快恢复 | `CA_RECOVERY` 之后出现 `CA_OPEN` | 自动测试通过 |
| 超时恢复 | 独立中断场景出现 `CA_LOSS`，窗口重置为 1 MSS，随后恢复接收 | 自动测试通过 |

超时测试在 2 至 4 s 将正向错误模型丢弃概率设为 1；它使用独立配置运行。`rto_value` 表示计时器数值变化，超时事件统计依据为进入 `CA_LOSS`。

**容量变化实验检验对网络条件的响应。** 三个算法各运行一条持续供给数据的连接，其余条件一致：

| 参数 | 实验值 |
| --- | --- |
| 拓扑 | 哑铃拓扑，每侧接入链路 1 Gbit/s、单向 1 ms |
| 瓶颈 | 初始 20 Mbit/s，单向传播时延 20 ms，FIFO 110000 字节 |
| TCP | MSS 1448 字节，初始窗口 10 MSS，初始阈值 4294967295 字节，发送和接收缓冲区各 16 MiB |
| TCP 选项 | SACK、Timestamp、窗口扩大开启；ECN 关闭；延迟确认计数为 2；使用 PRR；最小重传超时 1 s |
| 随机配置 | `seed=73`、`run=1`，启动时间为 1 s 加 0 至 0.1 s 的均匀偏移 |
| 网络变化 | 60 s 降至 5 Mbit/s，120 s 恢复 20 Mbit/s；队列字节容量固定 |
| 停止时间 | 180 s 停止提供新数据，210 s 结束仿真 |
| 稳定区间 | `[20,60)`、`[80,120)`、`[140,180)` |
| 模型配置 | 每 1 s 请求一次，携带最多五个窗口；允许比例为 0.4 至 0.8、步长 0.1；零仿真决策延迟 |
| 采样与损失 | 周期采样 0.1 s，随机丢包概率为 0；队列可能因拥塞丢弃数据包 |

首先生成配置。`--runs 1` 为 96 个场景各生成一个运行编号为 1 的 JSON 文件，下面选择其中三种容量参考和三种容量变化场景：

```bash
uv run --locked tcp-lab matrix --output results/reproduce-configs --runs 1
```

无损参考用于测量相同报文与链路条件下的有效传输能力。参考场景分别固定为 5、20、50 Mbit/s，使用 Reno，初始窗口 1000 MSS，初始阈值 1448000 字节，队列 16 MiB，关闭启动偏移和随机丢包；1 至 10 s 提供数据，20 s 结束，在 `[4,10)` 测量吞吐量。较大的在途数据量使参考连接能够充分使用链路。

```bash
for capacity in 5 20 50; do
  uv run --locked tcp-lab run "results/reproduce-configs/reference-${capacity}-01.json" --output "results/reproduce-runs/reference-${capacity}-01"
  uv run --locked tcp-lab analyze "results/reproduce-runs/reference-${capacity}-01"
done
```

检查各参考运行的 `network.json`：`error_drops` 和各队列 `dropped` 应为 0。分析器在使用参考结果时也会检查这一条件。参考吞吐量从各自 `metrics.json` 的第一个评价区间读取。

随后运行三种算法，并提供 5、20 Mbit/s 的参考目录。`--references` 读取已完成的配置、网络统计和指标文件：

```bash
for algorithm in reno cubic glm; do
  uv run --locked tcp-lab run "results/reproduce-configs/capacity-${algorithm}-01.json" --output "results/reproduce-runs/capacity-${algorithm}-01"
  uv run --locked tcp-lab analyze "results/reproduce-runs/capacity-${algorithm}-01" --references results/reproduce-runs/reference-5-01 results/reproduce-runs/reference-20-01
done
uv run --locked tcp-lab report results/reproduce-runs
```

有效吞吐量为统计区间内接收应用获得的有效字节数乘以 8，再除以区间长度。下表为已记录的一次独立运行，单位为 Mbit/s，每个算法的样本数量为 1。

| 算法 | `[20,60)` | `[80,120)` | `[140,180)` |
| --- | --- | --- | --- |
| Reno | 19.280120 | 4.820102 | 19.280120 |
| CUBIC | 19.280989 | 4.841822 | 19.280989 |
| GLM 控制的 Reno | 19.280989 | 4.820102 | 19.280989 |

三种算法在这些稳定区间都接近对应的无损参考吞吐量。模型控制的差异还需结合阈值事件、过渡过程、排队时延和多连接竞争结果判读。新一次模型调用使用其实际响应重新计算结果，保存的动作可用于重放同一次运行。

**恢复时间采用滑动窗口判据。** 变化后从第 1 s 开始，每隔 0.1 s 计算前 1 s 的有效吞吐量。达到新容量参考值的 90%，并在连续采样点保持至少 3 s 后，取首次达标时刻减去容量变化时刻。观察范围止于下一次变化或连接停止供给时间。

已记录的 5、20 Mbit/s 参考吞吐量分别约为 4.820875、19.279637 Mbit/s。GLM 运行在容量下降后的恢复时间为 3.3 s，容量恢复后的恢复时间为 1.0 s。对应数据在单次运行的 `metrics.json.recovery` 中。`reference_required` 表示需要提供参考结果，`not_reached` 表示在观察区间内未达到判据，`recovered` 表示已满足判据。

**模型动作通过事件关联验证。** 已记录的 GLM 容量变化运行产生 185 次参数启用和 43 次阈值计算事件。比例 0.5、0.6、0.7、0.8 分别出现 61、91、31、2 次。检查 `decisions.jsonl` 的动作，再用 `decision_id` 找到 `events.jsonl` 中的 `action` 和 `threshold_compute`，核对阈值是否满足：

$$
ssthresh=1448\cdot\max\left(2,\left\lfloor\frac{\beta\cdot cwnd}{1448}\right\rfloor\right)
$$

`decision_id=initial` 表示首次模型响应前使用的初始比例。参数启用次数与阈值计算次数分别统计，因为阈值在拥塞事件中计算。

该次运行的实际 API 耗时中位数约为 3.56 s，P95 约为 5.18 s。仿真决策延迟为 0，等待服务响应时仿真时间暂停。自动测试另外验证了 100 ms、500 ms 和 1 s 的仿真启用延迟。

**诊断评价使用真实丢弃事件生成标签。** 对每次决策最近 1 s 的本连接记录，按队列丢弃、误码丢弃、两者同时存在或均未出现，标注 `queue_loss`、`random_loss`、`mixed_loss` 或 `no_loss`。模型还可以输出 `uncertain`。准确率为正确分类数量除以全部决策数量，同时报告作答覆盖率和混淆矩阵。

| 该次容量变化运行的真实标签 | 模型输出 | 数量 |
| --- | --- | --- |
| `no_loss` | `no_loss` | 139 |
| `queue_loss` | `no_loss` | 46 |

总体准确率为 `139/185 = 75.14%`，队列丢包窗口的正确分类数量为 0。该分布表明，诊断准确率需要结合类别数量理解。阈值控制效果使用网络指标评价，诊断结果另行核验。

**固定观测实验检查重复请求的一致性。** 输入来自前述 Reno 容量变化运行的观测事件。程序从按时间排列的事件中等间隔选取 30 个样本，每个独立请求 5 次：

```bash
uv run --locked tcp-lab consistency results/reproduce-runs/capacity-reno-01 --output results/reproduce-consistency --samples 30 --repeats 5
```

读取 `status.json`，应包含 `samples=30`、`requests=150` 和 `status=complete`。每个样本的 `beta_agreement` 与 `diagnosis_agreement` 为最常见取值出现次数除以 5。已记录的 30 个样本中，两项一致率均为 1。逐次输入输出保存在该命令生成的目录中。

**共享瓶颈公平性通过多连接场景判读。** [competition-check.json](../configs/competition-check.json)让 Reno、CUBIC、GLM 各一条连接同时运行，共用 20 Mbit/s 瓶颈。连接在 1 至 4 s 供给数据，仿真至 7 s，评价区间为 `[2,4)` 和 `[4,7)`：

```bash
uv run --locked tcp-lab run configs/competition-check.json --output results/reproduce-competition
uv run --locked tcp-lab analyze results/reproduce-competition
```

每条连接应收到数据，模型动作应属于 GLM 连接。`metrics.json` 的每连接吞吐量和 `shares` 展示分配结果，Jain 指数为 `(各连接吞吐量之和)² ÷ (连接数 × 各吞吐量平方之和)`。三条同向活跃连接的指数越接近 1，分配越均衡；结合总吞吐量判断利用程度。活跃集合变化时，分析器按时间划分子区间并加权。

**自动验证检查协议与实现的一致性。** 配置密钥后执行全部测试，并生成可检查的 JUnit 报告：

```bash
uv run --locked pytest --junitxml=results/reproduce-tests.xml
ctest --test-dir build --output-on-failure
uv run --locked ruff check .
```

已记录的完整测试为 22 项，全部通过；CTest、Ruff 和依赖锁定检查通过。API 测试实际请求服务，并验证延迟生效、混合竞争、跨进程串行调用和保存动作的精确重放。非 API 测试可通过 `uv run --locked pytest -m 'not api'` 单独执行。

**独立重复用于统计比较。** 生成器包含 96 个场景，`--runs 20` 为每个场景生成 20 次重复，共 1920 项配置。`seed` 固定为 73，`run` 从 1 至 20；每次先独立计算指标，再统计均值和基于 Student t 分布的 95% 置信区间。相同场景、区间和运行编号用于配对比较。

```bash
uv run --locked tcp-lab matrix --output results/statistical-configs --runs 20
uv run --locked tcp-lab suite results/statistical-configs/manifest.json --output results/statistical-runs
uv run --locked tcp-lab report results/statistical-runs
```

批量执行按清单记录各项状态；恢复时间需要在完成对应参考场景后，按前述 `--references` 流程分析选定运行。`runs.csv` 保留每次运行的指标，`summary.json` 记录统计区间、样本数、置信区间和配对差值。本报告的实测范围为自动测试、上述容量变化与无损参考运行、固定观测一致性实验；1920 项正式运行的清单已经验证，完整矩阵尚未全部执行。
