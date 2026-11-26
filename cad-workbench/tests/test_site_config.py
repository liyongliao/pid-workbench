"""Installation, authorization, persistence and capability regression coverage."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from support import Service
from access_control import AccessControl, AccessError
from site_config import read, save, capabilities, team_names
from workspace import initialize
from test_managed import Services


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = initialize(Path(self.temp.name))
        self.env = patch.dict(os.environ, PID_VAULT=str(self.root))
        self.env.start()
    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

    def test_validation_is_atomic_and_revision_conflicts_are_rejected(self):
        initial = read(self.root)
        for change in [dict(systemName=''), dict(features={}), dict(teams=[]),
                       dict(teams=[dict(name='仪表', enabled=True, tagFields=['bad field'])])]:
            with self.subTest(change=change), self.assertRaises(ValueError):save(self.root, dict(initial, **change))
        self.assertEqual(read(self.root), initial)
        updated = save(self.root, dict(initial, systemName='通用工程资料库', complete=True))
        self.assertTrue(updated['setupComplete'])
        self.assertEqual(read(self.root)['systemName'], '通用工程资料库')
        with self.assertRaises(AccessError) as err:save(self.root, initial)
        self.assertEqual(err.exception.status, 409)

    def test_custom_teams_and_disabled_team_authorization(self):
        from accounts import require_team
        from disciplines import apply
        config = read(self.root)
        config['teams'].append(dict(name='仪表', enabled=True, tagFields=['LOOP'], searchFields=['SERVICE']))
        config['teams'][0]['enabled'] = False
        save(self.root, config)
        self.assertIn('仪表', team_names())
        self.assertNotIn('工艺', team_names())
        with self.assertRaises(AccessError):require_team(dict(role='admin'), '工艺')
        require_team(dict(role='editor', teams=['仪表']), '仪表')
        drawing = dict(items=[dict(handle='1', entity='INSERT', name='', block='Instrument', tag='', xy=[0, 0],
                                  attributes=[dict(key='LOOP', value='P-101'),dict(key='SERVICE', value='供水')])])
        apply(dict(team='仪表'), drawing)
        self.assertEqual(drawing['equipment'][0]['tag'], 'P-101')
        self.assertEqual(drawing['equipment'][0]['search'], '供水')

    def test_empty_data_never_enables_features_and_models_need_review_data(self):
        manager = SimpleNamespace(base=self.root, catalog=[])
        state = capabilities(manager)
        self.assertFalse(any(state['enabled'].values()))
        config = read(self.root)
        save(self.root, config)
        manager.catalog = [dict(equipment=[dict(tag='A')])]
        state = capabilities(manager)
        self.assertTrue(state['enabled']['drawings'])
        self.assertTrue(state['enabled']['equipment'])
        self.assertFalse(state['enabled']['schematic'])
        self.assertFalse(state['enabled']['models'])
        folder = self.root/'models/custom/editor'; folder.mkdir(parents=True)
        (folder/'index.json').write_text('{}')
        self.assertTrue(capabilities(manager)['enabled']['models'])
        config = read(self.root); config['features']['models'] = 'off'; save(self.root, config)
        self.assertFalse(capabilities(manager)['enabled']['models'])
        self.assertTrue(capabilities(manager)['available']['models'])

    def test_remote_setup_code_is_one_time_and_never_in_public_settings(self):
        auth = AccessControl(self.root)
        code = auth.setup_code()
        self.assertEqual((self.root/'data/setup-token.txt').stat().st_mode & 0o777, 0o600)
        payload = dict(adminPassword='Admin-test-123', viewerPassword='Viewer-test-123', setupToken='wrong')
        with self.assertRaises(AccessError):auth.setup(payload, '192.0.2.50')
        payload['setupToken'] = code
        auth.setup(payload, '192.0.2.50')
        self.assertFalse((self.root/'data/setup-token.txt').exists())
        with self.assertRaises(AccessError):auth.setup(payload, '192.0.2.50')
        self.assertNotIn(code, json.dumps(read(self.root)))

    def test_existing_install_is_not_reset(self):
        (self.root/'data/access-control.json').write_text('{}')
        self.assertTrue(read(self.root)['setupComplete'])
        config = read(self.root)
        config['teams'] = config['teams'][1:]
        with self.assertRaises(ValueError):save(self.root, config)


class SetupHTTPTests(unittest.TestCase):
    def test_fresh_setup_public_branding_and_permissions(self):
        service = Service()
        try:
            for path in ('/setup', '/setup.js', '/setup.css', '/api/site'):
                self.assertEqual(service.request(path)[0], 200)
            self.assertEqual(service.request('/api/admin/settings')[0], 401)
            cookie = service.setup()
            self.assertTrue(service.request('/api/capabilities', cookie=cookie)[1]['setupRequired'])
            payload = service.request('/api/admin/settings', cookie=cookie)[1]['settings']
            payload.update(systemName='<安全显示的名称>', complete=True)
            status, saved, _ = service.post_admin('/api/admin/settings', payload, cookie)
            self.assertEqual(status, 200, saved)
            self.assertEqual(service.request('/api/site')[1]['systemName'], '<安全显示的名称>')
            self.assertNotIn('teams', service.request('/api/site')[1])
            self.assertFalse(service.request('/api/capabilities', cookie=cookie)[1]['setupRequired'])
            viewer = service.login('viewer')
            self.assertEqual(service.request('/api/admin/settings', cookie=viewer)[0], 403)
            self.assertEqual(service.request('/api/admin/settings', 'POST', saved, viewer, {'X-Management-Token':service.state(cookie)['token']})[0], 403)
            self.assertEqual(service.request('/api/admin/settings', 'POST', saved, cookie)[0], 403)
            self.assertEqual(service.post_admin('/api/admin/settings', payload, cookie)[0], 409)
            self.assertEqual(service.request('/nwd.html', cookie=cookie)[0], 302)
            saved['features']['drawings'] = 'off'
            self.assertEqual(service.post_admin('/api/admin/settings', saved, cookie)[0], 200)
            self.assertEqual(service.request('/api/catalog', cookie=cookie)[1], [])
            self.assertEqual(service.request('/api/search?q=test', cookie=cookie)[1]['total'], 0)
            self.assertEqual(service.request('/api/drawing/test', cookie=cookie)[0], 404)
        finally:service.close()


@unittest.skipIf(os.name=='nt','Managed services require Unix process locks')
class ManagedSetupHTTPTests(unittest.TestCase):
    def test_settings_survive_restart_and_are_admin_only(self):
        service = Services()
        try:
            admin = service.setup()
            config = service.request('/api/admin/settings', cookie=admin)[1]['settings']
            config['teams'].append(dict(name='仪表', enabled=True, tagFields=['TAG'], searchFields=[]))
            config.update(systemName='设备资料中心', complete=True)
            code, saved, _ = service.post_admin('/api/admin/settings', config, admin)
            self.assertEqual(code, 200, saved)
            payload = dict(login='tester', name='测试人员', teams=['仪表'], password='Editor-test-123', enabled=True)
            self.assertEqual(service.post_admin('/api/admin/accounts', payload, admin)[0], 200)
            status, _, headers = service.request('/api/auth/login', 'POST', dict(role='editor', login='tester', password=payload['password']))
            self.assertEqual(status, 200)
            editor = headers['Set-Cookie'].split(';')[0]
            self.assertEqual(service.request('/api/admin/settings', cookie=editor)[0], 403)
            self.assertEqual(service.post_admin('/api/admin/settings', saved, editor)[0], 403)
            # Config lives outside immutable baseline/revisions and is retained at restart.
            self.assertTrue((service.vault.root/'data/system-settings.json').is_file())
            self.assertFalse((service.root/'data/system-settings.json').exists())
            service.process.terminate(); service.process.wait(timeout=15)
            service.process = service.start('production.py')
            import time
            for _ in range(100):
                try:
                    if service.request('/api/site')[0] == 200:break
                except OSError:pass
                time.sleep(.1)
            self.assertEqual(service.request('/api/site')[1]['systemName'], '设备资料中心')
        finally:service.close()
