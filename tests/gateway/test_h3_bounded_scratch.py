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
    def test_real_factory_requires_profile_initialization(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            for name in ("home", "scratch"):
                (root / name).mkdir()
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
            self.assertTrue(report["block"].startswith("write:home"), report)
            self.assertEqual(sorted(p.relative_to(root).as_posix() for p in root.rglob("*")),
                             ["home", "scratch", "scratch/canary"])
        self.assertFalse(root.exists())


if __name__ == "__main__":
    if len(sys.argv) == 2:
        sys.path.insert(0, os.getcwd())
        probe(Path(sys.argv[1]))
    else:
        unittest.main()

