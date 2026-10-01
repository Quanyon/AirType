#!/usr/bin/env bash
# ============================================================
# TypeBridge 麒麟版 · 一键安装向导
#
# 目标用户：不会命令行的人。全程图形弹窗，只有"安装系统依赖"
# 那一步会弹一次管理员密码框。
#
# 用法（两种任选，全程自动，无需输入 y，只有补装依赖时要一次管理员密码）：
#   1. 双击运行：右键本文件 → 属性 → 权限 → 勾选"允许作为程序执行"
#      然后双击 → 选"运行"。
#   2. 终端运行：bash install.sh        （加 --ask 可恢复手动逐项确认）
#
# 会做四件事：
#   ① 检测这台机器的显示协议与注入工具（X11 / Wayland）
#   ② 用管理员权限补齐注入依赖（xdotool / wl-clipboard / xclip）
#   ③ 把程序装到用户目录（~/.local/share/typebridge，无需管理员）
#   ④ 创建桌面图标 + 开始菜单项 + 开机自启，并立即启动
#
# 说明：脚本要求 LF 换行、UTF-8 无 BOM。若在 Windows 上编辑过，
#       请用 dos2unix install.sh 转一下。
# ============================================================

set -u

# 安装模式：默认全程自动（所有"是否继续"都自动选"是"，不等待输入）。
# 只有补装系统依赖时会弹一次管理员密码框（pkexec / sudo）。
# 加 --ask 参数可恢复手动逐项确认。
AUTO=1

# 双击运行且没有图形弹窗组件（zenity 未装）时，自动用终端重新拉起自己，
# 避免"双击没反应"。若连终端也没有，继续纯文本模式（反正全程自动，不等待输入）。
if [ ! -t 0 ] && ! command -v zenity >/dev/null 2>&1 && [ -z "${TB_REEXEC:-}" ]; then
    for term in x-terminal-emulator gnome-terminal konsole xfce4-terminal mate-terminal; do
        if command -v "$term" >/dev/null 2>&1; then
            export TB_REEXEC=1
            "$term" -e bash "$0" "$@" >/dev/null 2>&1 &
            exit 0
        fi
    done
fi

APP_NAME="TypeBridge 跨屏输入"
INSTALL_DIR="$HOME/.local/share/typebridge"
ICON_DST="$INSTALL_DIR/icon.svg"
APPS_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$APPS_DIR/typebridge.desktop"
LOG="$INSTALL_DIR/install.log"

# 脚本所在目录（双击运行时 $0 可能是相对路径，先转成绝对路径）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_PY="$SCRIPT_DIR/typebridge.py"
SRC_WEB="$SCRIPT_DIR/web"
SRC_ICON="$SCRIPT_DIR/assets/typebridge-icon.svg"
[ -f "$SRC_ICON" ] || SRC_ICON="$SCRIPT_DIR/typebridge-icon.svg"

# 检测函数：会写全局变量 SESSION / MISSING / CAN_INSTALL
SESSION=""
MISSING=""
CAN_INSTALL=0

# ---------- 图形化封装（zenity 缺失时自动降级为纯文本） ----------

have_zenity() { command -v zenity >/dev/null 2>&1; }

msg() {
    # 信息提示框
    if have_zenity; then
        zenity --info --title="$APP_NAME 安装向导" --width=460 --text="$1"
    else
        echo "------------------------------------------"
        echo "$1"
        echo "------------------------------------------"
    fi
}

confirm() {
    # 是/否 确认框：$1 文本，$2 确定按钮文字，$3 取消按钮文字
    if [ "$AUTO" = "1" ]; then
        # 自动模式：不等待任何输入，一律按「$2」继续
        echo "[自动] $1 —— 自动继续（无需输入）"
        return 0
    fi
    if have_zenity; then
        zenity --question --title="$APP_NAME 安装向导" --width=460 \
            --text="$1" --ok-label="$2" --cancel-label="$3"
    else
        echo "$1"
        echo "输入 y 表示「$2」，回车继续；其它任意键表示「$3」"
        read -r REPLY
        [ "$REPLY" = "y" ] || [ "$REPLY" = "Y" ]
    fi
}

