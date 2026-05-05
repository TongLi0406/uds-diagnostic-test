---
name: uds-diagnostic-test
version: "2.2.0"
description: "UDS 诊断测试技能。Use when: 收到诊断调查表、UDS diagnostic survey table、生成 UDS 测试脚本、基于诊断资料生成测试、执行 UDS 诊断测试、CAN 测试、DID 测试、DTC 测试、IOControl 测试、RoutineControl 测试、诊断服务测试、diagnostic test script generation and execution via SocketCAN"
argument-hint: "提供诊断调查表文件路径，或描述需要测试的诊断服务"
---

# UDS 诊断测试技能

## 环境准备（首次使用执行一次）

```bash
# 1. 确认 CAN 硬件已连接
lsusb | grep -i "peak\|can\|vector\|kvaser" || echo "未检测到CAN设备"

# 2. 安装 Python 依赖（使用 venv 或当前环境）
pip install python-can openpyxl

# 3. 验证 SocketCAN 可用
python3 -c "import can.interfaces.socketcan; print('SocketCAN OK')"
```

**环境要求：**
- Linux（含 WSL2），内核支持 SocketCAN + 对应驱动（peak_usb / gs_usb / mttcan 等）
- Python 3.8+，已安装 `python-can` 和 `openpyxl`
- CAN 硬件适配器（PEAK PCAN-USB、Kvaser、Vector 等支持 SocketCAN 的设备）
- sudo 权限（用于 `ip link set` 配置 CAN 接口）

## 会话初始化（每次 Agent 启动后执行一次）

Agent 收到 UDS 任务时，先设置以下变量：

```bash
# 使用本 SKILL.md 所在目录作为脚本根目录
SKILL_DIR="$(dirname "$0")/.." 2>/dev/null || SKILL_DIR="."

# 查找已安装 can 库的 Python（优先当前激活的 venv/conda）
PYTHON=$(which python3 2>/dev/null || which python 2>/dev/null)
$PYTHON -c "import can, openpyxl" 2>/dev/null || {
    echo "[WARN] 当前 Python 缺少 python-can 或 openpyxl，请先 pip install"
}
```

参数说明：
- `$SKILL_DIR` — 指向本技能根目录（SKILL.md 所在目录）
- `$PYTHON` — 已安装 `python-can` + `openpyxl` 的 Python 解释器
- 所有脚本使用 `$PYTHON $SKILL_DIR/scripts/xxx.py` 格式调用

## 禁止事项

| 错误模式 | 正确做法 |
|----------|----------|
| 使用系统 `python3`（未装 can 库） | 使用 `$PYTHON`（已确认 can+openpyxl 可用） |
| `source activate` 后分步执行 | 每个 shell 调用独立，统一用 `$PYTHON script.py` |
| 直接执行 `.py` 文件 | 始终用 `$PYTHON $SKILL_DIR/scripts/xxx.py` |
| 手动拼 `ip link set` 命令 | 统一用 `bash $SKILL_DIR/scripts/can_init.sh` |
| 跳过 CAN FD 参数 | 调查表有 `can_fd=true` 时必须用 `--fd` |

## 触发场景

1. 收到诊断调查表 → 先询问用户是否需要生成测试脚本
2. 被要求基于资料生成测试脚本 → 直接解析并生成
3. 被要求生成并执行测试 → 生成后立即执行

## 工作流程

### 阶段 1：解析诊断调查表 & 确认配置

**Step 1.0 验证文件存在：**

```bash
ls -la "<用户提供的文件路径>"
```

**Step 1.1 解析调查表：**

```bash
$PYTHON $SKILL_DIR/scripts/uds_survey_parser.py \
  --input "<调查表文件路径>" \
  --output /tmp/uds_parsed.json
```

支持格式：Excel (.xlsx/.xls)、CSV (.csv)、JSON (.json)、文本/表格。

解析器自动提取：CAN ID (TX/RX)、波特率、采样点、CAN FD 标志等 → `can_config` 字段。

**Step 1.2 检查解析结果：**

读取 `/tmp/uds_parsed.json`，检查 `can_config`、`defaults_used`、`missing_attributes`。
**用表格展示关键 CAN 配置给用户确认。**

