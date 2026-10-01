# -*- coding: utf-8 -*-
"""sync 指令协议冒烟测试
安全前提：所有测试都保证 back 最终为 0 或负数（夹到 0），text 为空，
因此不会产生任何真实注入，不会污染前台窗口。
"""
import base64, hashlib, json, os, re, socket, struct, sys, urllib.request

HOST, PORT = "127.0.0.1", 8765
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 绕开环境代理

# 1) 从 /pair 抓实时配对码
html = opener.open("http://127.0.0.1:8765/pair", timeout=5).read().decode("utf-8")
m = re.search(r"code=(\d{4})", html)
if not m:
    print("FAIL: 配对码抓取失败")
    sys.exit(1)
code = m.group(1)
print("配对码:", code)

# 2) 手机页面是否已带同步功能
page = opener.open("http://127.0.0.1:8765/m", timeout=5).read().decode("utf-8")
checks = {
    "下拉控件 id=mode": 'id="mode"' in page,
    "下拉与发送同排": 'id="sendrow"' in page,
    "含 实时同步 选项": "实时同步" in page,
    "增量指令 sync": "'sync'" in page,
    "最长公共前缀 calcDiff": "calcDiff" in page,
    "输入法组合保护": "compositionstart" in page,
}
for k, v in checks.items():
    print("  %-24s %s" % (k, "OK" if v else "缺失"))

# 3) WS 握手
s = socket.create_connection((HOST, PORT), timeout=5)
key = base64.b64encode(os.urandom(16)).decode()
s.sendall((
    "GET /ws HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
    "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (HOST, PORT, key)
).encode())
buf = b""
while b"\r\n\r\n" not in buf:
    buf += s.recv(4096)
head = buf.split(b"\r\n\r\n")[0].decode(errors="ignore")
expect = base64.b64encode(
    hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
).decode()
print("握手:", "OK" if ("Sec-WebSocket-Accept: " + expect) in head else "FAIL")


def send_frame(payload: bytes):
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    n = len(payload)
    header = struct.pack("!BB", 0x81, 0x80 | n) if n < 126 else struct.pack("!BBH", 0x81, 0x80 | 126, n)
    s.sendall(header + mask + masked)


def recv_json():
    b = s.recv(2)
    if len(b) < 2:
        return None
    b1 = b[1]
    ln = b1 & 0x7F
    if ln == 126:
        ln = struct.unpack("!H", s.recv(2))[0]
    elif ln == 127:
        ln = struct.unpack("!Q", s.recv(8))[0]
    data = b""
    while len(data) < ln:
        chunk = s.recv(ln - len(data))
        if not chunk:
            break
        data += chunk
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


send_frame(json.dumps({"type": "hello", "code": code}).encode())
r = recv_json()
print("hello ->", r)

send_frame(json.dumps({"type": "sync", "back": 0, "text": ""}).encode())
r1 = recv_json()
print("sync(back=0, text='') ->", r1)

send_frame(json.dumps({"type": "sync", "back": -5, "text": ""}).encode())
r2 = recv_json()
print("sync(back=-5, text='') -> 负数应被夹到 0，无注入")
print("   ->", r2)

send_frame(json.dumps({"type": "ping"}).encode())
print("ping ->", recv_json())

ok = (r1 and r1.get("type") == "ack") and (r2 and r2.get("type") == "ack")
print()
print("[结论]", "sync 协议链路 OK（真实注入行为需手机实测）" if ok else "sync 协议异常")
s.close()
