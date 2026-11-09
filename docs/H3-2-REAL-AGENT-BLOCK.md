# H3.2: real `AIAgent` construction is not offline-safe

H3.2 tested the actual `run_agent.AIAgent` import and initializer with guards for network
sockets, child processes, shell execution, and file creation/writes. The test does not run a
Gateway or a model. Its HERMES_HOME points at a unique non-existent temporary path; write attempts
are intercepted before reaching disk.

## Observed first blocked effects

The production API factory imports `run_agent.AIAgent` before calling the constructor. On Windows,
that import reaches `hermes_logging._portalocker_probe()`. The probe uses `tempfile.mkstemp()` to
create a scratch file and test the logging lock. The offline sentinel blocks its `os.open` write.
Separately, import-time allowlist setup attempts to create the configured Hermes home; that
`Path.mkdir` is also blocked. With the imports already loaded, the constructor enters
`agent.agent_init.init_agent()` and `_setup_logging()` repeats the lock probe before it can proceed.
It cannot satisfy a no-write construction contract even before a provider request or tool turn.

After logging, initialization creates an API client in `_build_client()`, then
`_load_tools()` calls `hermes_cli.left_core_migration.recover_at_startup()` before plugin discovery
or the tool snapshot. That recovery may install a plugin through PM when pending migrations and
policy permit it. Later initialization creates the session directory and publishes session state.
Skipping only `recover_at_startup()` would therefore leave earlier and later filesystem effects,
provider setup, and additional initialization paths.

## H3 decision

The real `AIAgent` constructor is denied for the H3 offline-held path. `H3ConstructionMixin` keeps
that path on the dedicated `H3HeldRuntime`; it does not fall through to `_create_agent_unrestricted`
or import `run_agent`. Its held result still rejects turn, tool, auxiliary, provider-request, and
package-acquisition calls. Ordinary factory calls without an H3 spec continue to delegate their
arguments and result unchanged.

This does not claim that normal Hermes agent creation is unsafe under its ordinary user-authorized
operation. It shows that normal creation cannot be reused to prove a zero-write, zero-install,
zero-egress H3 runtime. Making the real class safe would require an upstream initializer design that
separates logging, client creation, migration/recovery, session persistence, and tool/plugin loading
behind explicit inert-mode seams. H3 does not bypass those operations or weaken their guards.

## Offline test evidence

`tests/gateway/test_h3_real_agent_construction.py` imports the real factory and attempts the actual
`AIAgent` constructor under side-effect sentinels. The first observed filesystem boundary is
import-time allowlist setup attempting `Path.mkdir`. After that is blocked, the constructor's
logging setup reaches the Windows scratch-file probe (`os.open`). Both are stopped. The H3 unit
tests continue to prove no runtime import or effect in the held path, and that ordinary factory
calls delegate unchanged.

Run with the repository's test interpreter:

```powershell
python -B -m unittest discover -s tests/gateway -p 'test_h3*construction.py' -v
```

Full `scripts/run_tests.sh` and `scripts/check` were not run because the checkout's PM test
environment is not provisioned; provisioning would install dependencies, which this task forbids.
