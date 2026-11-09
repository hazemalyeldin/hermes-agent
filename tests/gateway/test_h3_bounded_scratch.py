"""H3.3 bounded scratch contract. Run the probe in a fresh interpreter."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class Blocked(BaseException):
    pass


def probe(root):
    home = root / "home"
    scratch = root / "scratch"
    events = []

    def reject(event):
        frame = sys._getframe(2)
        callers = []
        while frame:
            callers.append(frame.f_code.co_name)
            frame = frame.f_back
        raise Blocked(event, callers)

    def writable(path):
        if not isinstance(path, (str, bytes, os.PathLike)):
            reject("unresolved file descriptor")
        target = Path(os.fsdecode(path)).resolve()
        if target.parent != scratch:
            reject("write:" + (target.relative_to(root).as_posix()
                               if target.is_relative_to(root) else "<outside>"))
        events.append(target.name)

    def audit(event, args):
        if event == "open":
            if args[2] & (os.O_CREAT | os.O_APPEND | os.O_TRUNC | os.O_RDWR | os.O_WRONLY):
                writable(args[0])
        elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime", "os.truncate"}:
            if event == "os.mkdir" and Path(args[0]).resolve() == home and home.is_dir():
                return  # Existing directory: mkdir cannot create or replace it.
            if event == "os.chmod" and Path(args[0]).resolve() == home:
                reject(f"os.chmod:home:{args[1]:04o}")
            writable(args[0])
        elif event == "socket.gethostname":
            return
        elif event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn", "os.startfile", "winreg.Create", "winreg.Set")) or event in {
            "os.system", "os.rename", "os.link", "os.symlink", "os.chdir", "sqlite3.connect"
        }:
            reject(event)

    def trace(frame, event, arg):
        if event == "call":
            module = frame.f_globals.get("__name__", "")
            if module.startswith("pm.install") or frame.f_code.co_name in {
                "recover_at_startup", "handle_function_call", "run_conversation", "_build_client"
            }:
                reject(module + "." + frame.f_code.co_name)

    sys.addaudithook(audit)
    sys.setprofile(trace)
    (scratch / "canary").write_bytes(b"scratch")
    for forbidden in (home / "plugins", home / "config.yaml", root.parent / "outside-canary"):
        try:
            forbidden.write_bytes(b"")
        except Blocked:
            continue
        raise AssertionError("forbidden write passed")
    try:
        from run_agent import AIAgent
        AIAgent(quiet_mode=True, enabled_toolsets=[], fallback_model={})
    except Blocked as exc:
        print(json.dumps(dict(block=exc.args[0], stack=exc.args[1], writes=events)))
    else:
        raise AssertionError("construction boundary changed")


class SandboxTest(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt" and sys.version_info >= (3, 13), "Windows secure mkdir")
    def test_preprovisioned_home_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            home = root / "home"
            home.mkdir(mode=0o700)
            (root / "scratch").mkdir()
            self.assertEqual(list(home.iterdir()), [])
            # Read back the native descriptor before the diagnostic child starts.
            check = """
            $ErrorActionPreference = "Stop"
            $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            $acl = New-Object System.Security.AccessControl.DirectorySecurity
            $acl.SetAccessRuleProtection($true,$false)
            foreach ($principal in @($sid,'S-1-5-32-544','S-1-5-18')) {
                $id = [Security.Principal.SecurityIdentifier]::new($principal)
                $ace = [Security.AccessControl.FileSystemAccessRule]::new(
                    $id,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
                $acl.AddAccessRule($ace)
            }
            [IO.Directory]::SetAccessControl($env:H34_HOME,$acl)
            $acl = Get-Acl -LiteralPath $env:H34_HOME
            $rules = $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])
            $allowed = @($sid,'S-1-5-32-544','S-1-5-18')
            if (!$acl.AreAccessRulesProtected -or !$rules.Count) { exit 1 }
            foreach ($rule in $rules) {
                if ($rule.IsInherited -or $rule.IdentityReference.Value -notin $allowed) { exit 2 }
            }
            if ($sid -notin $rules.IdentityReference.Value) { exit 3 }
            """
            powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", check],
                           env={"SystemRoot": os.environ["SystemRoot"], "H34_HOME": str(home)},
                           check=True, timeout=30)
            env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "PATH") if key in os.environ}
            env.update(HERMES_HOME=str(root / "home"), TEMP=str(root / "scratch"),
                       TMP=str(root / "scratch"), TMPDIR=str(root / "scratch"),
                       USERPROFILE=str(root), HOME=str(root))
            cmd = [sys.executable, "-I", "-B", str(Path(__file__).resolve()), str(root)]
            child = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[2], env=env,
                                   capture_output=True, text=True, timeout=60)
            self.assertEqual(child.returncode, 0, child.stderr)
            report = json.loads(child.stdout.strip().splitlines()[-1])
            print(report)
            self.assertEqual(report["block"], "os.chmod:home:0700", report)
            self.assertIn("apply_secure_dir_policy", report["stack"])
            self.assertEqual(sorted(p.relative_to(root).as_posix() for p in root.rglob("*")),
                             ["home", "scratch", "scratch/canary"])
        self.assertFalse(root.exists())


if __name__ == "__main__":
    if len(sys.argv) == 2:
        sys.path.insert(0, os.getcwd())
        probe(Path(sys.argv[1]))
    else:
        unittest.main()
