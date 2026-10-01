"""TypeBridge WS 配对冒烟测试（纯标准库，不做任何注入）"""
import socket
import base64
import hashlib
import struct
import json
import os
import sys

HOST = "127.0.0.1"
PORT = 8765
MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_connect():
    s = socket.create_connection((HOST, PORT), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        "GET /ws HTTP/1.1\r\n"
        f"Host: {HOST}:{PORT}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    s.sendall(req.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = s.recv(4096)
        if not chunk:
            raise RuntimeError("握手无响应")
        resp += chunk
    head, _, rest = resp.partition(b"\r\n\r\n")
    head = head.decode("latin1")
    if "101" not in head.split("\r\n")[0]:
        raise RuntimeError("握手失败: " + head.split("\r\n")[0])
    expect = base64.b64encode(hashlib.sha1((key + MAGIC).encode()).digest()).decode()
    ok = expect in head
    return s, ok, rest


def send_text_frame(s, text):
    payload = text.encode("utf-8")
    mask = os.urandom(4)
    header = bytearray([0x81])
    n = len(payload)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", n)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", n)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    s.sendall(bytes(header) + mask + masked)


def recv_frame(s, leftover=b""):
    buf = leftover
    while len(buf) < 2:
        chunk = s.recv(4096)
        if not chunk:
            return None, b""
        buf += chunk
    b0, b1 = buf[0], buf[1]
    opcode = b0 & 0x0F
    ln = b1 & 0x7F
    idx = 2
    if ln == 126:
        while len(buf) < idx + 2:
            buf += s.recv(4096)
        ln = struct.unpack(">H", buf[idx:idx + 2])[0]
        idx += 2
    elif ln == 127:
        while len(buf) < idx + 8:
            buf += s.recv(4096)
        ln = struct.unpack(">Q", buf[idx:idx + 8])[0]
        idx += 8
    while len(buf) < idx + ln:
        chunk = s.recv(4096)
        if not chunk:
            return None, b""
        buf += chunk
    payload = buf[idx:idx + ln]
    return opcode, payload


def test(name, code_sent, expect):
    s, accept_ok, rest = ws_connect()
    assert accept_ok, "Sec-WebSocket-Accept 校验失败"
    send_text_frame(s, json.dumps({"type": "hello", "code": code_sent}))
    op, payload = recv_frame(s, rest)
    if payload is None:
        print(f"[{name}] 连接被服务端关闭(无应答帧)")
        result = "closed"
    else:
        msg = json.loads(payload.decode("utf-8"))
        print(f"[{name}] 收到: {msg}")
        result = msg.get("type")
    verdict = "OK" if result == expect else "FAIL"
    print(f"[{name}] 期望 {expect} -> {verdict}\n")
    try:
        s.close()
    except OSError:
        pass
    return result == expect


# 服务端配对码从 /pair 页面抓取
import urllib.request
import re

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
html = opener.open("http://127.0.0.1:8765/pair", timeout=5).read().decode("utf-8")
m = re.search(r"code=(\d+)", html)
real_code = m.group(1)
print(f"当前配对码: {real_code}\n")

ok1 = test("错码应拒绝", "9999" if real_code != "9999" else "0000", "error")
ok2 = test("对码应通过", real_code, "ready")

# 对码后测 ping/pong（不测 text，避免真实注入打字）
s, accept_ok, rest = ws_connect()
send_text_frame(s, json.dumps({"type": "hello", "code": real_code}))
op, payload = recv_frame(s, rest)
send_text_frame(s, json.dumps({"type": "ping"}))
op, payload = recv_frame(s)
msg = json.loads(payload.decode("utf-8"))
ok3 = msg.get("type") == "pong"
print(f"[ping-pong] 收到: {msg} -> {'OK' if ok3 else 'FAIL'}")
s.close()

print()
if ok1 and ok2 and ok3:
    print("[总结论] WS 配对链路冒烟测试全部通过")
    sys.exit(0)
print("[总结论] 存在失败项")
sys.exit(1)
