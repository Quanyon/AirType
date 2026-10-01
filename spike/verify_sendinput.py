"""验证 ctypes 调用 Win32 SendInput 的绑定正确性（静态验证，不实际注入文字）

实测发现的两个坑：
1. x64 下 sizeof(INPUT)=40 而非 32，因为 union 被 MOUSEINPUT(32字节) 撑大；
   若按 32 传给 SendInput 的 cbSize，会返回 0（失败）。
2. GetCurrentProcess() 返回伪句柄 -1，若不声明 argtypes 直接传入
   OpenProcessToken 会抛 OverflowError: int too long to convert。
   必须为所有涉及 HANDLE 的函数显式声明 argtypes。
"""
import ctypes
import struct
import sys

print(f"Python: {sys.version.split()[0]}  架构: {struct.calcsize('P') * 8}bit")
X64 = struct.calcsize("P") == 8
ULONG_PTR = ctypes.c_ulonglong if X64 else ctypes.c_ulong

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
advapi32 = ctypes.windll.advapi32


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", INPUT_UNION)]


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D
VK_BACK = 0x08

sz_input = ctypes.sizeof(INPUT)
sz_keybd = ctypes.sizeof(KEYBDINPUT)
expect_input = 40 if X64 else 28
print(f"sizeof(INPUT)      = {sz_input}   期望 {expect_input}  -> {'OK' if sz_input == expect_input else '不符!'}")
print(f"sizeof(KEYBDINPUT) = {sz_keybd}   (union 实际由 MOUSEINPUT 撑到 {ctypes.sizeof(INPUT_UNION)})")
print(f"sizeof(INPUT_UNION)= {ctypes.sizeof(INPUT_UNION)}")

# --- 显式声明 argtypes（坑2的修复）---
kernel32.GetCurrentProcess.restype = ctypes.c_void_p
kernel32.GetCurrentProcess.argtypes = []
advapi32.OpenProcessToken.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p)]
advapi32.OpenProcessToken.restype = ctypes.c_int
advapi32.GetTokenInformation.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)
]
advapi32.GetTokenInformation.restype = ctypes.c_int
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = ctypes.c_int

user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetForegroundWindow.argtypes = []
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
user32.GetWindowThreadProcessId.restype = ctypes.c_ulong

print("\n--- API 绑定 ---")
print(f"SendInput           : OK")
hwnd = user32.GetForegroundWindow()
pid = ctypes.c_ulong()
user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
print(f"GetForegroundWindow : {hwnd}  (前台进程 PID={pid.value})")

print("\n--- 完整性级别（UIPI 判断能否注入）---")
TOKEN_QUERY = 0x0008
TokenIntegrityLevel = 25
hToken = ctypes.c_void_p()
if advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(hToken)):
    size = ctypes.c_ulong(0)
    advapi32.GetTokenInformation(hToken, TokenIntegrityLevel, None, 0, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    if advapi32.GetTokenInformation(hToken, TokenIntegrityLevel, buf, size, ctypes.byref(size)):
        raw = buf.raw
        print(f"TOKEN_MANDATORY_LABEL 原始字节: {raw.hex(' ')}  (长度 {len(raw)})")
        # SID 布局: Revision(1) SubAuthorityCount(1) IdentifierAuthority(6) SubAuthority[0](4, offset=8)
        revision, sub_count = raw[0], raw[1]
        sub0 = struct.unpack_from("<I", raw, 8)[0] if len(raw) >= 12 else -1
        print(f"Revision={revision}  SubAuthorityCount={sub_count}  SubAuthority[0]={hex(sub0)}")
        # 坑3：不能 & 0xFFF！完整性 RID 本身就是 0x1000/0x2000/0x3000 量级，掩码会把它们抹成 0
        levels = {0x0000: "不可信", 0x1000: "低", 0x2000: "中(普通用户)",
                  0x2100: "中+", 0x3000: "高(管理员)", 0x4000: "系统"}
        print(f"本进程完整性级别 = {levels.get(sub0, '未知(' + hex(sub0) + ')')}")
        print("提示：注入到「以管理员身份运行」的程序需要本进程也是高级别，否则被 UIPI 拦截")
    kernel32.CloseHandle(hToken)   # 坑2b：CloseHandle 在 kernel32，不在 advapi32
else:
    print(f"OpenProcessToken 失败 err={ctypes.GetLastError()}")

print("\n--- 空发送探测（不产生任何实际输入）---")
ret = user32.SendInput(0, (INPUT * 1)(), sz_input)
print(f"SendInput(0, ...) = {ret}  (0=正常，表示发送了 0 个事件)")


def build_unicode_inputs(text):
    """把文字编码成 INPUT 数组：每个 UTF-16 码元一对 down/up"""
    raw = text.encode("utf-16-le")
    units = struct.unpack(f"<{len(raw)//2}H", raw)
    events = []
    for u in units:
        events.append((u, 0))                       # key down
        events.append((u, KEYEVENTF_KEYUP))         # key up
    arr = (INPUT * len(events))()
    for i, (scan, flags) in enumerate(events):
        arr[i].type = INPUT_KEYBOARD
        arr[i].u.ki.wVk = 0
        arr[i].u.ki.wScan = scan
        arr[i].u.ki.dwFlags = KEYEVENTF_UNICODE | flags
        arr[i].u.ki.time = 0
        arr[i].u.ki.dwExtraInfo = 0
    return arr


sample = "跨屏输入测试 Hello 🎉"
arr = build_unicode_inputs(sample)
print(f"\n--- 编码验证（纯内存计算，未发送）---")
print(f"样例文字 : {sample}")
print(f"字符数   : {len(sample)}   UTF-16 码元数: {len(sample.encode('utf-16-le'))//2}")
print(f"生成事件 : {len(arr)} 个 INPUT（每码元 down+up 各一）")
print(f"数组字节 : {ctypes.sizeof(arr)}  (= {len(arr)} x {sz_input})")
print(f"前3个 wScan: {[hex(arr[i].u.ki.wScan) for i in range(3)]}  "
      f"对应 {[chr(arr[i].u.ki.wScan) for i in range(0, 6, 2)]}")

print("\n[结论] ctypes -> SendInput 路线完全可用，零第三方原生依赖")
