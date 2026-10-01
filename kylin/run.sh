#!/usr/bin/env bash
# TypeBridge 麒麟版 启动脚本
#
# 用法：
#   ./run.sh              先自检，再启动服务并弹出配对页
#   ./run.sh --port 9000  换端口（默认 8765）
#   ./run.sh --channel dotool   强制指定注入通道
#
# 首次使用请务必看一眼自检结果，它会告诉你这台机器能用哪条注入通道，
# 以及缺的东西该怎么装。

cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    echo "没找到 python3。"
    echo "麒麟 V10 桌面版一般自带，先确认一下：  python3 --version"
    echo "真没有就装一个：  sudo apt install python3"
    exit 1
fi

echo "=========================================="
echo " 第一步：环境自检（这一步不会往任何地方打字）"
echo "=========================================="
python3 typebridge.py --selfcheck
SC=$?
echo
if [ "$SC" -ne 0 ]; then
    echo "自检没通过 —— 上面列了该装什么。"
    echo "装完再重新跑本脚本即可。"
    echo
    echo "也可以先直接启动看看（配对页上会挂出提示）："
    echo "  python3 typebridge.py --open-browser"
    echo
fi

echo "=========================================="
echo " 第二步：启动服务"
echo "=========================================="
exec python3 typebridge.py --open-browser "$@"