**Step 1.3 询问用户确认：**
- CAN ID (TX/RX) — 调查表有则使用，否则默认 TX=0x7E0, RX=0x7E8
- CAN FD — 如 `can_config.can_fd=true` 则确认
- $27 SecurityAccess DLL — security level > 0 时需要
- CAN 通信日志 — 默认生成 `.asc` 文件

### 阶段 2：生成测试脚本

```bash
$PYTHON $SKILL_DIR/scripts/uds_test_generator.py \
  --input /tmp/uds_parsed.json \
  --output /tmp/uds_test.py
```

CAN 配置（bitrate、sample_point、TX/RX ID、CAN FD）自动从 `can_config` 继承，无需手动传参。

### 阶段 3：初始化 CAN & 执行测试

**`can_init.sh` 使用说明：**

| 场景 | 命令 |
|------|------|
| Classic CAN（默认 500k/80%） | `bash $SKILL_DIR/scripts/can_init.sh` |
| CAN FD（默认 500k/2M/双80%） | `bash $SKILL_DIR/scripts/can_init.sh --fd` |
| CAN FD 自定义参数 | `bash $SKILL_DIR/scripts/can_init.sh --fd --bitrate 500000 --dbitrate 2000000 --sp 0.800 --dsp 0.800` |
| 接口被占用，强制释放 | `bash $SKILL_DIR/scripts/can_init.sh --force` |
| 指定通道 | `bash $SKILL_DIR/scripts/can_init.sh --channel can1` |
| 查看帮助 | `bash $SKILL_DIR/scripts/can_init.sh --help` |

**CAN FD 默认参数：** 仲裁段 500kbps / 数据段 2Mbps / 采样点均为 80% (0.800)

**Step 3.1 初始化 CAN：**

```bash
# Classic CAN
bash $SKILL_DIR/scripts/can_init.sh

# CAN FD
bash $SKILL_DIR/scripts/can_init.sh --fd
```

**Step 3.2 验证连通性：**

```bash
$PYTHON /tmp/uds_test.py --test-connection
```

| 输出 | 含义 |
|------|------|
| `[OK] CAN 连接成功` + `[OK] ECU 应答` | 正常 |
| `[OK] CAN 连接成功` + `[WARN] ECU 无应答` | 检查 ECU 上电/CAN ID |
| `[ERROR] CAN 连接失败` | 检查 USB/驱动 |

**Step 3.3 执行测试：**

```bash
$PYTHON /tmp/uds_test.py \
  --report /tmp/uds_report.md \
  --can-log /tmp/can_trace_$(date +%Y%m%d_%H%M%S).asc
```

---

## CAN 初始化逻辑说明

CAN 初始化有唯一入口 `can_init.sh`（bash）和内置入口 `_setup_socketcan()`（Python 模板，嵌入生成的测试脚本），两者逻辑一致：

```
加载内核模块 (can, can_raw) → 检查接口 → 强制 down（失败则 fuser -k 释放）→ 配置 → up
```

- 参数已匹配 → 直接使用；不匹配 → 自动 down → 重新配置 → up
- 被占用 → `--force` 或自动 `fuser -k` 释放后重试

## CAN 故障排查

1. USB：`lsusb | grep -i peak`
2. 内核模块：`lsmod | grep -E "peak_usb|can_raw"`
3. 接口：`ip link show can0`
4. 强制初始化：`bash $SKILL_DIR/scripts/can_init.sh --force`
5. 手动恢复：
   ```bash
   sudo modprobe can can_raw peak_usb
   sudo fuser -k /sys/class/net/can0/
   sudo ip link set can0 down
   sudo ip link set can0 type can bitrate 500000 sample-point 0.800
   sudo ip link set can0 up
   ```

---

## 测试用例覆盖策略

**DID（$22/$2E）：** 会话验证 / 安全访问验证 / 长度验证 / 边界值 / 超范围 / 功能寻址

**IOControl（$2F）：** 正确执行 / 错误会话 / 无安全访问 / ReturnControlToECU

**Routine（$31）：** Start/Stop/RequestResults / 会话验证 / 安全访问验证

**DTC（$19/$14/$85）：** ReadDTCInformation / ClearDiagnosticInformation / ControlDTCSetting

**通用：** DiagnosticSessionControl ($10) / SecurityAccess ($27) / TesterPresent ($3E) / ECUReset ($11)

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

### DID 默认值（缺失时）

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