# 必须让用户本人拍板的询问：即使全程自动（AUTO=1）也弹窗，不自动跳过。
# 用于"开机自启"这类用户偏好，不能被默认值代替。
ask_real() {
    if have_zenity; then
        zenity --question --title="$APP_NAME 安装向导" --width=460 \
            --text="$1" --ok-label="$2" --cancel-label="$3"
    else
        echo "$1"
        echo "输入 y 表示「$2」，回车继续；其它任意键表示「$3」"
        read -r REPLY
        [ "$REPLY" = "y" ] || [ "$REPLY" = "Y" ]
    fi
}

fail_exit() {
    if have_zenity; then
        zenity --error --title="$APP_NAME 安装向导" --width=460 --text="$1"
    else
        echo "错误：$1"
    fi
    exit 1
}

# ---------- 第 ① 步：环境检测 ----------

detect_session() {
    SESSION="${XDG_SESSION_TYPE:-}"
    if [ -z "$SESSION" ] && command -v loginctl >/dev/null 2>&1; then
        SID=$(loginctl 2>/dev/null | awk -v u="$(whoami)" '$3==u {print $1; exit}')
        [ -n "$SID" ] && SESSION=$(loginctl show-session "$SID" -p Type 2>/dev/null | cut -d= -f2)
    fi
    case "$SESSION" in
        x11)   SESSION="X11" ;;
        wayland) SESSION="Wayland" ;;
        *)     SESSION="未知" ;;
    esac
}

detect_tools() {
    MISSING=""
    if [ "$SESSION" = "X11" ]; then
        command -v xdotool >/dev/null 2>&1 || MISSING="$MISSING xdotool"
        command -v xclip  >/dev/null 2>&1 || MISSING="$MISSING xclip"
    elif [ "$SESSION" = "Wayland" ]; then
        command -v wl-copy >/dev/null 2>&1 || MISSING="$MISSING wl-clipboard"
    else
        command -v xdotool >/dev/null 2>&1 || MISSING="$MISSING xdotool"
        command -v wl-copy >/dev/null 2>&1 || MISSING="$MISSING wl-clipboard"
    fi
    CAN_INSTALL=0
    command -v apt-get >/dev/null 2>&1 && CAN_INSTALL=1
    # 图形弹窗组件缺失会让安装器只能走文字模式（双击无反应），一并检测
    command -v zenity >/dev/null 2>&1 || MISSING="$MISSING zenity"
}

# ---------- 第 ② 步：安装系统依赖 ----------

install_deps() {
    local pkgs=""
    if [ "$SESSION" = "X11" ]; then
        command -v xdotool >/dev/null 2>&1 || pkgs="$pkgs xdotool"
        command -v xclip  >/dev/null 2>&1 || pkgs="$pkgs xclip"
    elif [ "$SESSION" = "Wayland" ]; then
        command -v wl-copy >/dev/null 2>&1 || pkgs="$pkgs wl-clipboard"
    else
        command -v xdotool >/dev/null 2>&1 || pkgs="$pkgs xdotool"
        command -v wl-copy >/dev/null 2>&1 || pkgs="$pkgs wl-clipboard"
        command -v xclip  >/dev/null 2>&1 || pkgs="$pkgs xclip"
    fi
    # 图形弹窗组件（zenity）缺失时一并补装，让安装器以后能弹窗
    command -v zenity >/dev/null 2>&1 || pkgs="$pkgs zenity"
    if [ -z "$pkgs" ]; then
        return 0
    fi

    msg "需要管理员权限安装这些依赖（会弹一次密码框）：$pkgs\n\n安装过程中请不要关闭窗口。若弹出密码框，输入这台电脑的管理员密码即可。"
    if ! have_zenity; then
        echo "即将执行：pkexec /usr/bin/apt-get install -y $pkgs"
    fi

    mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
    # pkexec 会弹出图形化授权框；apt 输出写入日志，装完再统一提示
    if command -v pkexec >/dev/null 2>&1; then
        pkexec /usr/bin/apt-get install -y $pkgs >>"$LOG" 2>&1
    else
        sudo /usr/bin/apt-get install -y $pkgs >>"$LOG" 2>&1
    fi
    local rc=$?

    if [ $rc -eq 0 ]; then
        msg "依赖安装完成 ✅"
        return 0
    fi

    # 安装失败（常见：没网 / 软件源不可用 / 授权被拒）
    local hint=""
    if [ "$SESSION" = "X11" ]; then
        hint="装不上 xdotool 也能先装好 TypeBridge 试试看，必要时改用剪贴板方案（装 xclip）。"
    else
        hint="装不上 wl-clipboard 的话，剪贴板方案也跑不了。可以检查这台电脑的网络/软件源后重装。"
    fi
    if confirm "依赖没装上（可能是没网、软件源不可用或密码没输对）。\n\n$hint\n\n是否继续安装 TypeBridge 本体？\n（程序会先装上，等依赖就绪后再用）" "继续安装" "退出"; then
        return 1
    fi
    fail_exit "安装已取消。想重试时再运行 install.sh 即可。"
}

