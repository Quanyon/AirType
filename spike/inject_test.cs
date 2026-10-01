// ============================================================
// AirType 阶段0验证程序 v2 —— SendInput 注入内核测试
// v2 改版原因：v1 的"倒计时抢窗口"方式对人不友好，且无防呆，
//   有用户误对 WorkBuddy(聊天类应用)注入导致其卡死。
// v2 核心改进：
//   1. 窗口选择器：列出当前打开的窗口，输编号直接选定，无需抢时间
//   2. 注入前强制校验前台窗口，目标不对立即取消（防打错地方）
//   3. 启动即强警告：禁止对微信/QQ/WorkBuddy 等聊天软件测试
// 语法：C# 5（系统自带 csc.exe 编译，禁用 C#6+ 语法）
// 编译：build\build_stage0.bat
// 运行：build\inject_test.exe             （交互式实测）
//       build\inject_test.exe --selfcheck （无害自检，不注入）
// ============================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

static class InjectTest
{
    // ---------------- Win32 P/Invoke ----------------
    // 坑1(方案9.3)：x64 下 sizeof(INPUT)=40（union 被 MOUSEINPUT 撑大），
    //               绝不能手写死，必须 Marshal.SizeOf 动态取。
    [StructLayout(LayoutKind.Sequential)]
    private struct KEYBDINPUT
    {
        public ushort wVk;
        public ushort wScan;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MOUSEINPUT
    {
        public int dx;
        public int dy;
        public uint mouseData;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct HARDWAREINPUT
    {
        public uint uMsg;
        public ushort wParamL;
        public ushort wParamH;
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct INPUTUNION
    {
        [FieldOffset(0)] public MOUSEINPUT mi;
        [FieldOffset(0)] public KEYBDINPUT ki;
        [FieldOffset(0)] public HARDWAREINPUT hi;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct INPUT
    {
        public uint type;
        public INPUTUNION u;
    }

    private const uint INPUT_KEYBOARD = 1;
    private const uint KEYEVENTF_KEYUP = 0x0002;
    private const uint KEYEVENTF_UNICODE = 0x0004;
    private const ushort VK_RETURN = 0x0D;
    private const ushort VK_BACK = 0x08;

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    private static extern bool IsWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern void SwitchToThisWindow(IntPtr hWnd, bool altTab);

    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern int GetWindowLong(IntPtr hWnd, int nIndex);

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetConsoleWindow();

    private const int GWL_EXSTYLE = -20;
    private const int WS_EX_TOOLWINDOW = 0x80;

    private static readonly int SizeOfInput = Marshal.SizeOf(typeof(INPUT));

    // ---------------- 窗口选择器（v2 新增） ----------------
    private class WindowInfo
    {
        public IntPtr Hwnd;
        public string Title;
        public string Process;
    }

    private static List<WindowInfo> ListUserWindows()
    {
        List<WindowInfo> result = new List<WindowInfo>();
        IntPtr console = GetConsoleWindow();
        EnumWindows(delegate(IntPtr hWnd, IntPtr lParam)
        {
            if (!IsWindowVisible(hWnd)) return true;
            if (hWnd == console) return true;                       // 排除自己这个黑窗口
            if ((GetWindowLong(hWnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW) != 0) return true;
            if (GetWindowTextLength(hWnd) == 0) return true;
            uint pid;
            GetWindowThreadProcessId(hWnd, out pid);
            string proc = "unknown";
            try { proc = Process.GetProcessById((int)pid).ProcessName; }
            catch (Exception) { }
            StringBuilder sb = new StringBuilder(256);
            GetWindowText(hWnd, sb, 256);
            WindowInfo wi = new WindowInfo();
            wi.Hwnd = hWnd;
            wi.Title = sb.ToString();
            wi.Process = proc;
            result.Add(wi);
            return true;
        }, IntPtr.Zero);
        return result;
    }

    private static IntPtr targetHwnd = IntPtr.Zero;
    private static string targetName = "";

    private static void PickWindow()
    {
        List<WindowInfo> wins = ListUserWindows();
        Console.WriteLine();
        Console.WriteLine("--- 当前打开的窗口（输入编号选定注入目标）---");
        for (int i = 0; i < wins.Count; i++)
        {
            string mark = (wins[i].Hwnd == targetHwnd) ? " <-当前目标" : "";
            Console.WriteLine(string.Format("  [{0}] {1} | {2}{3}", i + 1, wins[i].Process, wins[i].Title, mark));
        }
        Console.Write("目标编号(回车取消): ");
        string line = Console.ReadLine();
        if (line == null || line.Trim().Length == 0) { Console.WriteLine("  已取消"); return; }
        int n;
        if (!int.TryParse(line.Trim(), out n) || n < 1 || n > wins.Count)
        {
            Console.WriteLine("  编号无效"); return;
        }
        targetHwnd = wins[n - 1].Hwnd;
        targetName = string.Format("{0} | {1}", wins[n - 1].Process, wins[n - 1].Title);
        Console.WriteLine(string.Format("  已选定目标: {0}", targetName));
        if (IsChatLike(wins[n - 1].Process, wins[n - 1].Title))
        {
            Console.WriteLine();
            Console.WriteLine("  !!! 警告: 这看起来是聊天/办公类软件 !!!");
            Console.WriteLine("  !!! 对它注入可能导致: 误发消息 / 程序卡死 !!!");
            Console.WriteLine("  !!! 强烈建议改用记事本(notepad)。仍要继续请自担风险 !!!");
        }
    }

    // 粗筛聊天/办公类进程名，给出醒目警告
    private static bool IsChatLike(string proc, string title)
    {
        string[] risky = new string[] {
            "wechat", "weixin", "qq", "dingtalk", "feishu", "lark",
            "wework", "teams", "slack", "telegram", "workbuddy", "workbuddy" };
        string p = proc.ToLower();
        for (int i = 0; i < risky.Length; i++)
        {
            if (p.Contains(risky[i])) return true;
        }
        return false;
    }

    // 注入前防呆：目标窗口还活着，且确实是前台。不满足立即取消。
    private static bool EnsureTargetReady()
    {
        if (targetHwnd == IntPtr.Zero)
        {
            Console.WriteLine("  [拦截] 还没选目标窗口。请先选 8 重新选窗口。");
            return false;
        }
        if (!IsWindow(targetHwnd))
        {
            Console.WriteLine("  [拦截] 目标窗口已关闭，请重新选窗口(按 8)。");
            targetHwnd = IntPtr.Zero;
            return false;
        }
        SwitchToThisWindow(targetHwnd, true);
        Thread.Sleep(300);
        IntPtr fg = GetForegroundWindow();
        if (fg != targetHwnd)
        {
            Console.WriteLine("  [拦截] 未能把目标切到前台(当前前台不是所选窗口)，已取消注入。");
            Console.WriteLine("         这是为了防止文字打错地方。请把目标窗口调出来后重试(按 8 重选)。");
            return false;
        }
        return true;
    }

    // ---------------- 注入引擎（与正式版 AirType 同源） ----------------

    // 把文字编码成 INPUT 数组：每个 UTF-16 码元一对 down/up（emoji 走代理对自动拆分）
    private static INPUT[] BuildTextInputs(string text)
    {
        byte[] raw = Encoding.Unicode.GetBytes(text);   // UTF-16 LE
        int units = raw.Length / 2;
        INPUT[] inputs = new INPUT[units * 2];
        int idx = 0;
        for (int i = 0; i < units; i++)
        {
            ushort code = (ushort)(raw[i * 2] | (raw[i * 2 + 1] << 8));
            for (int phase = 0; phase < 2; phase++)
            {
                inputs[idx].type = INPUT_KEYBOARD;
                inputs[idx].u.ki.wVk = 0;                       // KEYEVENTF_UNICODE 要求 wVk=0
                inputs[idx].u.ki.wScan = code;                  // wScan = Unicode 码元
                inputs[idx].u.ki.dwFlags = KEYEVENTF_UNICODE | (phase == 1 ? KEYEVENTF_KEYUP : 0);
                inputs[idx].u.ki.time = 0;
                inputs[idx].u.ki.dwExtraInfo = IntPtr.Zero;
                idx++;
            }
        }
        return inputs;
    }

    // 普通虚拟键（回车/退格），down + up
    private static INPUT[] BuildKeyInputs(ushort vk, int count)
    {
        INPUT[] inputs = new INPUT[count * 2];
        int idx = 0;
        for (int i = 0; i < count; i++)
        {
            for (int phase = 0; phase < 2; phase++)
            {
                inputs[idx].type = INPUT_KEYBOARD;
                inputs[idx].u.ki.wVk = vk;
                inputs[idx].u.ki.wScan = 0;
                inputs[idx].u.ki.dwFlags = (phase == 1 ? KEYEVENTF_KEYUP : 0);
                inputs[idx].u.ki.time = 0;
                inputs[idx].u.ki.dwExtraInfo = IntPtr.Zero;
                idx++;
            }
        }
        return inputs;
    }

    private static uint SendEvents(INPUT[] inputs)
    {
        return SendInput((uint)inputs.Length, inputs, SizeOfInput);
    }

    // 分批注入长文本（每批 500 码元，批间隔 20ms，给重型应用喘息）
    private static uint InjectTextBatched(string text)
    {
        byte[] raw = Encoding.Unicode.GetBytes(text);
        int units = raw.Length / 2;
        const int BatchUnits = 500;
        uint totalSent = 0;
        int offset = 0;
        while (offset < units)
        {
            int take = Math.Min(BatchUnits, units - offset);
            INPUT[] batch = BuildTextInputs(
                new string(text.ToCharArray(), offset, take));
            totalSent += SendEvents(batch);
            offset += take;
            if (offset < units) Thread.Sleep(20);
        }
        return totalSent;
    }

    // ---------------- 报告 ----------------
    private static void Report(string action, uint expected, uint sent)
    {
        Console.WriteLine();
        if (sent == expected)
            Console.WriteLine(string.Format(
                "  [API-OK] {0}: 已发送 {1}/{2} 个事件", action, sent, expected));
        else
            Console.WriteLine(string.Format(
                "  [API-FAIL] {0}: 预期 {1} 个事件, 实际发送 {2} (GetLastError={3})",
                action, expected, sent, Marshal.GetLastWin32Error()));
        Console.WriteLine("  >>> 请肉眼检查目标窗口「" + targetName + "」里的文字是否正确");
    }

    // ---------------- 测试用例 ----------------
    private static void TestChinese()
    {
        if (!EnsureTargetReady()) return;
        string text = "跨屏输入测试，中文上屏正常。";
        uint sent = SendEvents(BuildTextInputs(text));
        Report("中文短句(" + text.Length + "字)", (uint)(Encoding.Unicode.GetBytes(text).Length / 2 * 2), sent);
    }

    private static void TestMixed()
    {
        if (!EnsureTargetReady()) return;
        string text = "Hello 世界 123 !@# 混合输入";
        uint sent = SendEvents(BuildTextInputs(text));
        Report("中英混合+符号", (uint)(Encoding.Unicode.GetBytes(text).Length / 2 * 2), sent);
    }

    private static void TestEmoji()
    {
        if (!EnsureTargetReady()) return;
        string text = "表情 🎉✅ 生僻字: 龘";
        uint sent = SendEvents(BuildTextInputs(text));
        Report("Emoji代理对+生僻字", (uint)(Encoding.Unicode.GetBytes(text).Length / 2 * 2), sent);
    }

    private static void TestLongText()
    {
        if (!EnsureTargetReady()) return;
        StringBuilder sb = new StringBuilder();
        string seg = "跨屏输入长文本验证，测试分批注入的稳定性。";
        while (sb.Length < 500) sb.Append(seg);
        string text = sb.ToString();
        uint sent = InjectTextBatched(text);
        Report("长文本" + text.Length + "字(分批)", (uint)(Encoding.Unicode.GetBytes(text).Length / 2 * 2), sent);
    }

    private static void TestEnter()
    {
        if (!EnsureTargetReady()) return;
        uint sent = SendEvents(BuildKeyInputs(VK_RETURN, 1));
        Report("回车键 x1 (聊天软件会误发消息!)", 2, sent);
    }

    private static void TestBackspace()
    {
        if (!EnsureTargetReady()) return;
        uint sent = SendEvents(BuildKeyInputs(VK_BACK, 3));
        Report("退格键 x3", 6, sent);
    }

    private static void TestCombo()
    {
        if (!EnsureTargetReady()) return;
        string text = "这是一句话";
        uint sent1 = SendEvents(BuildTextInputs(text));
        Thread.Sleep(100);
        uint sent2 = SendEvents(BuildKeyInputs(VK_RETURN, 1));
        Report("文字+回车组合 (聊天软件会误发消息!)", sent1 + 2, sent1 + sent2);
    }

    // ---------------- 自检（不注入任何内容） ----------------
    private static int SelfCheck()
    {
        Console.WriteLine("AirType 阶段0 自检 (无注入)");
        Console.WriteLine(new string('=', 46));
        Console.WriteLine(string.Format("sizeof(INPUT)      = {0}   (x64 应为 40) {1}",
            SizeOfInput, SizeOfInput == 40 ? "OK" : "FAIL!"));
        Console.WriteLine(string.Format("sizeof(KEYBDINPUT) = {0}   (x64 应为 24)", Marshal.SizeOf(typeof(KEYBDINPUT))));

        IntPtr hwnd = GetForegroundWindow();
        Console.WriteLine(string.Format("GetForegroundWindow = {0}", hwnd));

        string sample = "跨屏输入测试 Hello 🎉";
        INPUT[] evs = BuildTextInputs(sample);
        Console.WriteLine();
        Console.WriteLine(string.Format("编码验证: \"{0}\"", sample));
        Console.WriteLine(string.Format("  字符数 {0}  UTF-16码元 {1}  生成事件 {2} (应={3})",
            sample.Length, Encoding.Unicode.GetBytes(sample).Length / 2, evs.Length, Encoding.Unicode.GetBytes(sample).Length));
        bool codeOk = evs[0].u.ki.wScan == 0x8DE8;  // '跨'
        bool typeOk = evs[0].type == INPUT_KEYBOARD && evs[0].u.ki.wVk == 0;
        bool flagOk = evs[0].u.ki.dwFlags == KEYEVENTF_UNICODE
                   && evs[1].u.ki.dwFlags == (KEYEVENTF_UNICODE | KEYEVENTF_KEYUP);
        Console.WriteLine(string.Format("  '跨' = U+8DE8 ? {0}  (实际 wScan=0x{1:X4})", codeOk ? "OK" : "FAIL", evs[0].u.ki.wScan));
        Console.WriteLine(string.Format("  type/wVk/flags 结构 ? {0}", (typeOk && flagOk) ? "OK" : "FAIL"));

        // 空发送探测：0 个事件，不产生任何实际输入
        uint ret = SendInput(0, new INPUT[1], SizeOfInput);
        Console.WriteLine(string.Format("SendInput(0,...) = {0}  (0=正常) {1}", ret, ret == 0 ? "OK" : "FAIL"));

        Console.WriteLine();
        Console.WriteLine(codeOk && typeOk && flagOk && SizeOfInput == 40
            ? "[结论] 注入内核自检全部通过, 可进入交互实测 (不带参数运行)"
            : "[结论] 自检未通过, 请把以上输出发给开发排查");
        return (codeOk && typeOk && flagOk && SizeOfInput == 40) ? 0 : 1;
    }

    // ---------------- 主程序 ----------------
    private static int Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "--selfcheck")
        {
            return SelfCheck();
        }

        Console.WriteLine("======================================================");
        Console.WriteLine("  AirType 阶段0验证 v2 (窗口选择版)");
        Console.WriteLine("======================================================");
        Console.WriteLine();
        Console.WriteLine("  ** 使用前必读 **");
        Console.WriteLine("  1. 推荐先打开「记事本」再运行本程序，所有测试都打在记事本里");
        Console.WriteLine("  2. 禁止选微信/QQ/WorkBuddy 等聊天软件:");
        Console.WriteLine("     回车会误发消息, 快速注入可能让对方卡死");
        Console.WriteLine("  3. 每次注入前程序会校验目标窗口, 打错地方会自动拦截");
        Console.WriteLine();
        Console.WriteLine("  三步用法:");
        Console.WriteLine("    第1步: 输入窗口编号, 选定记事本作为注入目标");
        Console.WriteLine("    第2步: 输入测试项编号 (推荐先测 1)");
        Console.WriteLine("    第3步: 切到记事本看结果。测完可继续选其他测试项");

        bool first = true;
        while (true)
        {
            Console.WriteLine();
            Console.WriteLine("------------------------------------------");
            Console.WriteLine(string.Format("  当前目标: {0}", targetHwnd == IntPtr.Zero ? "(未选)" : targetName));
            Console.WriteLine("  1.中文短句  2.中英混合  3.Emoji  4.长文本500字");
            Console.WriteLine("  5.回车(慎)  6.退格x3   7.文字+回车(慎)");
            Console.WriteLine("  8.选择/更换目标窗口   0.退出");
            Console.Write("选择: ");

            ConsoleKeyInfo key = Console.ReadKey(true);
            Console.WriteLine(key.KeyChar);
            if (first && key.KeyChar != '8' && key.KeyChar != '0')
            {
                Console.WriteLine("  (提示: 第一次使用请先按 8 选择目标窗口)");
                first = false;
                continue;
            }
            switch (key.KeyChar)
            {
                case '1': TestChinese(); break;
                case '2': TestMixed(); break;
                case '3': TestEmoji(); break;
                case '4': TestLongText(); break;
                case '5': TestEnter(); break;
                case '6': TestBackspace(); break;
                case '7': TestCombo(); break;
                case '8': PickWindow(); break;
                case '0':
                    return 0;
                default:
                    Console.WriteLine("  无效选择");
                    break;
            }
        }
    }
}
