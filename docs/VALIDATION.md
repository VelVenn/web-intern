# TCP 控制实验的验证报告

## 1. 实验设置与验证范围

实验分别检查 TCP 协议执行、容量变化下的传输表现，以及 GLM 决策的生效过程、诊断准确率和重复选择的一致性。环境为 Ubuntu 26.04.1 x86_64、GCC 15.2.0、CMake 4.2.3、Ninja 1.13.2、ns-3.49、uv 0.12.1 和 Python 3.12.13。

网络采用哑铃拓扑：每条连接经两个路由器之间的共享瓶颈传输数据，ACK 沿原路径返回。两侧接入链路各为 1 Gbit/s、单向传播时延 1 ms；瓶颈单向传播时延为 20 ms，基础传播 RTT 为 44 ms。默认瓶颈 FIFO 为 110000 字节，MSS 为 1448 字节，发送和接收缓冲区各为 16 MiB。

| 实验 | 具体条件 | 已有记录 |
| --- | --- | --- |
| 基本传输 | 一条 Reno 连接，1 至 3 s 提供数据，仿真至 12 s，关闭启动偏移 | 数据交付及计数核验 |
| 经典恢复 | 初始窗口 1 MSS、阈值 32 MSS，关闭 SACK，每段立即确认，使用经典恢复；队列 1000000 字节；丢弃正向接收序列中从零计数的第 150 号包 | 窗口、ACK、丢包、重传和恢复事件 |
| 容量变化 | Reno、CUBIC、GLM 控制的 Reno 各运行一条连接；60 s 从 20 降至 5 Mbit/s，120 s 恢复至 20 Mbit/s | 每种算法一次独立运行 |
| 容量参考 | 固定 5、20、50 Mbit/s；Reno 初始窗口 1000 MSS、阈值 1448000 字节；队列 16 MiB；1 至 10 s 提供数据，仿真至 20 s | 三个无损参考运行 |
| 模型一致性 | 从 Reno 容量变化运行抽取 30 个观测，每个独立请求 5 次 | 150 次实际请求 |
| 自动测试 | 传输、恢复、网络变化、竞争、模型接口、延迟与重放 | 22 项通过 |

容量变化运行使用 `seed=73`、`run=1`，连接在 1 s 加 0 至 0.1 s 均匀偏移后启动，180 s 停止提供新数据，210 s 结束仿真。TCP 初始窗口为 10 MSS，初始阈值为 4294967295 字节；SACK、Timestamp 和窗口扩大开启，ECN 关闭，延迟确认计数为 2，使用 PRR，最小重传超时为 1 s。队列容量保持固定，随机丢包概率为 0。

GLM 使用 `glm-4-flash-250414`，每 1 s 接收最多五个观测窗口，从 0.4、0.5、0.6、0.7、0.8 中选择窗口保留比例。容量变化运行采用零仿真决策延迟，真实 API 耗时单独记录。

现有实测覆盖上表项目。实验生成器另提供 96 个场景，每场景 20 次重复可生成 1920 项配置；完整矩阵尚未全部执行。平台实测已完成 Linux，macOS 实机验证待执行。

## 2. 协议与功能验证

协议验证通过报文和状态事件检查实现行为。基本传输场景检查数据是否完整交付，确定性丢包场景观察快恢复，独立中断场景观察超时恢复。

| 验证对象 | 判定依据 | 实测结果 |
| --- | --- | --- |
| 数据交付 | 应用提交、接收和 ACK 确认计数相等，截止时待交付字节数为 0 | 三项计数均为 21,150,176 字节 |
| 首次发送计数 | 全部发送有效载荷减去重传有效载荷，等于应用提交字节数 | 核验通过 |
| 慢开始与拥塞避免 | 窗口从 1 MSS 增长，达到阈值后继续按 Reno 机制增长 | 自动测试通过 |
| 快重传与快恢复 | 指定丢包后出现重复 ACK，重传早于最小 1 s 超时，随后进入 `CA_RECOVERY` 并返回 `CA_OPEN` | 自动测试通过 |
| 超时恢复 | 在 2 至 4 s 中断场景中出现 `CA_LOSS`，窗口重置为 1 MSS，随后恢复接收 | 自动测试通过 |
| 模型动作与重放 | 决策编号对应实际阈值计算；保存动作重放时，观测和事件一致 | 自动测试通过 |
| 决策延迟与并发 | 分别检查 100 ms、500 ms、1 s 的启用时间，以及独立进程的请求串行执行 | 自动测试通过 |
| 混合竞争 | Reno、CUBIC、GLM 共享瓶颈，三条连接均接收数据，模型动作属于 GLM 连接 | 自动测试通过 |