# ---------- 第 ③ 步：安装程序本体（用户目录，免管理员） ----------

install_app() {
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$APPS_DIR"

    # 拷贝主程序
    if [ ! -f "$SRC_PY" ]; then
        fail_exit "找不到 typebridge.py。请把整个 kylin 文件夹一起拷到这台电脑，再运行安装向导。"
    fi
    cp "$SRC_PY" "$INSTALL_DIR/typebridge.py" || fail_exit "写入 $INSTALL_DIR 失败，请检查磁盘空间或权限。"
    chmod +x "$INSTALL_DIR/typebridge.py"

    # 拷贝手机端网页（程序依赖同目录 web/）
    if [ -d "$SRC_WEB" ]; then
        rm -rf "$INSTALL_DIR/web"
        cp -r "$SRC_WEB" "$INSTALL_DIR/web"
    fi

    # 拷贝图标
    if [ -f "$SRC_ICON" ]; then
        cp "$SRC_ICON" "$ICON_DST"
    else
        # 兜底：没有图标文件时生成一个最小占位图标
        printf '%s' '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" rx="24" fill="#07C160"/><text x="64" y="82" font-size="52" fill="#fff" text-anchor="middle" font-family="sans-serif">T</text></svg>' > "$ICON_DST"
    fi

    # 一并拷入安装器本体，供以后自检/修复复用
    cp "$0" "$INSTALL_DIR/install.sh" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/install.sh" 2>/dev/null || true
}

# ---------- 第 ④ 步：桌面图标 / 开始菜单 / 开机自启 ----------

write_desktop_entry() {
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=TypeBridge 跨屏输入
Comment=手机扫码，电脑出字
Exec=python3 $INSTALL_DIR/typebridge.py --open-browser
Icon=$ICON_DST
Terminal=false
Categories=Utility;
StartupNotify=false
EOF
    chmod +x "$DESKTOP_FILE" 2>/dev/null || true
    # 修复入口：以后遇到"通道未就绪"双击它，先补装依赖再自检。
    # Terminal=true：没装 zenity 的机器双击也能弹出终端窗口走文字向导。
    cat > "$APPS_DIR/typebridge-fix.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=TypeBridge 环境修复
Comment=检查并修复文本注入通道
Exec=bash $INSTALL_DIR/install.sh --fix-deps --check
Icon=$ICON_DST
Terminal=true
Categories=Utility;
StartupNotify=false
EOF
    chmod +x "$APPS_DIR/typebridge-fix.desktop" 2>/dev/null || true
    # 稳定模式入口：xdotool 逐字打字在部分机器上会丢字，
    # 剪贴板方案整段粘贴 100% 不丢字，只是会覆盖剪贴板。
    cat > "$APPS_DIR/typebridge-stable.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=TypeBridge 稳定模式
Comment=剪贴板粘贴不丢字（需已装 xclip / wl-clipboard）
Exec=python3 $INSTALL_DIR/typebridge.py --open-browser --channel clipboard
Icon=$ICON_DST
Terminal=false
Categories=Utility;
StartupNotify=false
EOF
    chmod +x "$APPS_DIR/typebridge-stable.desktop" 2>/dev/null || true
    # 刷新开始菜单缓存（存在才执行）
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
    fi
}

