"""H3.2: exercise the real AIAgent initializer behind offline side-effect sentinels."""
import builtins
import importlib
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch


class ConstructionEffect(OSError):
    """An attempted effect was stopped before it could reach the host."""


class H3RealAgentConstructionTests(unittest.TestCase):
    def test_real_agent_stops_before_first_filesystem_write(self):
        attempted = []

        def deny(name):
            def blocked(*args, **kwargs):
                attempted.append(name)
                raise ConstructionEffect(name)
            return blocked

        original_open = builtins.open
        original_path_open = Path.open
        original_os_open = os.open

        def guarded_open(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                return deny("open")(file, mode, *args, **kwargs)
            return original_open(file, mode, *args, **kwargs)

        def guarded_path_open(path, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                return deny("Path.open")(path, mode, *args, **kwargs)
            return original_path_open(path, mode, *args, **kwargs)

        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

        def guarded_os_open(path, flags, *args, **kwargs):
            if flags & write_flags:
                return deny("os.open")(path, flags, *args, **kwargs)
            return original_os_open(path, flags, *args, **kwargs)

        hermes_home = str(Path(tempfile.gettempdir()) / "hermes-h3-real-agent-must-not-exist")
        effect_guards = (
            patch.object(socket, "socket", deny("socket.socket")),
            patch.object(socket, "create_connection", deny("socket.create_connection")),
            patch.object(subprocess, "Popen", deny("subprocess.Popen")),
            patch.object(subprocess, "run", deny("subprocess.run")),
            patch.object(os, "system", deny("os.system")),
            patch.object(os, "open", guarded_os_open),
            patch.object(builtins, "open", guarded_open),
            patch.object(Path, "open", guarded_path_open),
            patch.object(Path, "mkdir", deny("Path.mkdir")),
            patch.object(Path, "write_text", deny("Path.write_text")),
            patch.object(Path, "write_bytes", deny("Path.write_bytes")),
        )
        with patch.dict(os.environ, {"HERMES_HOME": hermes_home}):
            with ExitStack() as stack:
                for guard in effect_guards:
                    stack.enter_context(guard)
                agent_module = importlib.import_module("run_agent")
                self.assertTrue(attempted)
                with self.assertRaisesRegex(ConstructionEffect, "os.open"):
                    agent_module.AIAgent(
                        model="nvidia/nemotron-3.5-lightning:free",
                        provider="openrouter",
                        base_url="https://openrouter.ai/api/v1",
                        api_key="offline-dummy-key",
                        quiet_mode=True,
                        skip_memory=True,
                        skip_context_files=True,
                        skip_background_review=True,
                        enabled_toolsets=[],
                        fallback_model={},
                    )

        self.assertEqual(attempted[0], "Path.mkdir")
        self.assertFalse(Path(hermes_home).exists())


if __name__ == "__main__":
    unittest.main()
