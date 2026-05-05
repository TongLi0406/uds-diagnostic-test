---
name: uds-diagnostic-test
version: "2.1.0"
description: "UDS 诊断测试技能。Use when: 收到诊断调查表、UDS diagnostic survey table、生成 UDS 测试脚本、基于诊断资料生成测试、执行 UDS 诊断测试、CAN 测试、DID 测试、DTC 测试、IOControl 测试、RoutineControl 测试、诊断服务测试、diagnostic test script generation and execution via SocketCAN"
argument-hint: "提供诊断调查表文件路径，或描述需要测试的诊断服务"
---

# UDS 诊断测试技能

## 环境常量（不要猜测，使用以下固定值）

```bash
# 所有 Python 命令必须使用此路径，禁止使用系统 python/python3
PYTHON=/home/tongli123/qwen_env/bin/python

# 脚本目录
SKILL_DIR=/home/tongli123/.openclaw/workspace/skills/uds-diagnostic-test

# CAN 环境（已确认，无需验证）
CAN_CHANNEL=can0
CAN_IF=socketcan
DEFAULT_BITRATE=500000
DEFAULT_SAMPLE_POINT=0.800

# sudo 已配置免密（WSL2 环境）
```

## 禁止事项（严格执行）

以下操作是已知错误模式，**绝对禁止**：

| 错误模式 | 正确做法 |
|----------|----------|
| `/home/tongli123/movie_env/bin/python` | **只用** `/home/tongli123/qwen_env/bin/python` |
| `python3 script.py` 或 `python script.py` | **只用** `$PYTHON script.py` |
| `source ~/qwen_env/bin/activate` 然后 `python` | 每个 Bash 调用是新 shell，activate 无效。直接用 `$PYTHON` |
| `/bin/bash -u python ...` | `-u` 对 bash 无效，且不需要 bash 前缀。直接用 `$PYTHON` |
| 直接调用 `.py` 文件（如 `./script.py`） | 脚本已加入可执行权限，但为保险始终用 `$PYTHON script.py` |
| 无 `--fd` 初始化 CAN FD 设备 | 调查表有 `can_fd=true` 时必须用 `bash can_init.sh --fd --bitrate N` |
| 用 `can_init.sh` 后再次手动 `ip link set` | `can_init.sh` 已包含完整初始化，不要重复配置 |

## 触发场景

1. 收到诊断调查表 → 先询问用户是否需要生成测试脚本
2. 被要求基于资料生成测试脚本 → 直接解析并生成
3. 被要求生成并执行测试 → 生成后立即执行

## 工作流程（3 阶段）

### 阶段 1：解析诊断调查表 & 确认配置

**Step 1.0 验证文件存在（必须）：**

```bash
ls -la "<用户提供的文件路径>"
```

文件不存在时提示用户检查路径（WSL 下注意路径大小写：`/home/tongli123/.openclaw/media/inbound/`）。

**Step 1.1 解析调查表：**

```bash
$PYTHON $SKILL_DIR/scripts/uds_survey_parser.py \
  --input "<用户提供的调查表文件>" \
  --output /tmp/uds_parsed.json
```

支持的格式：Excel (.xlsx/.xls)、CSV (.csv)、JSON (.json)、文本/表格。

解析器会自动从调查表中提取：CAN ID (TX/RX)、波特率、采样点、CAN FD 标志等，保存在 `can_config` 字段中。

**Step 1.2 检查解析结果并告知用户：**

读取 `/tmp/uds_parsed.json`，重点检查：
- `can_config` — CAN 总线配置（波特率、CAN FD、TX/RX ID 等）
- `defaults_used` — 使用了默认值的属性列表
- `missing_attributes` — 完全缺失的属性

**用表格展示关键 CAN 配置给用户确认。**

**Step 1.3 询问用户确认配置：**

根据 `can_config` 内容，仅询问关键差异项：
- CAN ID (TX/RX) — 如调查表中有则使用
- CAN FD — 如 `can_config.can_fd=true`，告知用户"检测到 CAN FD 设备"并确认
- $27 SecurityAccess DLL — 如有 security level > 0 则需要
- CAN 通信日志 — 默认生成 `.asc` 文件

### 阶段 2：生成测试脚本

**基本命令（CAN FD 会自动从 parsed JSON 的 can_config 中继承）：**

```bash
$PYTHON $SKILL_DIR/scripts/uds_test_generator.py \
  --input /tmp/uds_parsed.json \
  --output /tmp/uds_test.py
```

生成器自动从 `can_config` 合并以下配置，**无需手动传参**（除非用户明确覆盖）：
- `bitrate`、`sample_point`、`tx_id`、`rx_id`、`func_id`
- `can_fd`、`fd_data_bitrate`、`fd_dsample_point`

### 阶段 3：初始化 CAN 并执行测试

**CAN 初始化入口（唯一）：`can_init.sh`**

生成的测试脚本在 `connect()` 时也会调用内置的 `_setup_socketcan()`（逻辑与 `can_init.sh` 完全一致：加载内核模块 → 强制 down → 配置 → up）。

**`can_init.sh` 使用说明（复制即用）：**