make_desktop_shortcut() {
    # 桌面目录：中文环境叫「桌面」，英文叫 Desktop，两个都探测
    local desktop_dir=""
    for d in "$HOME/桌面" "$HOME/Desktop"; do
        if [ -d "$d" ]; then desktop_dir="$d"; break; fi
    done
    [ -z "$desktop_dir" ] && return 0

    if confirm "是否在桌面放一个「TypeBridge」图标？\n（以后双击它就能弹出配对二维码）" "放一个" "不用了"; then
        cp "$DESKTOP_FILE" "$desktop_dir/TypeBridge.desktop"
        chmod +x "$desktop_dir/TypeBridge.desktop" 2>/dev/null || true
        # 标记为可信图标，避免双击时反复询问
        if command -v gio >/dev/null 2>&1; then
            gio set "$desktop_dir/TypeBridge.desktop" metadata::trusted true 2>/dev/null || true
        fi
    fi
}

install_autostart() {
    # 复用主程序自带的 XDG autostart 能力
    python3 "$INSTALL_DIR/typebridge.py" --install-autostart >>"$LOG" 2>&1
}

# ---------- 自检 / 修复入口（给已经装完、但遇到问题的用户） ----------

run_check() {
    # 图形化显示环境自检结果（复用主程序 --selfcheck）
    if ! command -v python3 >/dev/null 2>&1; then
        fail_exit "没找到 python3（麒麟 V10 桌面版一般自带）。"
    fi
    local py="$INSTALL_DIR/typebridge.py"
    [ -f "$py" ] || py="$SCRIPT_DIR/typebridge.py"
    if [ ! -f "$py" ]; then
        fail_exit "找不到 typebridge.py，请重新安装。"
    fi
    local out
    out=$(python3 "$py" --selfcheck 2>&1)
    if have_zenity; then
        zenity --text-info --title="TypeBridge 环境自检结果" --width=680 --height=480 \
            --font="Monospace 12" --ok-label="关闭" <<<"$out"
    else
        echo "$out"
    fi
}

fix_deps() {
    # 只做依赖检测与补装，不重装程序本体
    detect_session
    detect_tools
    if [ -z "$MISSING" ]; then
        msg "注入依赖已齐全（$SESSION），无需安装。\n\n如果仍提示通道未就绪，请点「环境自检」查看具体原因。"
        return 0
    fi
    if [ $CAN_INSTALL -eq 1 ]; then
        if confirm "检测到缺少：$MISSING\n\n现在用管理员权限补装（会弹一次密码框）。" "去安装" "跳过"; then
            install_deps
            detect_tools
        fi
    else
        msg "缺少：$MISSING，但这台电脑上没有 apt 包管理器，无法自动补装。\n\n请把自检结果截图发给技术人员。"
    fi
}

launch_now() {
    if confirm "全部装好了！现在立即启动 TypeBridge 吗？\n（会弹出配对二维码，手机扫码即可开始）" "立即启动" "稍后自己开"; then
        nohup python3 "$INSTALL_DIR/typebridge.py" --open-browser >>"$LOG" 2>&1 &
        disown 2>/dev/null || true
        msg "已启动。手机和电脑连同一个 WiFi，用手机浏览器扫电脑上弹出的二维码即可。\n\n以后使用：双击桌面（或开始菜单里的）「TypeBridge」图标。"
    else
        msg "安装完成。使用时双击桌面或开始菜单里的「TypeBridge 图标」即可。"
    fi
}

# ============================================================
# 主流程
# ============================================================

