#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麒麟版服务层测试（本机 Windows 跑，不产生任何真实注入）

能测的：HTTP 路由、WS 握手与协议、配对、sync 的退格加注入逻辑、
        注入失败与无通道时的错误回传、配对页警示条替换。
不能测的：xdotool / dotool / ydotool / 剪贴板的真实注入 —— 这些只在 Linux 上有，
          必须等麒麟真机。所以本测试用假注入器顶替。

用假注入器还有个额外好处：能精确断言「服务端到底让注入器做了什么」，
这是真机做不到的（真机只能看屏幕上出来什么字）。
"""
import base64
import hashlib
import importlib.util
import json
import os
import re
import socket
import struct
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "kylin", "typebridge.py")

# ---- 加载模块（不执行 main）----
spec = importlib.util.spec_from_file_location("tblinux", SRC)
tb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tb)

# ---- 隔离配置与日志，别污染真实环境 ----
TMP = tempfile.mkdtemp(prefix="tblinux-test-")
tb.CONF_DIR = TMP
tb.CONF_FILE = os.path.join(TMP, "config.json")
tb.LOG_FILE = os.path.join(TMP, "log.txt")

LOGS = []
tb.Log.info = staticmethod(lambda msg: LOGS.append(str(msg)))

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", name, ("  " + extra) if extra else ""))


class FakeInjector(tb.Injector):
    """记录被要求做了什么，可选地模拟失败。"""
    name = "fake"

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def _boom(self):
        if self.fail:
            raise tb.InjectError("模拟的通道故障")

    def type_text(self, text):
        self._boom()
        self.calls.append(("type", text))

    def press(self, key, count=1):
        self._boom()
        self.calls.append(("press", key, count))

    def paste(self):
        self._boom()
        self.calls.append(("paste",))


class Ws(object):
    """极简 WS 客户端。"""

    def __init__(self, port):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.buf = b""
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            "GET /ws HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (port, key)
        ).encode())
        while b"\r\n\r\n" not in self.buf:
            self.buf += self.sock.recv(4096)
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        expect = base64.b64encode(
            hashlib.sha1((key + tb.GUID).encode()).digest()).decode()
        self.handshake_ok = ("Sec-WebSocket-Accept: " + expect) in head.decode(errors="ignore")

    def send(self, obj):
        payload = json.dumps(obj).encode("utf-8")
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        n = len(payload)
        if n < 126:
            header = struct.pack("!BB", 0x81, 0x80 | n)
        elif n < 65536:
            header = struct.pack("!BBH", 0x81, 0x80 | 126, n)
        else:
            header = struct.pack("!BBQ", 0x81, 0x80 | 127, n)
        self.sock.sendall(header + mask + masked)

    def _fill(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            self.buf += chunk

    def recv(self):
        self._fill(2)
        if len(self.buf) < 2:
            return None
        b1 = self.buf[1]
        ln = b1 & 0x7F
        off = 2
        if ln == 126:
            self._fill(4)
            ln = struct.unpack("!H", self.buf[2:4])[0]
            off = 4
        elif ln == 127:
            self._fill(10)
            ln = struct.unpack("!Q", self.buf[2:10])[0]
            off = 10
        self._fill(off + ln)
        data = self.buf[off:off + ln]
        self.buf = self.buf[off + ln:]
        if not data:
            return None
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            return None

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def start_server(port, injector):
    srv = tb.Server(port, injector)
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
            return srv
        except Exception:
            time.sleep(0.05)
    raise RuntimeError("服务未能在端口 %d 起来" % port)


def get(port, path):
    return OPENER.open("http://127.0.0.1:%d%s" % (port, path), timeout=5).read().decode("utf-8")


CODE = tb.Pairing.load_or_new()

# ============================================================
print()
print("场景 A  注入通道正常（假注入器）")
# ============================================================
PORT_A = 8801
fake = FakeInjector()
start_server(PORT_A, fake)

pair_html = get(PORT_A, "/pair")
check("/pair 返回 200 且含配对码", CODE in pair_html)
check("通道正常时配对页不显示警示条", "class=\"warn\"" not in pair_html)
check("配对页占位符已被替换掉（不残留 <!--WARN-->）", "<!--WARN-->" not in pair_html)
check("/m 手机页可取", "id=\"mode\"" in get(PORT_A, "/m"))
check("/qrcode.js 可取", "function qrcode" in get(PORT_A, "/qrcode.js").replace(" ", "") or "qrcode" in get(PORT_A, "/qrcode.js"))

ws = Ws(PORT_A)
check("WS 握手", ws.handshake_ok)

ws.send({"type": "hello", "code": "0000"})
r = ws.recv()
check("配对码错误时被拒", r is not None and r.get("type") == "error", str(r))
ws.close()

ws = Ws(PORT_A)
ws.send({"type": "hello", "code": CODE})
check("正确配对码返回 ready", ws.recv().get("type") == "ready")

ws.send({"type": "text", "text": "你好世界"})
r = ws.recv()
check("普通文本返回 ack", r.get("type") == "ack" and r.get("chars") == 4, str(r))
check("注入器收到原文", ("type", "你好世界") in fake.calls, str(fake.calls))

fake.calls = []
ws.send({"type": "sync", "back": 3, "text": "abc"})
r = ws.recv()
check("sync 返回 ack", r.get("type") == "ack", str(r))
check("sync 先退格再注入，顺序正确",
      fake.calls == [("press", "BackSpace", 3), ("type", "abc")], str(fake.calls))

fake.calls = []
ws.send({"type": "sync", "back": 0, "text": ""})
r = ws.recv()
check("空 sync 仍回 ack（手机端心跳依赖）", r.get("type") == "ack", str(r))
check("空 sync 不碰注入器", fake.calls == [], str(fake.calls))

fake.calls = []
ws.send({"type": "sync", "back": -5, "text": ""})
r = ws.recv()
check("负数退格被夹到 0，不产生退格", r.get("type") == "ack" and fake.calls == [], str(fake.calls))

fake.calls = []
ws.send({"type": "enter"})
check("enter 回 ack", ws.recv().get("type") == "ack")
check("enter 触发 Enter 按键", ("press", "Enter", 1) in fake.calls, str(fake.calls))

fake.calls = []
ws.send({"type": "text", "text": "x" * 10001})
r = ws.recv()
check("超长文本被拦下", r.get("type") == "error", str(r))
check("超长文本没有触达注入器", fake.calls == [], str(fake.calls))

ws.send({"type": "ping"})
check("ping 回 pong", ws.recv().get("type") == "pong")
ws.close()

# ============================================================
print()
print("场景 B  注入通道报错（模拟 xdotool 挂了）")
# ============================================================
PORT_B = 8802
bad = FakeInjector(fail=True)
start_server(PORT_B, bad)

ws = Ws(PORT_B)
ws.send({"type": "hello", "code": CODE})
check("仍能配对成功", ws.recv().get("type") == "ready")

ws.send({"type": "text", "text": "这条应该失败"})
r = ws.recv()
check("注入失败时回 error 而不是 ack", r.get("type") == "error", str(r))
check("错误信息带上了通道原因", "模拟的通道故障" in (r.get("msg") or ""), str(r))

ws.send({"type": "sync", "back": 2, "text": "y"})
r = ws.recv()
check("sync 注入失败也回 error", r.get("type") == "error", str(r))

ws.send({"type": "ping"})
check("注入失败后连接仍可用（不误踢）", ws.recv().get("type") == "pong")
ws.close()

# ============================================================
print()
print("场景 C  完全没有注入通道（麒麟上没装任何工具）")
# ============================================================
PORT_C = 8803
start_server(PORT_C, None)

pair_html = get(PORT_C, "/pair")
check("配对页显示警示条", "class=\"warn\"" in pair_html)
check("配对页不残留占位符", "<!--WARN-->" not in pair_html)
check("警示条里带排查命令", "--selfcheck" in pair_html)
check("二维码仍然照常生成（不影响扫码）", "qrcode(0, 'M')" in pair_html)

ws = Ws(PORT_C)
ws.send({"type": "hello", "code": CODE})
check("无通道时仍能配对", ws.recv().get("type") == "ready")

ws.send({"type": "text", "text": "没通道"})
r = ws.recv()
check("无通道时回 error（不是崩掉连接）", r.get("type") == "error", str(r))
check("错误信息有指导性", "注入通道" in (r.get("msg") or ""), str(r))

ws.send({"type": "ping"})
check("无通道时连接仍存活", ws.recv().get("type") == "pong")
ws.close()

# ============================================================
print()
print("场景 D  工具函数")
# ============================================================
# _split_lines：换行制表要单独出来交给按键
parts = tb._split_lines("第一行\n第二行\t尾")
check("_split_lines 把换行制表切出来",
      parts == ["第一行", "\n", "第二行", "\t", "尾"], str(parts))
check("_split_lines 空串安全", tb._split_lines("") == [], str(tb._split_lines("")))

# 通道选择：强制指定不存在的通道名要干净地失败
check("强制未知通道返回 None", tb.build_injector(force="不存在的通道") is None)
# 在 Windows 上所有 Linux 通道都不可用，自动选择应返回 None 且不炸
check("本机（无任何 Linux 工具）自动选择返回 None 且不抛异常", tb.build_injector() is None)
# ydotool 现在能被识别为已知通道（不再报「未知通道名」）
check("--channel ydotool 被识别为已知通道", tb.build_injector(force="ydotool") is None)
check("未知通道提示里列出了全部可选通道",
      any("未知通道名" in m and "ydotool" in m for m in LOGS), str(LOGS[-3:]))

# 通道优先级：Wayland 下 dotool 应排第一位
_order_seen = []
_orig_env = os.environ.get("XDG_SESSION_TYPE")
os.environ["XDG_SESSION_TYPE"] = "wayland"
_order_seen.append(tb.channel_order())
os.environ["XDG_SESSION_TYPE"] = "x11"
_order_seen.append(tb.channel_order())
if _orig_env is None:
    os.environ.pop("XDG_SESSION_TYPE", None)
else:
    os.environ["XDG_SESSION_TYPE"] = _orig_env
check("Wayland 下 dotool 优先", _order_seen[0][0] == "dotool", str(_order_seen[0]))
check("X11 下剪贴板优先（xdotool type 中文掉字，剪贴板整段粘贴最稳）",
      _order_seen[1][0] == "clipboard", str(_order_seen[1]))

# ---- xdotool 可用性：应该看「真能连上 X」，而不是环境变量写着什么 ----
_orig_which = tb.shutil.which
_orig_run = tb._run
_orig_display = os.environ.get("DISPLAY")

tb.shutil.which = lambda n: ("/usr/bin/xdotool" if n == "xdotool" else _orig_which(n))

# 先测 DISPLAY 缺失的情形：这时真该判不可用（xdotool 靠它找 X 服务器）
os.environ.pop("DISPLAY", None)
ok_d, why_d = tb.XdotoolInjector.available()
check("DISPLAY 为空时判为不可用", ok_d is False, str(why_d))
check("提示里说清了用户该怎么办", "桌面" in (why_d or ""), str(why_d))

# 补上 DISPLAY，模拟真机上的图形会话
os.environ["DISPLAY"] = ":0"
tb._run = lambda cmd, stdin_data=None, timeout=15: (1, b"", b"Error: Can't open display: ")
ok, why = tb.XdotoolInjector.available()
check("装了 xdotool 但连不上 X 时判为不可用", ok is False, str(why))
check("这种情况下自动选择不会选中它", tb.build_injector() is None)

tb._run = lambda cmd, stdin_data=None, timeout=15: (0, b"1920x1080", b"")
ok2, why2 = tb.XdotoolInjector.available()
check("能连上 X 就判为可用（不再盯着 XDG_SESSION_TYPE）", ok2 is True, str(why2))
_inj = tb.build_injector()
check("此时自动选择到 xdotool", _inj is not None and _inj.name == "xdotool", str(_inj))

# 环境变量不在 x11 但 X 连得上，仍然应该可用（麒麟上变量经常缺失）
os.environ["XDG_SESSION_TYPE"] = "wayland"
ok3, why3 = tb.XdotoolInjector.available()
check("会话变量是 wayland 但 X 连得上，xdotool 仍判可用", ok3 is True, str(why3))
# Wayland 下没装 dotool 时，应退到 xdotool，而不是直接跳到最弱的剪贴板方案
_inj2 = tb.build_injector()
check("Wayland 下没 dotool 时退到 xdotool（而非直接剪贴板）",
      _inj2 is not None and _inj2.name == "xdotool", str(_inj2))
if _orig_env is None:
    os.environ.pop("XDG_SESSION_TYPE", None)
else:
    os.environ["XDG_SESSION_TYPE"] = _orig_env
if _orig_display is None:
    os.environ.pop("DISPLAY", None)
else:
    os.environ["DISPLAY"] = _orig_display

tb.shutil.which, tb._run = _orig_which, _orig_run

# ============================================================
print()
print("场景 E  端口占用（重复启动的情形）")
# ============================================================
# 场景 A 的服务还占着 8801
check("port_in_use 认得出被占用的端口", tb.port_in_use(8801) is True)
check("port_in_use 对空闲端口返回 False", tb.port_in_use(8899) is False)

# 模拟「端口被占用」。让占位者故意不开 SO_REUSEADDR：
# Server 自己带着 SO_REUSEADDR，而这个选项在 Windows 上的含义是「允许抢绑」，
# 两个都开着它的 socket 在 Windows 上能同时绑住同一端口，根本测不出失败。
# 占位者不开，两个平台都会让 Server 的 bind 真的失败。
_blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
_blocker.bind(("0.0.0.0", 8806))
_blocker.listen(1)
blocked = tb.Server(8806, FakeInjector())
_tb2 = threading.Thread(target=blocked.serve_forever)
_tb2.daemon = True
_tb2.start()
time.sleep(0.5)
check("端口被占用时启动失败（不假装在跑）", blocked.failed is True)
check("失败实例不会置 ready", blocked.ready is False)
_blocker.close()

# 换个空闲端口就能正常起来
ok_srv = tb.Server(8805, FakeInjector())
_to = threading.Thread(target=ok_srv.serve_forever)
_to.daemon = True
_to.start()
time.sleep(0.5)
check("空闲端口能正常就绪", ok_srv.ready is True and ok_srv.failed is False)
check("新起来的服务真的能访问", CODE in get(8805, "/pair"))

# ============================================================
print()
print("=" * 56)
print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
if FAIL:
    print("失败项：")
    for f in FAIL:
        print("  - " + f)
print("=" * 56)
sys.exit(1 if FAIL else 0)