| 场景 | 命令 |
|------|------|
| Classic CAN（默认 500k/80%） | `bash $SKILL_DIR/scripts/can_init.sh` |
| Classic CAN（自定义） | `bash $SKILL_DIR/scripts/can_init.sh --bitrate 250000 --sp 0.750` |
| CAN FD（默认：仲裁500k/数据2M/双80%） | `bash $SKILL_DIR/scripts/can_init.sh --fd` |
| CAN FD（自定义） | `bash $SKILL_DIR/scripts/can_init.sh --fd --bitrate 500000 --dbitrate 2000000 --sp 0.800 --dsp 0.800` |
| 接口被占用，强制释放 | `bash $SKILL_DIR/scripts/can_init.sh --force` |
| 查看帮助 | `bash $SKILL_DIR/scripts/can_init.sh --help` |

**CAN FD 默认参数：**
- 仲裁段波特率: `500000` (500kbps)
- 数据段波特率: `2000000` (2Mbps)
- 仲裁段采样点: `0.800` (80%)
- 数据段采样点: `0.800` (80%)

**Step 3.1 初始化 CAN 接口：**

```bash
# Classic CAN
bash $SKILL_DIR/scripts/can_init.sh

# CAN FD（调查表 can_config.can_fd=true 时）
bash $SKILL_DIR/scripts/can_init.sh --fd
```

**Step 3.2 快速验证 CAN 连通性（推荐）：**

```bash
$PYTHON /tmp/uds_test.py --test-connection
```

| 输出 | 含义 |
|------|------|
| `[OK] CAN 连接成功` + `[OK] ECU 应答` | 正常，继续测试 |
| `[OK] CAN 连接成功` + `[WARN] ECU 无应答` | 检查 ECU 上电/CAN ID |
| `[ERROR] CAN 连接失败` | 检查 USB 连接/驱动 |

**Step 3.3 执行完整测试：**

```bash
$PYTHON /tmp/uds_test.py \
  --report /tmp/uds_report.md \
  --can-log /tmp/can_trace_$(date +%Y%m%d_%H%M%S).asc
```

---

## 测试用例覆盖策略

**对每个 DID（$22/$2E）：**
1. 各支持会话下读取 → 期望正响应
2. 不支持会话下读取 → 期望 NRC 0x7F
3. 功能寻址读取（如支持）→ 期望正响应
4. 验证响应数据长度
5. 无安全访问写入 → 期望 NRC 0x33
6. 正确会话+安全访问下写入 → 期望正响应
7. 错误长度数据写入 → 期望 NRC 0x13
8. 边界值写入（最小/最大）
9. 超范围值写入 → 期望 NRC 0x31

**对每个 IOControl（$2F）：**
1. 正确会话+安全等级下执行 → 期望正响应
2. 错误会话下执行 → 期望 NRC
3. 无安全访问执行 → 期望 NRC 0x33
4. ReturnControlToECU 测试

**对每个 Routine（$31）：**
1. 正确条件下 StartRoutine → 期望正响应
2. 错误会话下 → 期望 NRC
3. 无安全访问 → 期望 NRC 0x33
4. StopRoutine / RequestRoutineResults（如支持）

**对 DTC（$19/$14/$85）：**
1. ReadDTCInformation 各子功能
2. ClearDiagnosticInformation
3. ControlDTCSetting On/Off

**通用会话管理：**
1. DiagnosticSessionControl ($10)、SecurityAccess ($27)
2. TesterPresent ($3E)、ECUReset ($11)

---

## CAN 环境故障排查

所有 CAN 初始化统一经 `can_init.sh` (bash) 或测试脚本内置的 `_setup_socketcan()` (Python) — 两者逻辑一致。

如果初始化失败：

1. 检查 USB：`lsusb | grep -i peak`
2. 检查内核模块：`lsmod | grep -E "peak_usb|can_raw"`
3. 检查接口：`ip link show can0`
4. 如果接口被占用无法 down：
   ```bash
   bash $SKILL_DIR/scripts/can_init.sh --force
   ```
5. 手动恢复（仅在以上全部失败时）：
   ```bash
   sudo modprobe can can_raw peak_usb
   sudo fuser -k /sys/class/net/can0/
   sudo ip link set can0 down
   sudo ip link set can0 type can bitrate 500000 sample-point 0.800
   sudo ip link set can0 up
   ```

---

## UDS NRC 速查

| NRC | 名称 | 场景 |
|-----|------|------|
| 0x13 | incorrectMessageLengthOrInvalidFormat | 错误长度请求 |
| 0x22 | conditionsNotCorrect | 条件不满足 |
| 0x31 | requestOutOfRange | 无效 DID/参数值 |
| 0x33 | securityAccessDenied | 未解锁写入/控制 |
| 0x35 | invalidKey | 安全访问密钥错误 |
| 0x7F | serviceNotSupportedInActiveSession | 服务会话限制 |
| 0x78 | responsePending | 需等待继续接收 |

## 诊断调查表属性参考

### DID 默认值
| 属性 | 默认值 | 属性 | 默认值 |
|------|--------|------|--------|
| R/W State | "R" | Data Type | "RAW" |
| Size (Bytes) | 1 | Method Type | "identical" |
| Session Support | Default=Y, Extended=Y | Functional Addressing | "N" |

### IOControl / Routine / DTC 默认值
| 类型 | 属性 | 默认值 |
|------|------|--------|
| IOControl | IOControlParam | "ShortTermAdjustment" |
| IOControl | Security Level | "Level1" |
| Routine | ControlType | "StartRoutine(01)" |
| Routine | Security Level | "Level1" |
| DTC | Priority | 4 |
| DTC | DTC Aging | 40 |
