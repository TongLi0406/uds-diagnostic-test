#!/bin/bash
# CAN 接口初始化脚本 (WSL2 + PCAN-USB Pro FD)
# 唯一入口 — 所有CAN初始化统一经过此处
# 用法:
#   Classic CAN:  bash can_init.sh
#                  bash can_init.sh --bitrate 500000 --sp 0.800
#   CAN FD:       bash can_init.sh --fd
#                  bash can_init.sh --fd --bitrate 500000 --dbitrate 2000000 --sp 0.800 --dsp 0.800
#   强制释放占用: bash can_init.sh --force
# 默认值:
#   Classic CAN: bitrate=500000, sp=0.800
#   CAN FD:      bitrate=500000(仲裁段), dbitrate=2000000(数据段), sp=0.800(仲裁段采样点), dsp=0.800(数据段采样点)

CHANNEL="can0"
FD_MODE=false
BITRATE=500000
DBITRATE=2000000
SAMPLE_POINT=0.800
DSAMPLE_POINT=0.800
FORCE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fd|-f) FD_MODE=true; shift ;;
        --channel|-c) CHANNEL="$2"; shift 2 ;;
        --bitrate|-b) BITRATE="$2"; shift 2 ;;
        --dbitrate|-d) DBITRATE="$2"; shift 2 ;;
        --sp|-s) SAMPLE_POINT="$2"; shift 2 ;;
        --dsp) DSAMPLE_POINT="$2"; shift 2 ;;
        --force) FORCE=true; shift ;;
        --help|-h)
            echo "用法: can_init.sh [选项]"
            echo ""
            echo "=== Classic CAN ==="
            echo "  bash can_init.sh"
            echo "  bash can_init.sh --bitrate 500000 --sp 0.800"
            echo ""
            echo "=== CAN FD (仲裁段500k, 数据段2M, 采样点均80%) ==="
            echo "  bash can_init.sh --fd"
            echo "  bash can_init.sh --fd --bitrate 500000 --dbitrate 2000000 --sp 0.800 --dsp 0.800"
            echo ""
            echo "=== 其他 ==="
            echo "  bash can_init.sh --channel can1               # 指定通道"
            echo "  bash can_init.sh --force                       # 强制释放占用后初始化"
            echo ""
            echo "默认值:"
            echo "  Classic CAN: bitrate=500000, sp=0.800"
            echo "  CAN FD:      bitrate=500000(仲裁段), dbitrate=2000000(数据段)"
            echo "               sp=0.800(仲裁段采样点), dsp=0.800(数据段采样点)"
            exit 0
            ;;
        *)
            # 位置参数兼容: 含小数点→采样点, 否则→bitrate(或dbitrate)
            case "$1" in
                *.*) SAMPLE_POINT="$1" ;;
                *) if [ "$FD_MODE" = true ] && [ "$BITRATE" != "500000" ]; then DBITRATE="$1"
                   else BITRATE="$1"; fi ;;
            esac
            shift
            ;;
    esac
done

echo "=== CAN 初始化 (${CHANNEL}) ==="
if [ "$FD_MODE" = true ]; then
    echo "[INFO] 模式: CAN FD (仲裁段 bitrate=${BITRATE}, 数据段 dbitrate=${DBITRATE}, sp=${SAMPLE_POINT}, dsp=${DSAMPLE_POINT})"
else
    echo "[INFO] 模式: Classic CAN (bitrate=${BITRATE}, sp=${SAMPLE_POINT})"
fi

# 1. 加载内核模块 (WSL2 必须)
for mod in can can_raw peak_usb; do
    if ! lsmod | grep -q "^${mod} "; then
        echo "[INFO] 加载 ${mod} 模块..."
        sudo modprobe ${mod} 2>/dev/null || { echo "[ERROR] 无法加载 ${mod} 模块"; exit 1; }
    fi
done
echo "[OK] 内核模块已加载 (can, can_raw, peak_usb)"

# 2. 检查接口是否存在
if ! ip link show ${CHANNEL} &>/dev/null; then
    echo "[ERROR] ${CHANNEL} 接口不存在，请检查 USB 连接"
    exit 1
fi

# 3. 强制 down (释放可能占用的 socket, 确保可重新配置)
if [ "$FORCE" = true ]; then
    echo "[INFO] 强制模式: 清理占用 ${CHANNEL} 的进程..."
    sudo fuser -k /sys/class/net/${CHANNEL}/ 2>/dev/null || true
    sleep 0.3
fi

sudo ip link set ${CHANNEL} down 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[INFO] ${CHANNEL} down 失败 (可能被占用), 尝试 fuser 释放..."
    sudo fuser -k /sys/class/net/${CHANNEL}/ 2>/dev/null || true
    sleep 0.3
    sudo ip link set ${CHANNEL} down 2>/dev/null || true
fi

# 4. 配置接口参数 (Classic CAN / CAN FD 统一路径)
if [ "$FD_MODE" = true ]; then
    sudo ip link set ${CHANNEL} type can \
        bitrate ${BITRATE} \
        dbitrate ${DBITRATE} \
        fd on \
        sample-point ${SAMPLE_POINT} \
        dsample-point ${DSAMPLE_POINT}
else
    sudo ip link set ${CHANNEL} type can \
        bitrate ${BITRATE} \
        sample-point ${SAMPLE_POINT}
fi

if [ $? -ne 0 ]; then
    echo "[ERROR] 配置 ${CHANNEL} 失败"
    exit 1
fi

# 5. 启用接口
sudo ip link set ${CHANNEL} up
if [ $? -ne 0 ]; then
    echo "[ERROR] 启用 ${CHANNEL} 失败"
    exit 1
fi

MODE_STR="bitrate=${BITRATE}"
if [ "$FD_MODE" = true ]; then
    MODE_STR="${MODE_STR}, dbitrate=${DBITRATE}, fd=on, dsp=${DSAMPLE_POINT}"
fi
echo "[OK] ${CHANNEL} 已就绪 (${MODE_STR}, sp=${SAMPLE_POINT})"
ip -details link show ${CHANNEL} | grep -E 'state|bitrate|dbitrate|sample-point|FD' | sed 's/^/  /'
echo "=== 初始化完成 ==="
