using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;

namespace LedgerZeroLauncher
{
    class Program
    {
        private static Process serverProcess = null;
        private static int targetPort = 8080;
        private static bool autoBrowser = true;
        private static string exeDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');

        static void Main(string[] args)
        {
            Console.OutputEncoding = Encoding.UTF8;
            Console.Title = "LedgerZero — Autonomous Treasury & AI Finance Controller";

            ParseArguments(args);

            PrintBanner();

            // Set working directory to the folder containing LedgerZero.exe
            if (!string.IsNullOrEmpty(exeDir) && Directory.Exists(exeDir))
            {
                Directory.SetCurrentDirectory(exeDir);
            }

            // Register cleanup handlers
            Console.CancelKeyPress += (s, e) =>
            {
                e.Cancel = true;
                StopServerAndExit();
            };
            AppDomain.CurrentDomain.ProcessExit += (s, e) =>
            {
                CleanupChildProcess();
            };

            // Check if server is already running on target port
            bool alreadyRunning = IsServerOnline(targetPort);

            if (alreadyRunning)
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("[INFO] LedgerZero server is already running on port " + targetPort + ".");
                Console.ResetColor();

                PrintAccessEndpoints();

                if (autoBrowser)
                {
                    OpenBrowser("http://localhost:" + targetPort + "/dashboard.html");
                }

                RunInteractiveLoop(alreadyRunning: true);
                return;
            }

            // Locate Python interpreter
            string pythonPath = FindPythonExecutable();
            if (string.IsNullOrEmpty(pythonPath))
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("[ERROR] Could not locate a valid Python interpreter.");
                Console.WriteLine("        Please ensure Python 3.10+ is installed and added to PATH,");
                Console.WriteLine("        or create a .venv in this folder.");
                Console.ResetColor();
                Console.WriteLine("\nPress any key to exit...");
                Console.ReadKey(true);
                return;
            }

