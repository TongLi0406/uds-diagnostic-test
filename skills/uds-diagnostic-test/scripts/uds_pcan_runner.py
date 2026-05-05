#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UDS PCAN测试执行器
调用已生成的测试脚本，通过PCAN硬件执行测试并生成报告
也可作为独立编排工具：解析 → 生成 → 执行 一站式完成
"""

__version__ = "1.6.1"

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent


def _resolve_can_config(can_if, channel):
    """选择CAN接口和通道 (仅支持SocketCAN)"""
    can_if = "socketcan"
    if not channel or channel.upper().startswith("PCAN_"):
        channel = "can0"
    return can_if, channel


def _append_cli_arg(cmd, key, val):
    """按argparse语义追加CLI参数，避免把False/None错误转成字符串参数。"""
    if val is None:
        return

    flag = f"--{key.replace('_', '-')}"
    if isinstance(val, bool):
        if val:
            cmd.append(flag)
        return

    if isinstance(val, str) and val == "":
        return

    cmd.extend([flag, str(val)])


def _setup_socketcan_interface(channel, bitrate, sample_point=0.8, fd=False, dbitrate=2000000, dsample_point=0.0):
    """自动配置SocketCAN接口 (bitrate/sample-point/dbitrate/dsample-point从参数获取)"""
    import subprocess as _sp

    # 检查接口是否存在
    ret = _sp.run(["ip", "link", "show", channel], capture_output=True, text=True)
    if ret.returncode != 0:
        return  # 接口不存在

    is_up = "UP" in (ret.stdout.split("\n")[0] if ret.stdout else "")

    # 读取当前波特率和采样点
    current_bitrate = 0
    current_sp = 0.0
    det = _sp.run(["ip", "-details", "link", "show", channel], capture_output=True, text=True)
    if det.returncode == 0:
        for line in det.stdout.split("\n"):
            if "bitrate" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "bitrate" and i + 1 < len(parts):
                        try:
                            current_bitrate = int(parts[i + 1])
                        except ValueError:
                            pass
                    if p == "sample-point" and i + 1 < len(parts):
                        try:
                            current_sp = float(parts[i + 1])
                        except ValueError:
                            pass

    need_reconfig = (current_bitrate != bitrate)
    if sample_point > 0 and current_sp > 0 and abs(current_sp - sample_point) > 0.005:
        need_reconfig = True

    if is_up and not need_reconfig:
        sp_info = f", sample-point={current_sp}" if current_sp > 0 else ""
        print(f"[OK] SocketCAN {channel} 已启用且配置匹配 (bitrate={current_bitrate}{sp_info}), 直接使用")
        return  # 已正确配置，无需sudo

    # 总是先 down 再重新配置
    _sp.run(["sudo", "ip", "link", "set", channel, "down"], capture_output=True)

    if fd:
        cmd = ["sudo", "ip", "link", "set", channel, "type", "can",
               "bitrate", str(bitrate), "dbitrate", str(dbitrate), "fd", "on"]
    else:
        cmd = ["sudo", "ip", "link", "set", channel, "type", "can", "bitrate", str(bitrate)]
    if sample_point > 0:
        cmd.extend(["sample-point", f"{sample_point:.3f}"])
    if fd and dsample_point > 0:
        cmd.extend(["dsample-point", f"{dsample_point:.3f}"])
    print(f"[INFO] 自动配置SocketCAN: {' '.join(cmd)}")
    _sp.run(cmd, capture_output=True)

    _sp.run(["sudo", "ip", "link", "set", channel, "up"], capture_output=True)
    sp_info = f", sample-point={sample_point:.3f}" if sample_point > 0 else ""
    print(f"[OK] SocketCAN {channel} 已自动配置 (bitrate={bitrate}{sp_info})")


def run_parser(input_file, output_json):
    """运行诊断调查表解析器"""
    parser_script = SCRIPT_DIR / "uds_survey_parser.py"
    cmd = [
        sys.executable, str(parser_script),
        "--input", input_file,
        "--output", output_json,
    ]
    print(f"[INFO] 执行解析: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode == 0


def run_generator(input_json, output_script, **kwargs):
    """运行测试脚本生成器"""
    generator_script = SCRIPT_DIR / "uds_test_generator.py"
    cmd = [
        sys.executable, str(generator_script),
        "--input", input_json,
        "--output", output_script,
    ]
    for key, val in kwargs.items():
        _append_cli_arg(cmd, key, val)

    print(f"[INFO] 执行生成: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode == 0


def run_test_script(test_script, report_path, **kwargs):
    """执行生成的测试脚本"""
    cmd = [
        sys.executable, test_script,
        "--report", report_path,
    ]
    for key, val in kwargs.items():
        _append_cli_arg(cmd, key, val)

    print(f"[INFO] 执行测试: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode == 0


def pipeline(survey_file, output_dir, **kwargs):
    """
    完整流水线：解析 → 生成 → 执行 → 报告
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(output_dir, exist_ok=True)

    parsed_json = os.path.join(output_dir, f"parsed_{timestamp}.json")
    test_script = os.path.join(output_dir, f"test_uds_{timestamp}.py")
    report_path = os.path.join(output_dir, f"report_{timestamp}.md")
    can_log_arg = kwargs.get("can_log", "auto")
    if can_log_arg.lower() == "off":
        can_log_path = ""
    elif can_log_arg == "" or can_log_arg.lower() == "auto":
        can_log_path = os.path.join(output_dir, f"can_trace_{timestamp}.asc")
    else:
        can_log_path = can_log_arg

    print("=" * 60)
    print("UDS诊断测试 - 完整流水线")
    print(f"输入: {survey_file}")
    print(f"输出目录: {output_dir}")
    print("=" * 60)

    # Step 1: 解析
    print("\n[Step 1/3] 解析诊断调查表...")
    if not run_parser(survey_file, parsed_json):
        print("[ERROR] 解析失败")
        return False

    # 检查默认值使用情况
    with open(parsed_json, "r", encoding="utf-8") as f:
        parsed_data = json.load(f)

    if parsed_data.get("defaults_used"):
        print("\n" + "=" * 60)
        print("⚠ 以下属性使用了默认值，建议补充：")
        print("-" * 60)
        for item in parsed_data["defaults_used"]:
            ident = item.get("did") or item.get("io_did") or item.get("rid") or item.get("dtc") or "?"
            for attr, val in item.get("defaults", []):
                print(f"  {ident}: {attr} = {val}")
        print("=" * 60)

    # Step 2: 生成测试脚本
    print("\n[Step 2/3] 生成测试脚本...")
    gen_kwargs = {k: v for k, v in kwargs.items()
                  if k in ("channel", "can_if", "bitrate", "sample_point", "tx_id", "rx_id", "func_id",
                           "can_fd", "fd_data_bitrate", "fd_dsample_point",
                           "p2_timeout", "p2_star_timeout")}
    if not run_generator(parsed_json, test_script, **gen_kwargs):
        print("[ERROR] 生成失败")
        return False

    # Step 3: 执行测试
    print("\n[Step 3/3] 执行测试...")
    can_if_r, channel_r = _resolve_can_config("socketcan", kwargs.get("channel", ""))
    print(f"[INFO] CAN接口: {can_if_r}/{channel_r} (SocketCAN)")

    run_kwargs = {k: v for k, v in kwargs.items()
                  if k in ("channel", "can_if", "bitrate", "sample_point", "tx_id", "rx_id", "func_id",
                           "can_fd", "fd_data_bitrate", "fd_dsample_point")}
    run_kwargs["can_log"] = can_log_path
    if not run_test_script(test_script, report_path, **run_kwargs):
        print("[WARNING] 测试执行中可能有错误，请查看报告")

    print(f"\n[完成] 测试报告: {report_path}")
    if can_log_path:
        print(f"[完成] CAN通信日志: {can_log_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="UDS PCAN测试执行器")
    sub = parser.add_subparsers(dest="command", help="子命令")

    # parse子命令
    p_parse = sub.add_parser("parse", help="仅解析诊断调查表")
    p_parse.add_argument("--input", "-i", required=True, help="诊断调查表文件")
    p_parse.add_argument("--output", "-o", required=True, help="输出JSON")

    # generate子命令
    p_gen = sub.add_parser("generate", help="基于解析结果生成测试脚本")
    p_gen.add_argument("--input", "-i", required=True, help="解析后的JSON")
    p_gen.add_argument("--output", "-o", required=True, help="输出测试脚本")
    p_gen.add_argument("--channel", default="", help="CAN通道 (如can0)")
    p_gen.add_argument("--can-if", default="socketcan", choices=["socketcan"],
                        help="CAN接口类型 (仅支持socketcan)")
    p_gen.add_argument("--bitrate", type=int, default=None, help="显式覆盖CAN波特率；留空则使用调查表/默认值")
    p_gen.add_argument("--sample-point", type=float, default=None, help="显式覆盖CAN采样点 (0.0~1.0)")
    p_gen.add_argument("--can-fd", action="store_true", default=False, help="启用CAN FD模式")
    p_gen.add_argument("--fd-data-bitrate", type=int, default=None, help="显式覆盖CAN FD数据段波特率")
    p_gen.add_argument("--fd-dsample-point", type=float, default=None, help="显式覆盖CAN FD数据段采样点 (0.0~1.0)")
    p_gen.add_argument("--tx-id", default=None, help="显式覆盖发送CAN ID")
    p_gen.add_argument("--rx-id", default=None, help="显式覆盖接收CAN ID")

    # run子命令
    p_run = sub.add_parser("run", help="执行测试脚本")
    p_run.add_argument("--test-script", "-t", required=True, help="测试脚本路径")
    p_run.add_argument("--report", "-r", default="uds_test_report.md", help="报告输出路径")
    p_run.add_argument("--channel", default="", help="CAN通道")
    p_run.add_argument("--can-if", default="socketcan", choices=["socketcan"],
                        help="CAN接口类型 (仅支持socketcan)")
    p_run.add_argument("--bitrate", type=int, default=None, help="显式覆盖CAN波特率；留空则使用脚本内默认值")
    p_run.add_argument("--sample-point", type=float, default=None, help="显式覆盖CAN采样点 (0.0~1.0)")
    p_run.add_argument("--can-fd", action="store_true", default=False, help="启用CAN FD模式")
    p_run.add_argument("--fd-data-bitrate", type=int, default=None, help="显式覆盖CAN FD数据段波特率")
    p_run.add_argument("--fd-dsample-point", type=float, default=None, help="显式覆盖CAN FD数据段采样点 (0.0~1.0)")
    p_run.add_argument("--tx-id", default=None, help="显式覆盖发送CAN ID")
    p_run.add_argument("--rx-id", default=None, help="显式覆盖接收CAN ID")
    p_run.add_argument("--can-log", default="", help="CAN通信日志输出路径 (支持.asc/.blf格式, 留空则不记录)")

    # pipeline子命令
    p_pipe = sub.add_parser("pipeline", help="完整流水线：解析→生成→执行→报告")
    p_pipe.add_argument("--input", "-i", required=True, help="诊断调查表文件")
    p_pipe.add_argument("--output-dir", "-o", default="./uds_test_output", help="输出目录")
    p_pipe.add_argument("--channel", default="", help="CAN通道")
    p_pipe.add_argument("--can-if", default="socketcan", choices=["socketcan"],
                        help="CAN接口类型 (仅支持socketcan)")
    p_pipe.add_argument("--bitrate", type=int, default=None, help="显式覆盖CAN波特率；留空则使用调查表/默认值")
    p_pipe.add_argument("--sample-point", type=float, default=None, help="显式覆盖CAN采样点 (0.0~1.0)")
    p_pipe.add_argument("--can-fd", action="store_true", default=False, help="启用CAN FD模式")
    p_pipe.add_argument("--fd-data-bitrate", type=int, default=None, help="显式覆盖CAN FD数据段波特率")
    p_pipe.add_argument("--fd-dsample-point", type=float, default=None, help="显式覆盖CAN FD数据段采样点 (0.0~1.0)")
    p_pipe.add_argument("--can-log", default="auto", help="CAN通信日志: auto=自动生成.asc, off=不记录, 或指定路径")
    p_pipe.add_argument("--tx-id", default=None, help="显式覆盖发送CAN ID")
    p_pipe.add_argument("--rx-id", default=None, help="显式覆盖接收CAN ID")
    p_pipe.add_argument("--func-id", default=None, help="显式覆盖功能寻址CAN ID")

    args = parser.parse_args()

    if args.command == "parse":
        success = run_parser(args.input, args.output)
    elif args.command == "generate":
        can_if_val = getattr(args, 'can_if', 'socketcan')
        success = run_generator(args.input, args.output,
                                channel=args.channel, can_if=can_if_val,
                                bitrate=args.bitrate,
                                sample_point=args.sample_point,
                                can_fd=args.can_fd,
                                fd_data_bitrate=args.fd_data_bitrate,
                                fd_dsample_point=args.fd_dsample_point,
                                tx_id=args.tx_id, rx_id=args.rx_id)
    elif args.command == "run":
        can_if_val = getattr(args, 'can_if', 'socketcan')
        success = run_test_script(args.test_script, args.report,
                                  channel=args.channel, can_if=can_if_val,
                                  bitrate=args.bitrate,
                                  sample_point=args.sample_point,
                                  can_fd=args.can_fd,
                                  fd_data_bitrate=args.fd_data_bitrate,
                                  fd_dsample_point=args.fd_dsample_point,
                                  can_log=args.can_log,
                                  tx_id=args.tx_id, rx_id=args.rx_id)
    elif args.command == "pipeline":
        can_if_val = getattr(args, 'can_if', 'socketcan')
        success = pipeline(args.input, args.output_dir,
                           channel=args.channel, can_if=can_if_val,
                           bitrate=args.bitrate,
                           sample_point=args.sample_point,
                           can_fd=args.can_fd,
                           fd_data_bitrate=args.fd_data_bitrate,
                           fd_dsample_point=args.fd_dsample_point,
                           can_log=args.can_log,
                           tx_id=args.tx_id, rx_id=args.rx_id,
                           func_id=args.func_id)
    else:
        parser.print_help()
        success = True

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
