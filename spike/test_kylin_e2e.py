#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麒麟版端到端验证：真的把 airtype.py 当程序跑起来。

覆盖 main() 里的两条新路径：
  1) 一个注入通道都没有时，服务仍然要起得来，配对页要挂出警示条
  2) 重复启动时不能闷头再起一个，要认出已有实例并给出提示

本机是 Windows，跑不了 Linux 注入，但这两条路径跟注入通道无关，能完整验证。
"""
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "kylin", "airtype.py")
PY = sys.executable
PORT = 8807

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", name, ("  " + extra) if extra else ""))


env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"
env.pop("XDG_SESSION_TYPE", None)   # 本机没有图形会话，让自检按最差情况走

print()
print("第一个实例（本机没有任何 Linux 注入工具）")
p1 = subprocess.Popen([PY, SRC, "--port", str(PORT)],
                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                      text=True, encoding="utf-8", errors="replace", env=env)
time.sleep(3.0)

try:
    html = OPENER.open("http://127.0.0.1:%d/pair" % PORT, timeout=5).read().decode("utf-8")
    alive = True
except Exception as e:
    html, alive = "", False
    print("    （访问失败：%s）" % e)

check("没有注入通道时服务照样起得来", alive)
check("配对页挂出了警示条", 'class="warn"' in html)
check("警示条里给了排查命令", "--selfcheck" in html)
check("二维码功能没被影响", "qrcode(0, 'M')" in html)

print()
print("第二个实例（同端口，应识别出已有实例）")
try:
    p2 = subprocess.run([PY, SRC, "--port", str(PORT)],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", env=env, timeout=25)
    out2, rc2 = p2.stdout or "", p2.returncode
except subprocess.TimeoutExpired as e:
    p2 = None
    out2, rc2 = (e.stdout or ""), "超时"
    print("    第二个实例没有自己退出，说明它闷头又起了一个服务")

print("    退出码：%s" % rc2)
check("第二个实例正常退出（没有僵着）", rc2 == 0)
check("提示里说明了已有实例", "已经在跑" in out2 or "有人在监听" in out2, out2.strip().splitlines()[-1] if out2.strip() else "")
check("把配对页地址给了出来", "/pair" in out2)

# 收尾
p1.terminate()
try:
    p1.wait(timeout=5)
except Exception:
    p1.kill()

print()
print("=" * 56)
print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
for f in FAIL:
    print("  - " + f)
print("=" * 56)
sys.exit(1 if FAIL else 0)