字节计数位于 `network.json` 的 `flows` 数组，协议过程保存在 `events.jsonl`。`status=complete` 表示仿真正常结束，`pending_bytes` 表示截止时尚未交付的应用数据；这两个字段分别描述运行状态和交付状态。

已有完整测试报告包含 22 项通过记录。CTest 的非 API 测试、Ruff 检查和 uv 依赖锁定检查也已通过。独立 CMake 构建目录编译出的程序完成了相同基本传输场景的交付。

## 3. 容量变化下的传输表现

### 3.1 阶段吞吐量

三个评价区间为 `[20,60)`、`[80,120)` 和 `[140,180)`，分别对应容量变化后的稳定阶段。有效吞吐量按区间内接收应用获得的有效字节数乘以 8，再除以区间长度计算。下表单位为 Mbit/s，每个算法的样本数量为 1。

| 算法 | 20 Mbit/s 初始阶段 | 5 Mbit/s 阶段 | 20 Mbit/s 恢复阶段 |
| --- | --- | --- | --- |
| Reno | 19.280120 | 4.820102 | 19.280120 |
| CUBIC | 19.280989 | 4.841822 | 19.280989 |
| GLM 控制的 Reno | 19.280989 | 4.820102 | 19.280989 |

无损参考运行在 `[4,10)` 测量有效吞吐量，其队列丢弃和误码丢弃均为 0。5、20 Mbit/s 链路的参考值分别约为 4.820875、19.279637 Mbit/s。三种算法在本次单连接运行的稳定区间均接近相应参考值。

### 3.2 变化后的恢复时间

容量变化后，从第 1 s 开始每隔 0.1 s 计算前 1 s 的有效吞吐量。达到新容量参考值的 90%，并在连续采样点保持至少 3 s 后，以首次达标时刻减去容量变化时刻作为恢复时间。观察范围止于下一次变化或连接停止供给时间。

| GLM 运行中的变化 | 恢复时间 |
| --- | --- |
| 20 降至 5 Mbit/s | 3.3 s |
| 5 恢复至 20 Mbit/s | 1.0 s |

阶段吞吐量衡量稳定传输能力，恢复时间衡量变化后的响应过程。两项指标共同描述这次容量变化运行；多连接带宽分配通过竞争场景评价。

## 4. 模型决策与实际行为

### 4.1 参数选择与阈值计算

GLM 容量变化运行产生 185 次参数启用和 43 次阈值计算事件。每次阈值计算将当前 `cwnd` 乘以有效比例，向下取整为 1448 字节的整数倍，下限为 2896 字节。参数启用和阈值计算通过 `decision_id` 关联；`initial` 表示首次模型响应前使用的比例 0.5。

| 窗口保留比例 | 0.4 | 0.5 | 0.6 | 0.7 | 0.8 |
| --- | --- | --- | --- | --- | --- |
| 模型选择次数 | 0 | 61 | 91 | 31 | 2 |

参数启用次数与阈值计算次数分别反映模型选择和拥塞事件。同一个有效比例可以用于多次阈值计算，也可能在下一次拥塞前被新决策更新。

该次运行的 API 实际耗时中位数约为 3.56 s，P95 约为 5.18 s。等待响应期间仿真时间暂停，因此这组网络性能数据对应第 1 节所列的零仿真决策延迟。

### 4.2 丢包原因诊断

诊断标签依据每次决策前 1 s 内本连接的真实丢弃事件生成。队列丢弃、误码丢弃、两者同时存在和均未出现，分别对应 `queue_loss`、`random_loss`、`mixed_loss` 和 `no_loss`。模型还可以回答 `uncertain`。

| 真实标签 | 模型输出 | 窗口数量 |
| --- | --- | --- |
| `no_loss` | `no_loss` | 139 |
| `queue_loss` | `no_loss` | 46 |

