# H3.1 — local held construction experiment

Source implementation for AEH PR #131 review 5827028114, based on Hermes v0.23.0 / `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. MIT license and Nous Research notice preserved.

`gateway.h3_guarded_construction.prepare_h3_local(H3LocalSpec(...))` constructs an actual dedicated `H3HeldRuntime` and an `H3Hold` retaining that exact object. It is a deliberately restricted new runtime type, **not a fully initialized ordinary AIAgent**, a dry-run snapshot of one, or proof about an installed/running gateway. The explicit specification names a fixed candidate model route; it does not establish current pricing, configured provider identity or privacy eligibility. No credentials or client are resolved.

The adapter inherits `H3ConstructionMixin._create_agent(..., h3_construction=spec)`, which branches to this module **before** importing `run_agent` or resolving config/provider state. Normal calls delegate arguments unchanged to the original factory body, renamed `_create_agent_unrestricted`. No HTTP handler supplies the H3 argument; no new route, request selector or launcher is added. H3 mode rejects room/session/routing/model overrides and all nonlocal owner declarations. It cannot be used as a live-owner/authority executor: it has no live execution method or admission path.

The H3 object contains empty concrete tool/fallback/auxiliary tuples, no client, and a held marker. `validate(candidate)` requires `candidate is held.runtime` and revalidates both strict field types and the saved route/identity/capability state. It rejects an equal but different object, unsafe initial holds, and drift in client/tools/fallback/auxiliary/model/provider/URL/profile/request/held state. Validation returns the same **still-held** object; there is no release/activate operation, signing key, serializable policy assertion or `policy_reader` callback. Turn, provider, tool, auxiliary and package entry methods always deny.

## Why ordinary construction is not used in this first slice

Ordinary `_create_agent` resolves credentials and session state, then AIAgent's `init_agent` builds clients, discovers plugins and initializes memory/context engines. The precise tool-loading acquisition entry is `agent/agent_init.py::_load_tools` calling `hermes_cli.left_core_migration.recover_at_startup`, before final tool definitions are known. This patch avoids that entire constructor; it does **not** claim those normal paths now have mandatory zero-egress guards. A future guarded full AIAgent needs those initialization paths refactored into safe preparation/execution phases and independently tested. This is a bounded code prototype, not another diagnosis-only deliverable.

## Offline verification

New tests import the real new module and invoke the production mixin construction seam under sentinels rejecting sockets, subprocesses, shell commands, Path reads/writes, and imports of `run_agent`, `agent`, `tools`, `model_tools`, `pm`, `hermes_cli`, OpenAI and Anthropic. Tests assert local-only scope, zero capabilities, exact-object identity, state drift and permanent execution denial; a separate behavioral test confirms default delegation forwards arguments and return identity unchanged. No source-text/AST shape tests or installed Hermes imports are used. The full API adapter import/dependency graph and ordinary AIAgent initialization are not exercised by this dependency-free slice.

Run with an existing Python 3.10+ interpreter from the checkout:

```text
python -B -m unittest discover -s tests/gateway -p test_h3_guarded_construction.py -v
```

The canonical `scripts/run_tests.sh` suite and `scripts/check` are NOT_RUN on this station: no pytest/test environment or lint environment is installed, and the canonical runner would attempt provisioning. Installing dependencies is prohibited by the task. The standalone stdlib slice is an explicit constrained verification alternative, not a claim of CI parity or full Hermes regression coverage. No dependencies were installed. Earlier successful CAIA tests were not rerun.

## Remaining gates

H3 remains **BLOCKED_RUNTIME_ATTESTATION / PARTIAL_ACCEPT**. This experiment has no network/OS sandbox and does not defend against hostile Python code mutating objects or replacing methods in the same interpreter. Signed process identity, trusted launcher/verifier, safe full-AIAgent construction, OS privilege observations, policy enforcement across all real transports, and any live inference remain separate gates. No gateway/model was started, no installed source/configuration/secrets/Worker was modified, and no merge/deployment is authorized.

Verification: 15/15 standalone Offline tests PASS on existing Python 3.14.6. Initial missing-module and later identity/type regressions were observed failing before implementation/correction. Independent read-only source review found no blocking issue within the explicitly limited held-type scope. Canonical suite/lint NOT_RUN; no dependencies installed.