main() {
    # 参数入口：--check 只做自检；--fix-deps 只补装依赖（可组合 --check）；
    #           --ask 恢复手动逐项确认（默认全程自动）
    local arg_check=0
    local arg_fix=0
    for a in "$@"; do
        case "$a" in
            --ask)   AUTO=0 ;;
            --check) arg_check=1 ;;
            --fix-deps) arg_fix=1 ;;
        esac
    done
    if [ $arg_check -eq 1 ]; then
        run_check
        return 0
    fi
    if [ $arg_fix -eq 1 ]; then
        fix_deps
        if [ $arg_check -eq 1 ]; then
            run_check
        fi
        return 0
    fi

    echo "TypeBridge 麒麟版 一键安装向导（全程自动模式）"

    # 欢迎页（自动模式直接开始）
    if ! confirm "欢迎使用 TypeBridge 跨屏输入工具！\n\n功能：手机打字/语音 → 电脑光标处直接出字，不用传文件。\n\n安装向导会：\n  ① 检测这台电脑的环境\n  ② 安装所需依赖（会要一次管理员密码）\n  ③ 安装 TypeBridge 并创建桌面图标\n\n现在开始吗？" "开始安装" "退出"; then
        exit 0
    fi

    # ① 环境检测
    detect_session
    detect_tools

    local det="显示协议：$SESSION"
    if [ "$SESSION" = "X11" ]; then
        det="$det\n说明：X11 会话，可以用 xdotool 直接键入，体验最好。"
    elif [ "$SESSION" = "Wayland" ]; then
        det="$det\n说明：Wayland 会话，走剪贴板方案（中文写入剪贴板再模拟粘贴），同样能用。"
    else
        det="$det\n说明：未能自动判定会话类型。安装向导会同时尝试补齐两套依赖。"
    fi
    if [ -n "$MISSING" ]; then
        det="$det\n\n缺少的依赖：$MISSING"
    else
        det="$det\n\n注入依赖已齐全，无需额外安装。"
    fi
    msg "$det"

    # ② 安装依赖（用户可跳过）
    if [ -n "$MISSING" ]; then
        if [ $CAN_INSTALL -eq 1 ]; then
            if confirm "检测到缺少：$MISSING\n\n需要管理员权限安装（会弹一次密码框）。\n\n装不上也不影响先装好程序本体，随时可以跳过。" "去安装" "跳过"; then
                install_deps
                # 装完重新检测一次
                detect_tools
            fi
        else
            if ! confirm "检测到缺少：$MISSING\n\n这台电脑上没找到 apt 包管理器（可能不是麒麟桌面版，或环境受限）。\n\n是否仍继续安装程序本体？" "继续" "退出"; then
                exit 0
            fi
        fi
    fi

    # ③ 安装本体
    if ! command -v python3 >/dev/null 2>&1; then
        fail_exit "没找到 python3（麒麟 V10 桌面版一般自带）。请先安装 python3 后再运行安装向导。"
    fi
    install_app

    # ④ 桌面图标 + 开始菜单 + 自启
    write_desktop_entry
    make_desktop_shortcut

    # 开机自启必须让用户本人选一次（即使全程自动也弹窗），选否就不装
    local autostart_note
    if ask_real "是否开机自动启动 TypeBridge？\n\n开启后，每次开机自动在后台待命，手机扫码就能用。\n\n推荐开启。" "开机自启（推荐）" "不需要"; then
        install_autostart
        autostart_note="· 开机自启已开启（下次开机自动运行）"
    else
        autostart_note="· 开机自启未开启（以后想要可重新运行安装向导）"
    fi

    # 完成并启动
    local done="✅ 安装完成！\n\n· 程序目录：$INSTALL_DIR\n· 开始菜单已添加「TypeBridge」\n$autostart_note\n\n卸载方法：开始菜单搜索 TypeBridge 相关内容，或运行 python3 $INSTALL_DIR/typebridge.py --uninstall-autostart 后删除 $INSTALL_DIR 文件夹。"
    msg "$done"

    launch_now
}

main "$@"
