"""H3.1 local, zero-egress construction experiment. No execution or attestation.

This dedicated held runtime deliberately does NOT initialize ordinary AIAgent:
that constructor loads provider/config/plugin/context-engine machinery. There is
no release operation. Do not connect this object to a policy_reader or HTTP run.
Like all in-process Python state, these checks do not resist hostile host code.
"""
from dataclasses import dataclass
import re

_MODEL = 'nvidia/nemotron-3.5-lightning:free'
_PROVIDER = 'openrouter'
_BASE_URL = 'https://openrouter.ai/api/v1'
_IDENTITY = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')


class H3ConstructionDenied(RuntimeError):
    """This experiment is permanently held, or its construction invariant failed."""


@dataclass(frozen=True, slots=True)
class H3LocalSpec:
    """Explicit inputs, not claims about configured or running Hermes state."""
    profile: str
    request_id: str
    owner: str = 'local'
    model: str = _MODEL
    provider: str = _PROVIDER
    base_url: str = _BASE_URL
    tools: tuple = ()
    fallbacks: tuple = ()
    auxiliary_routes: tuple = ()

    def __post_init__(self):
        for identity in (self.profile, self.request_id):
            if type(identity) is not str or not _IDENTITY.fullmatch(identity):
                raise ValueError('H3 requires bounded profile/request identifiers')
        if (any(type(value) is not str for value in (self.owner,self.model,self.provider,self.base_url))
                or any(type(value) is not tuple for value in (self.tools,self.fallbacks,self.auxiliary_routes))
                or self.owner != 'local' or self.model != _MODEL or self.provider != _PROVIDER
                or self.base_url != _BASE_URL or self.tools != ()
                or self.fallbacks != () or self.auxiliary_routes != ()):
            raise ValueError('H3 construction requires the fixed local zero-capability route')


@dataclass(frozen=True, slots=True, eq=False)
class H3HeldRuntime:
    """Concrete H3-only runtime with no client, initialization side effects or turn."""
    profile: str
    request_id: str
    model: str
    provider: str
    base_url: str
    tools: tuple = ()
    fallbacks: tuple = ()
    auxiliary_routes: tuple = ()
    client: object = None
    held: bool = True

    def run_conversation(self, *args, **kwargs):
        raise H3ConstructionDenied('H3.1 is permanently held; live execution is unavailable')

    chat = run_conversation
    request_provider = run_conversation
    execute_tool = run_conversation
    call_auxiliary = run_conversation
    acquire_package = run_conversation


class H3Hold:
    """Keep the exact constructed object and reject identity or state drift.

    Validation returns the same still-held object, never a release token or a
    serializable policy assertion. No API can convert this into ordinary AIAgent.
    """
    __slots__ = ('_runtime', '_expected')

    def __init__(self, runtime):
        self._runtime = runtime
        self._expected = self._state(runtime)

    @property
    def runtime(self):
        return self._runtime

    @staticmethod
    def _state(runtime):
        if (type(runtime) is not H3HeldRuntime or runtime.client is not None
                or runtime.held is not True):
            raise H3ConstructionDenied('H3 runtime must have no client and remain held')
        try:
            H3LocalSpec(profile=runtime.profile, request_id=runtime.request_id,
                        model=runtime.model, provider=runtime.provider, base_url=runtime.base_url,
                        tools=runtime.tools, fallbacks=runtime.fallbacks,
                        auxiliary_routes=runtime.auxiliary_routes)
        except ValueError as exc:
            raise H3ConstructionDenied('H3 runtime capability or route changed') from exc
        return (runtime.profile, runtime.request_id, runtime.model, runtime.provider,
                runtime.base_url, runtime.tools, runtime.fallbacks,
                runtime.auxiliary_routes, runtime.client, runtime.held)

    def validate(self, candidate):
        if candidate is not self._runtime or self._state(candidate) != self._expected:
            raise H3ConstructionDenied('H3 held object identity or policy changed')
        return candidate

    def run_conversation(self, *args, **kwargs):
        raise H3ConstructionDenied('H3.1 has no release or execution path')


def prepare_h3_local(spec, *, requested_model=None, requested_provider=None,
                     model_options=None, route=None, session_model=None,
                     room_dispatch=None, room_execution_policy=None,
                     gateway_session_key=None):
    """Construct only the dedicated held runtime; never call the normal factory.

    This internal entry point has no wire selector, config loader, provider SDK,
    credentials, installer, tool discovery or caller-supplied factory callback.
    Delegated/live-owner/authority ownership is rejected by H3LocalSpec.
    """
    if type(spec) is not H3LocalSpec:
        raise TypeError('H3 requires a typed local construction specification')
    # Revalidate even if a caller bypassed frozen dataclass assignment.
    spec.__post_init__()
    if any(value is not None for value in (
            requested_model, requested_provider, model_options, route, session_model,
            room_dispatch, room_execution_policy, gateway_session_key)):
        raise H3ConstructionDenied('H3 construction does not allow routed/session/room overrides')
    runtime = H3HeldRuntime(profile=spec.profile, request_id=spec.request_id,
                           model=spec.model, provider=spec.provider, base_url=spec.base_url)
    return H3Hold(runtime)


class H3ConstructionMixin:
    """The API adapter's tested construction seam; normal calls stay unchanged."""

    def _create_agent(self, *args, h3_construction=None, **kwargs):
        if h3_construction is None:
            return self._create_agent_unrestricted(*args, **kwargs)
        if args:
            raise H3ConstructionDenied('H3 construction only accepts explicit keyword inputs')
        return prepare_h3_local(h3_construction, **kwargs)
