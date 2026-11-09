"""Offline H3.1 behavior tests; also runnable with stdlib unittest, no pytest."""
import importlib
import importlib.abc
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import gateway.h3_guarded_construction as h3


class ForbiddenRuntimeImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'run_agent', 'agent', 'tools', 'model_tools', 'pm', 'hermes_cli', 'openai', 'anthropic'}:
            raise AssertionError('Forbidden construction import: '+fullname)
        return None


class H3ConstructionTests(unittest.TestCase):
    def spec(self, **changes):
        values = dict(profile='isolated-h3', request_id='offline-request')
        values.update(changes)
        return h3.H3LocalSpec(**values)

    def test_import_and_construction_have_no_runtime_egress(self):
        finder=ForbiddenRuntimeImports()
        sys.meta_path.insert(0,finder)
        try:
            with ExitStack() as stack:
                for owner,name in ((socket,'socket'),(socket,'create_connection'),
                                   (subprocess,'Popen'),(subprocess,'run'),(os,'system'),
                                   (Path,'read_text'),(Path,'read_bytes'),(Path,'write_text'),(Path,'write_bytes')):
                    stack.enter_context(patch.object(owner,name,side_effect=AssertionError('egress forbidden')))
                module=importlib.reload(sys.modules['gateway.h3_guarded_construction'])
                class Factory(module.H3ConstructionMixin):
                    def _create_agent_unrestricted(self, *args, **kwargs):
                        raise AssertionError('Ordinary construction forbidden')
                held=Factory()._create_agent(h3_construction=module.H3LocalSpec(
                    profile='isolated-h3',request_id='offline-request'))
                self.assertIs(held.validate(held.runtime),held.runtime)
                self.assertIsNone(held.runtime.client)
                self.assertEqual(held.runtime.tools,())
                self.assertEqual(held.runtime.fallbacks,())
                self.assertEqual(held.runtime.auxiliary_routes,())
        finally:
            sys.meta_path.remove(finder)

    def test_rejects_nonlocal_owners(self):
        for owner in ('delegated','live_owner','authority','LOCAL',''):
            with self.subTest(owner=owner), self.assertRaises(ValueError):
                self.spec(owner=owner)

    def test_rejects_unbounded_route_and_nonempty_capabilities(self):
        for field,value in [('model','paid'),('provider','auto'),('base_url','https://other.invalid'),
                            ('tools',('terminal',)),('fallbacks',('paid',)),('auxiliary_routes',('title',))]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.spec(**{field:value})

    def test_rejects_missing_or_malformed_identity(self):
        for field,value in [('profile',''),('request_id',''),('request_id',None),('profile','x\nsecret')]:
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                self.spec(**{field:value})

    def test_exact_object_identity_required(self):
        first=h3.prepare_h3_local(self.spec())
        other=h3.prepare_h3_local(self.spec())
        self.assertIs(first.validate(first.runtime),first.runtime)
        with self.assertRaises(h3.H3ConstructionDenied): first.validate(other.runtime)

    def test_route_client_tools_and_identity_drift_rejected(self):
        for field,value in [('model','changed'),('provider','other'),('base_url','http://other'),
                            ('client',object()),('tools',('terminal',)),('fallbacks',('paid',)),
                            ('auxiliary_routes',('title',)),('profile','other'),('request_id','other'),('held',False)]:
            with self.subTest(field=field):
                held=h3.prepare_h3_local(self.spec())
                object.__setattr__(held.runtime,field,value)
                with self.assertRaises(h3.H3ConstructionDenied): held.validate(held.runtime)

    def test_validation_never_releases_for_execution(self):
        held=h3.prepare_h3_local(self.spec())
        for _ in range(2):
            runtime=held.validate(held.runtime)
            with self.assertRaises(h3.H3ConstructionDenied): runtime.run_conversation('offline')
            with self.assertRaises(h3.H3ConstructionDenied): runtime.chat('offline')

    def test_no_tool_auxiliary_package_or_provider_entry_can_execute(self):
        runtime=h3.prepare_h3_local(self.spec()).runtime
        for name in ('request_provider','execute_tool','call_auxiliary','acquire_package'):
            with self.subTest(name=name), self.assertRaises(h3.H3ConstructionDenied):
                getattr(runtime,name)()

    def test_arbitrary_dict_is_not_a_construction_spec(self):
        with self.assertRaises(TypeError): h3.prepare_h3_local({'profile':'isolated-h3'})

    def test_equal_but_wrong_typed_state_is_drift(self):
        held=h3.prepare_h3_local(self.spec())
        object.__setattr__(held.runtime,'held',1)
        with self.assertRaises(h3.H3ConstructionDenied): held.validate(held.runtime)

    def test_frozen_spec_revalidated_at_construction_boundary(self):
        spec=self.spec()
        object.__setattr__(spec,'owner','live_owner')
        with self.assertRaises(ValueError): h3.prepare_h3_local(spec)

    def test_cannot_hold_an_already_unsafe_runtime(self):
        runtime=h3.prepare_h3_local(self.spec()).runtime
        object.__setattr__(runtime,'tools',('terminal',))
        with self.assertRaises(h3.H3ConstructionDenied): h3.H3Hold(runtime)

    def test_route_session_room_and_model_overrides_rejected(self):
        for name,value in [('route',{}),('session_model','other'),('room_dispatch',{}),
                           ('room_execution_policy',{}),('gateway_session_key','owner'),
                           ('model_options',{}),('requested_model','other'),('requested_provider','other')]:
            with self.subTest(name=name), self.assertRaises(h3.H3ConstructionDenied):
                h3.prepare_h3_local(self.spec(),**{name:value})

    def test_production_factory_seam_holds_without_normal_construction(self):
        class Factory(h3.H3ConstructionMixin):
            def _create_agent_unrestricted(self, *args, **kwargs):
                raise AssertionError('Ordinary construction forbidden')
        held=Factory()._create_agent(h3_construction=self.spec())
        self.assertIs(held.validate(held.runtime),held.runtime)
        with self.assertRaises(h3.H3ConstructionDenied): held.run_conversation('offline')

    def test_production_factory_default_delegates_arguments_unchanged(self):
        normal=unittest.mock.Mock(return_value=object())
        class Factory(h3.H3ConstructionMixin):
            _create_agent_unrestricted=normal
        result=Factory()._create_agent(requested_model='existing',session_id='existing-session')
        normal.assert_called_once_with(requested_model='existing',session_id='existing-session')
        self.assertIs(result,normal.return_value)


if __name__ == '__main__': unittest.main()
