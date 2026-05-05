# UDS Diagnostic Test Skill

UDS（Unified Diagnostic Services）诊断自动化测试工具，基于 SocketCAN + python-can，支持解析诊断调查表、生成测试脚本、通过 CAN 硬件执行测试并输出报告。

## 功能

- 解析诊断调查表（Excel/CSV/JSON），自动提取 DID、DTC、IOControl、Routine、CAN 配置
- 生成 100% 覆盖率的 UDS 测试脚本（会话验证/安全访问/边界值/NRC 验证）
- 通过 SocketCAN 执行测试，支持 Classic CAN 和 CAN FD
- 输出 Markdown 测试报告 + CAN 通信日志（.asc 格式，兼容 CANoe/CANalyzer）
- 支持 $27 SecurityAccess 自动解锁（Vector SeedKey DLL）

## 硬件要求

- **CAN 适配器**（任一即可）：
  - PEAK PCAN-USB / PCAN-USB FD（推荐）
  - Kvaser USBcan
  - Vector VN16xx
  - 其他 SocketCAN 兼容设备（gs_usb、mttcan 等）
- **Linux 环境**：原生 Linux 或 WSL2（内核需编译 SocketCAN + 对应驱动模块）
- **CAN 总线**：连接目标 ECU

## 安装

### 1. 安装 CAN 驱动

**PEAK PCAN-USB（推荐）：**
```bash
# 安装 peak-linux-driver
git clone https://github.com/linux-can/peak-linux-driver.git
cd peak-linux-driver
make
sudo make install
sudo modprobe peak_usb
```

**其他设备：** 参考 [linux-can 文档](https://github.com/linux-can) 安装对应驱动。

**设置开机自动加载（可选）：**
```bash
echo -e "can\ncan_raw\npeak_usb" | sudo tee /etc/modules-load.d/can.conf
```

### 2. 配置 sudo 免密（推荐，避免每次输入密码）

```bash
echo "$(whoami) ALL=(root) NOPASSWD: /sbin/ip link set can* type can *, /sbin/ip link set can* up, /sbin/ip link set can* down, /sbin/modprobe can*, /usr/bin/fuser -k /sys/class/net/can*" | sudo tee /etc/sudoers.d/can-setup
sudo chmod 440 /etc/sudoers.d/can-setup
```

### 3. 安装 Python 依赖

```bash
# 创建虚拟环境（推荐）
python3 -m venv ~/uds_env
source ~/uds_env/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 快速开始

### 1. 验证 CAN 环境

```bash
# 确认 CAN 设备已识别
lsusb | grep -i peak

# 初始化 CAN 接口
bash scripts/can_init.sh

# 确认接口已启用
ip -details link show can0
```

### 2. 解析诊断调查表

```bash
python scripts/uds_survey_parser.py --input survey.xlsx --output parsed.json
```

### 3. 生成测试脚本

```bash
python scripts/uds_test_generator.py --input parsed.json --output test_uds.py
```

### 4. 验证连通性（可选）

```bash
python test_uds.py --test-connection
```

### 5. 执行测试

```bash
bash scripts/can_init.sh                            # 初始化 CAN
python test_uds.py --report report.md               # 执行测试
```

### 6. 一步到位（Pipeline 模式）

```bash
python scripts/uds_pcan_runner.py pipeline \
  --input survey.xlsx \
  --output-dir ./output
```

## `can_init.sh` 参考

| 命令 | 说明 |
|------|------|
| `bash scripts/can_init.sh` | Classic CAN, 500kbps, 80% SP |
| `bash scripts/can_init.sh --fd` | CAN FD, 仲裁500k/数据2M, 双80% SP |
| `bash scripts/can_init.sh --fd --bitrate 500000 --dbitrate 2000000 --sp 0.800 --dsp 0.800` | CAN FD 自定义参数 |
| `bash scripts/can_init.sh --channel can1` | 指定 CAN 通道 |
| `bash scripts/can_init.sh --force` | 强制释放占用后初始化 |
| `bash scripts/can_init.sh --help` | 查看完整帮助 |

### CAN FD 默认参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 仲裁段波特率 | 500000 (500kbps) | `--bitrate` |
| 数据段波特率 | 2000000 (2Mbps) | `--dbitrate` |
| 仲裁段采样点 | 0.800 (80%) | `--sp` |
| 数据段采样点 | 0.800 (80%) | `--dsp` |

## 文件结构

```
uds-diagnostic-test/
├── SKILL.md                      # AI Agent 技能定义
├── README.md                     # 本文件
├── requirements.txt              # Python 依赖
├── scripts/
│   ├── uds_survey_parser.py      # 诊断调查表解析器
│   ├── uds_test_generator.py     # 测试脚本生成器
│   ├── uds_pcan_runner.py        # 测试执行器（含 Pipeline 模式）
│   └── can_init.sh               # CAN 接口初始化脚本
└── references/
    └── uds_nrc_reference.md      # UDS NRC 参考
```

## UDS 服务覆盖

| 服务 | SID | 说明 |
|------|-----|------|
| DiagnosticSessionControl | 0x10 | 会话切换 |
| ECUReset | 0x11 | ECU 复位 |
| ClearDiagnosticInformation | 0x14 | 清除 DTC |
| ReadDTCInformation | 0x19 | 读取 DTC |
| ReadDataByIdentifier | 0x22 | 读取 DID |
| SecurityAccess | 0x27 | 安全访问解锁 |
| WriteDataByIdentifier | 0x2E | 写入 DID |
| IOControlByIdentifier | 0x2F | IO 控制 |
| RoutineControl | 0x31 | 例程控制 |
| TesterPresent | 0x3E | 保活 |
| ControlDTCSetting | 0x85 | DTC 设置控制 |

## 测试报告示例

```markdown
# UDS 诊断测试报告
**日期**: 2026-05-05 19:50:43
**ECU**: Example_ECU
**CAN 通道**: can0
**CAN ID**: TX=0x7E0, RX=0x7E8

## 测试汇总
| 指标 | 数量 |
|------|------|
| 总测试用例 | 480 |
| 通过 (PASS) | 452 |
| 失败 (FAIL) | 3 |
| 跳过 (SKIP) | 25 |
| 通过率 | 94.2% |
```

## 故障排查

| 问题 | 检查方法 |
|------|----------|
| CAN 设备未识别 | `lsusb \| grep -i peak` |
| 驱动未加载 | `lsmod \| grep -E "peak_usb\|can_raw"` |
| 接口不存在 | `ip link show can0` |
| 接口被占用 | `bash scripts/can_init.sh --force` |
| Python 找不到 can 模块 | `pip install python-can` |
| 权限不足 | 确认 sudoers 配置或手动 `sudo` |
| ECU 无应答 | 检查 CAN ID (TX/RX)、波特率、ECU 供电 |

## License

MIT