总体准确率为 `139/185 = 75.14%`，队列丢包窗口的正确分类数量为 0。模型在这些窗口中均选择了 `no_loss`，因此总体准确率与无丢包窗口的占比相同。诊断评价保留这一类别分布，控制效果则使用第 3 节的网络指标衡量。

### 4.3 重复选择的一致性

从 Reno 容量变化运行的观测序列中等间隔选取 30 个样本，每个样本独立请求 5 次。每个样本的一致率为最常见取值出现次数除以 5，比例选择和诊断分类分别统计。

150 次实际请求已完成。在这 30 个样本中，`beta_agreement` 和 `diagnosis_agreement` 均为 1。一致率描述相同输入下重复输出的稳定性，分类准确率由真实丢弃事件核验。

## 5. 复现步骤

### 5.1 运行前提与协议场景

在项目根目录执行命令，先按 [README](../README.md)完成构建，并为模型步骤配置自己的 `ZHIPU_API_KEY`。每个运行输出目录应尚未存在；重复复现时统一更换目录前缀。参数定义见 [DESIGN](DESIGN.md)。

[smoke.json](../configs/smoke.json)用于核对完整交付，[protocol.json](../configs/protocol.json)用于检查指定丢包后的恢复过程。运行产生原始事件，分析生成指标与曲线：

```bash
for scenario in smoke protocol; do
  uv run --locked tcp-lab run "configs/${scenario}.json" --output "results/reproduce/${scenario}"
  uv run --locked tcp-lab analyze "results/reproduce/${scenario}"
done
```

在基本传输输出的 `network.json` 中核对第 2 节的字节关系；在协议输出的 `events.jsonl` 中检查 `error_drop`、`tcp_ack`、`retransmission` 和 `congestion`，PCAP 可用于检查对应报文。全部自动测试的执行方式见 README。

### 5.2 生成容量实验配置与参考值

生成器根据 [matrix.py](../python/tcp_lab/matrix.py)产生 96 个场景的配置。`--runs 1` 为每个场景生成运行编号 1；下面选用三个参考场景和三个容量变化场景。

```bash
uv run --locked tcp-lab matrix --output results/reproduce/configs --runs 1
for capacity in 5 20 50; do
  uv run --locked tcp-lab run "results/reproduce/configs/reference-${capacity}-01.json" --output "results/reproduce/reference-${capacity}-01"
  uv run --locked tcp-lab analyze "results/reproduce/reference-${capacity}-01"
done
```

参考场景使用第 1 节的固定容量、大窗口和大队列设置。检查 `network.json` 的 `error_drops` 与各队列 `dropped` 均为 0；`metrics.json` 的第一个评价区间提供参考吞吐量。

### 5.3 运行比较场景并计算恢复时间

三份容量变化配置分别选择 Reno、CUBIC、GLM，其余条件与第 1 节一致。`--references` 读取已完成的 5、20 Mbit/s 参考配置、网络统计和指标文件。

```bash
for algorithm in reno cubic glm; do
  uv run --locked tcp-lab run "results/reproduce/configs/capacity-${algorithm}-01.json" --output "results/reproduce/capacity-${algorithm}-01"
  uv run --locked tcp-lab analyze "results/reproduce/capacity-${algorithm}-01" --references results/reproduce/reference-5-01 results/reproduce/reference-20-01
done
```

`metrics.json.intervals` 保存三个阶段的吞吐量、RTT 和公平性；`recovery` 保存恢复时间。`recovered` 表示达到判据，`not_reached` 表示观察区间内未达到，`reference_required` 表示需要提供对应容量的参考结果。新一次 GLM 实验按实际响应重新统计，重放同一次控制过程的步骤见 README。

### 5.4 检查一致性并汇总结果

一致性检查使用前一步 Reno 运行中已经产生的观测，30 个样本各请求 5 次：

```bash
uv run --locked tcp-lab consistency results/reproduce/capacity-reno-01 --output results/reproduce/consistency --samples 30 --repeats 5
uv run --locked tcp-lab report results/reproduce
```

一致性目录中的 `status.json` 应记录 `samples=30`、`requests=150`、`status=complete`；`consistency.json` 保存逐样本的一致率。汇总生成 `runs.csv`、`summary.json` 和比较图，保留场景、区间与样本数量。单次运行的置信区间为 `null`；需要独立重复的统计比较时，使用 README 中的批量实验流程。