            // Check if app.py exists
            string appPyPath = Path.Combine(exeDir, "app.py");
            if (!File.Exists(appPyPath))
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("[ERROR] Cannot find 'app.py' in: " + exeDir);
                Console.ResetColor();
                Console.WriteLine("\nPress any key to exit...");
                Console.ReadKey(true);
                return;
            }

            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine("[STARTUP] Python runtime: " + pythonPath);
            Console.WriteLine("[STARTUP] Starting LedgerZero server process...");
            Console.ResetColor();

            // Start python -u app.py
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pythonPath;
            psi.Arguments = "-u app.py";
            psi.WorkingDirectory = exeDir;
            psi.UseShellExecute = false;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.CreateNoWindow = true;

            try
            {
                serverProcess = new Process();
                serverProcess.StartInfo = psi;

                serverProcess.OutputDataReceived += (s, e) =>
                {
                    if (!string.IsNullOrEmpty(e.Data))
                    {
                        Console.WriteLine("  [SERVER] " + e.Data);
                    }
                };

                serverProcess.ErrorDataReceived += (s, e) =>
                {
                    if (!string.IsNullOrEmpty(e.Data))
                    {
                        Console.ForegroundColor = ConsoleColor.DarkYellow;
                        Console.WriteLine("  [LOG] " + e.Data);
                        Console.ResetColor();
                    }
                };

                serverProcess.Start();
                serverProcess.BeginOutputReadLine();
                serverProcess.BeginErrorReadLine();
            }
            catch (Exception ex)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("[ERROR] Failed to start server process: " + ex.Message);
                Console.ResetColor();
                Console.WriteLine("\nPress any key to exit...");
                Console.ReadKey(true);
                return;
            }

            // Wait for server to become responsive
            Console.Write("[WAIT] Waiting for server on http://localhost:" + targetPort + "/api/status ");
            bool isReady = false;
            for (int i = 0; i < 30; i++)
            {
                Thread.Sleep(500);
                Console.Write(".");
                if (IsServerOnline(targetPort))
                {
                    isReady = true;
                    break;
                }
                if (serverProcess.HasExited)
                {
                    break;
                }
            }
            Console.WriteLine();

            if (serverProcess.HasExited)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("[ERROR] Server process terminated unexpectedly (exit code: " + serverProcess.ExitCode + ").");
                Console.ResetColor();
                Console.WriteLine("\nPress any key to exit...");
                Console.ReadKey(true);
                return;
            }

            if (isReady)
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("\n======================================================================");
                Console.WriteLine("  [SUCCESS] LEDGERZERO ENGINE ONLINE & READY");
                Console.WriteLine("======================================================================");
                Console.ResetColor();

                PrintAccessEndpoints();

                if (autoBrowser)
                {
                    OpenBrowser("http://localhost:" + targetPort + "/dashboard.html");
                }
            }
            else
            {
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.WriteLine("[WARNING] Server took longer than expected to respond, but is running.");
                PrintAccessEndpoints();
                Console.ResetColor();
            }

            RunInteractiveLoop(alreadyRunning: false);
        }

        private static void ParseArguments(string[] args)
        {
            for (int i = 0; i < args.Length; i++)
            {
                string arg = args[i].ToLowerInvariant();
                if (arg == "--no-browser" || arg == "-n")
                {
                    autoBrowser = false;
                }
                else if ((arg == "--port" || arg == "-p") && i + 1 < args.Length)
                {
                    int p;
                    if (int.TryParse(args[i + 1], out p))
                    {
                        targetPort = p;
                        i++;
                    }
                }
                else if (arg == "--status")
                {
                    ShowStatusAndExit();
                }
                else if (arg == "--stop")
                {
                    StopPortOwners(targetPort);
                    Console.WriteLine("[OK] Stopped any running LedgerZero server instances.");
                    Environment.Exit(0);
                }
                else if (arg == "--help" || arg == "-h" || arg == "/?")
                {
                    PrintHelp();
                    Environment.Exit(0);
                }
            }
        }

        private static void PrintBanner()
        {
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine(@"
██╗     ███████╗██████╗  ██████╗ ███████╗██████╗ ███████╗███████╗██████╗ 
██║     ██╔════╝██╔══██╗██╔════╝ ██╔════╝██╔══██╗╚══███╔╝██╔════╝██╔══██╗
██║     █████╗  ██║  ██║██║  ███╗█████╗  ██████╔╝  ███╔╝ █████╗  ██████╔╝
██║     ██╔══╝  ██║  ██║██║   ██║██╔══╝  ██╔══██╗ ███╔╝  ██╔══╝  ██╔══██╗
███████╗███████╗██████╔╝╚██████╔╝███████╗██║  ██║███████╗███████╗██║  ██║
╚══════╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝
");
            Console.ForegroundColor = ConsoleColor.DarkCyan;
            Console.WriteLine("               AUTONOMOUS TREASURY & CLOSE ENGINE");
            Console.WriteLine("         Track 04: AI Finance Controller — Razorpay 2026");
            Console.WriteLine("======================================================================");
            Console.ResetColor();
        }

        private static void PrintAccessEndpoints()
        {
            Console.ForegroundColor = ConsoleColor.White;
            Console.WriteLine("  Web Dashboard : http://localhost:" + targetPort + "/dashboard.html");
            Console.WriteLine("  API Status    : http://localhost:" + targetPort + "/api/status");
            Console.WriteLine("  About / Showcase: http://localhost:" + targetPort + "/pitch.html");
            Console.WriteLine("======================================================================");
            Console.ResetColor();
        }

        private static void PrintHelp()
        {
            Console.WriteLine("LedgerZero.exe - System Launcher");
            Console.WriteLine("Usage: LedgerZero.exe [OPTIONS]");
            Console.WriteLine();
            Console.WriteLine("Options:");
            Console.WriteLine("  --no-browser, -n     Start server without opening the web browser");
            Console.WriteLine("  --port, -p <num>     Specify port (default: 8080)");
            Console.WriteLine("  --status             Check current health of running server and exit");
            Console.WriteLine("  --stop               Stop any running LedgerZero processes on port 8080");
            Console.WriteLine("  --help, -h           Show this help message");
        }

        private static void ShowStatusAndExit()
        {
            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + targetPort + "/api/status");
                req.Proxy = null;
                req.KeepAlive = false;
                req.Timeout = 5000;
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                using (StreamReader reader = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                {
                    string json = reader.ReadToEnd();
                    Console.ForegroundColor = ConsoleColor.Green;
                    Console.WriteLine("[ONLINE] Server is healthy:");
                    Console.ResetColor();
                    Console.WriteLine(json);
                }
            }
            catch (Exception ex)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("[OFFLINE] Cannot reach LedgerZero server on port " + targetPort + ": " + ex.Message);
                Console.ResetColor();
            }
            Environment.Exit(0);
        }

        private static bool IsServerOnline(int port)
        {
            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/api/status");
                req.Proxy = null;
                req.KeepAlive = false;
                req.Timeout = 2000;
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                {
                    return (resp.StatusCode == HttpStatusCode.OK);
                }
            }
            catch
            {
                return false;
            }
        }

        private static void OpenBrowser(string url)
        {
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine("[BROWSER] Automatically launching dashboard in default browser...");
            Console.ResetColor();

            // Tier 1: Windows CMD shell 'start' command (brings window to foreground reliably)
            try
            {
                ProcessStartInfo psiCmd = new ProcessStartInfo
                {
                    FileName = "cmd.exe",
                    Arguments = "/c start \"\" \"" + url + "\"",
                    CreateNoWindow = true,
                    UseShellExecute = false
                };
                using (Process p = Process.Start(psiCmd))
                {
                    if (p != null)
                    {
                        p.WaitForExit(3000);
                        return;
                    }
                }
            }
            catch { }

            // Tier 2: Direct ShellExecute
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName = url,
                    UseShellExecute = true
                };
                Process.Start(psi);
                return;
            }
            catch { }

            // Tier 3: explorer.exe URL handler
            try
            {
                Process.Start("explorer.exe", "\"" + url + "\"");
                return;
            }
            catch { }

            // Tier 4: Explicit system Edge/Chrome fallback
            try
            {
                Process.Start("msedge.exe", "\"" + url + "\"");
                return;
            }
            catch { }

            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine("[INFO] Open URL manually: " + url);
            Console.ResetColor();
        }

        private static string FindPythonExecutable()
        {
            // 1. Check local virtual environments in directory
            string[] localPaths = new string[]
            {
                Path.Combine(exeDir, ".venv", "Scripts", "python.exe"),
                Path.Combine(exeDir, "venv", "Scripts", "python.exe"),
                Path.Combine(exeDir, "env", "Scripts", "python.exe"),
                Path.Combine(exeDir, "python.exe")
            };

            foreach (string p in localPaths)
            {
                if (File.Exists(p)) return p;
            }

            // 2. Check standard user local python paths
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (!string.IsNullOrEmpty(localAppData))
            {
                string pyRoot = Path.Combine(localAppData, "Programs", "Python");
                if (Directory.Exists(pyRoot))
                {
                    foreach (string dir in Directory.GetDirectories(pyRoot, "Python3*"))
                    {
                        string candidate = Path.Combine(dir, "python.exe");
                        if (File.Exists(candidate)) return candidate;
                    }
                }
            }

            // 3. Test if 'python' is in PATH
            if (TestCommand("python", "--version")) return "python";

            // 4. Test if 'py' launcher is in PATH
            if (TestCommand("py", "-3 --version")) return "py";

            return null;
        }

        private static bool TestCommand(string cmd, string args)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = cmd;
                psi.Arguments = args;
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;
                using (Process p = Process.Start(psi))
                {
                    p.WaitForExit(2000);
                    return p.ExitCode == 0;
                }
            }
            catch
            {
                return false;
            }
        }

        private static void StopPortOwners(int port)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo("netstat", "-ano");
                psi.UseShellExecute = false;
                psi.RedirectStandardOutput = true;
                psi.CreateNoWindow = true;
                using (Process p = Process.Start(psi))
                {
                    string output = p.StandardOutput.ReadToEnd();
                    p.WaitForExit(3000);
                    foreach (string line in output.Split('\n'))
                    {
                        if (line.Contains(":" + port) && line.ToUpper().Contains("LISTENING"))
                        {
                            string[] parts = line.Trim().Split(new char[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
                            if (parts.Length > 0)
                            {
                                string pid = parts[parts.Length - 1];
                                int pidNum;
                                if (int.TryParse(pid, out pidNum))
                                {
                                    KillProcessTree(pidNum);
                                }
                            }
                        }
                    }
                }
            }
            catch { }
        }

        private static void KillProcessTree(int pid)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo("taskkill", "/F /T /PID " + pid);
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                using (Process p = Process.Start(psi))
                {
                    p.WaitForExit(2000);
                }
            }
            catch { }
        }

        private static void CleanupChildProcess()
        {
            if (serverProcess != null && !serverProcess.HasExited)
            {
                try
                {
                    KillProcessTree(serverProcess.Id);
                }
                catch { }
            }
        }

        private static void StopServerAndExit()
        {
            Console.WriteLine("\n[SHUTDOWN] Stopping LedgerZero server...");
            CleanupChildProcess();
            Console.WriteLine("[SHUTDOWN] Goodbye.");
            Environment.Exit(0);
        }

        private static void RunInteractiveLoop(bool alreadyRunning)
        {
            Console.WriteLine();
            Console.ForegroundColor = ConsoleColor.DarkGray;
            Console.WriteLine("Controls: [B] Open Browser | [S] Query Status | [Q] Quit");
            Console.ResetColor();

            while (true)
            {
                if (!alreadyRunning && serverProcess != null && serverProcess.HasExited)
                {
                    Console.ForegroundColor = ConsoleColor.Yellow;
                    Console.WriteLine("\n[ALERT] Server process has stopped.");
                    Console.ResetColor();
                    break;
                }

                if (Console.KeyAvailable)
                {
                    ConsoleKeyInfo key = Console.ReadKey(true);
                    if (key.Key == ConsoleKey.Q || (key.Modifiers == ConsoleModifiers.Control && key.Key == ConsoleKey.C))
                    {
                        StopServerAndExit();
                        break;
                    }
                    else if (key.Key == ConsoleKey.B)
                    {
                        OpenBrowser("http://localhost:" + targetPort + "/dashboard.html");
                    }
                    else if (key.Key == ConsoleKey.S)
                    {
                        ShowServerHealth();
                    }
                }
                Thread.Sleep(200);
            }
        }

        private static void ShowServerHealth()
        {
            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + targetPort + "/api/status");
                req.Proxy = null;
                req.KeepAlive = false;
                req.Timeout = 2000;
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                using (StreamReader reader = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                {
                    Console.ForegroundColor = ConsoleColor.Green;
                    Console.WriteLine("\n[STATUS 200 OK] " + reader.ReadToEnd());
                    Console.ResetColor();
                }
            }
            catch (Exception ex)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("\n[STATUS ERROR] " + ex.Message);
                Console.ResetColor();
            }
        }
    }
}
