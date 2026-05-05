#!/bin/bash
# CAN 接口初始化脚本 (WSL2 + PCAN-USB Pro FD)
# 用法:
#   Classic CAN:  bash can_init.sh
#   Classic CAN:  bash can_init.sh --bitrate 500000 --sp 0.800
#   CAN FD:       bash can_init.sh --fd --bitrate 2000000 --dbitrate 2000000 --sp 0.800
#   CAN FD (简写): bash can_init.sh --fd 2000000
# 默认值: bitrate=500000, dbitrate=2000000, sp=0.800, channel=can0

CHANNEL="can0"
FD_MODE=false
BITRATE=500000
DBITRATE=2000000
SAMPLE_POINT=0.800

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fd|-f) FD_MODE=true; shift ;;
        --channel|-c) CHANNEL="$2"; shift 2 ;;
        --bitrate|-b) BITRATE="$2"; shift 2 ;;
        --dbitrate|-d) DBITRATE="$2"; shift 2 ;;
        --sp|-s) SAMPLE_POINT="$2"; shift 2 ;;
        --help|-h)
            echo "用法: can_init.sh [--fd] [--bitrate N] [--dbitrate N] [--sp N] [--channel canX]"
            echo "  Classic CAN:  bash can_init.sh --bitrate 500000 --sp 0.800"
            echo "  CAN FD:       bash can_init.sh --fd --bitrate 2000000 --dbitrate 2000000 --sp 0.800"
            exit 0
            ;;
        *)
            # 位置参数兼容: 第一个=bitrate, 第二个=dbitrate(仅FD)/sp(classic)
            if [ "$FD_MODE" = true ]; then
                case "$1" in
                    *.*) SAMPLE_POINT="$1" ;;  # 含小数点 → 采样点
                    *) if [ "$BITRATE" = "500000" ]; then BITRATE="$1"
                       else DBITRATE="$1"; fi ;;
                esac
            else
                case "$1" in
                    *.*) SAMPLE_POINT="$1" ;;
                    *) BITRATE="$1" ;;
                esac
            fi
            shift
            ;;
    esac
done

echo "=== CAN 初始化 (${CHANNEL}) ==="
[ "$FD_MODE" = true ] && echo "[INFO] 模式: CAN FD (bitrate=${BITRATE}, dbitrate=${DBITRATE}, sp=${SAMPLE_POINT})" \
    || echo "[INFO] 模式: Classic CAN (bitrate=${BITRATE}, sp=${SAMPLE_POINT})"

# 1. 加载内核模块
for mod in can can_raw peak_usb; do
    if ! lsmod | grep -q "^${mod} "; then
        echo "[INFO] 加载 ${mod} 模块..."
        sudo modprobe ${mod} 2>/dev/null || { echo "[ERROR] 无法加载 ${mod} 模块"; exit 1; }
    fi
done
echo "[OK] CAN 内核模块已加载"

# 2. 检查接口
if ! ip link show ${CHANNEL} &>/dev/null; then
    echo "[ERROR] ${CHANNEL} 接口不存在，请检查 USB 连接"
    exit 1
fi

# 3. down → 配置 → up
sudo ip link set ${CHANNEL} down 2>/dev/null

if [ "$FD_MODE" = true ]; then
    sudo ip link set ${CHANNEL} type can bitrate ${BITRATE} dbitrate ${DBITRATE} fd on sample-point ${SAMPLE_POINT}
else
    sudo ip link set ${CHANNEL} type can bitrate ${BITRATE} sample-point ${SAMPLE_POINT}
fi

sudo ip link set ${CHANNEL} up

MODE_STR="bitrate=${BITRATE}"
[ "$FD_MODE" = true ] && MODE_STR="${MODE_STR}, dbitrate=${DBITRATE}, fd=on"
echo "[OK] ${CHANNEL} 已就绪 (${MODE_STR}, sp=${SAMPLE_POINT})"
ip -details link show ${CHANNEL} | grep -E 'state|bitrate|dbitrate|sample-point|FD' | sed 's/^/  /'
echo "=== 初始化完成 ==="
