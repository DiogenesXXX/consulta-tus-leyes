"""Pruebas de integración contra un servidor real y una base temporal."""
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

from backend.server import LocalServer
from backend.database import initialize


class Client:
    def __init__(self, port):
        self.port, self.cookie, self.csrf = port, '', ''

    def call(self, path, body=None, method=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        payload = json.dumps(body).encode() if body is not None else None
        request_headers = {'Content-Type': 'application/json', 'Cookie': self.cookie, 'X-CSRF-Token': self.csrf}
        request_headers.update(headers or {})
        connection.request(method or ('POST' if body is not None else 'GET'), path, payload, request_headers)
        response = connection.getresponse()
        raw = response.read()
        status, result_headers = response.status, dict(response.getheaders())
        result = json.loads(raw) if 'application/json' in result_headers.get('Content-Type', '') else raw
        if 'Set-Cookie' in result_headers:
            self.cookie = result_headers['Set-Cookie'].split(';')[0]
        if isinstance(result, dict) and 'csrf' in result:
            self.csrf = result['csrf'] or ''
        connection.close()
        return status, result, result_headers


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.temp.name) / 'test.db'
        cls.server = LocalServer(('127.0.0.1', 0), cls.db)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def setUp(self):
        self.client = Client(self.server.server_port)

    def register(self, client, email):
        return client.call('/api/register', {'name':'Persona de prueba','email':email,'password':'Una frase de prueba 2026','confirm_password':'Una frase de prueba 2026','consent':True})

    def test_01_catalog_filters_stats_and_exports(self):
        status, data, _ = self.client.call('/api/documents')
        self.assertEqual((status, data['total']), (200, 24))
        self.assertTrue(all(i['demo'] for i in data['items']))
        _, found, _ = self.client.call('/api/documents?'+urlencode({'q':'me quieren botar del cuarto','kind':'proyecto'}))
        self.assertEqual(found['total'], 2)
        self.assertTrue(all(i['sector']=='Vivienda' for i in found['items']))
        _, stats, _ = self.client.call('/api/stats?sector=Vivienda')
        self.assertEqual((stats['total'], stats['laws'], stats['projects']), (3,1,2))
        self.assertEqual(sum(i['count'] for i in stats['by_chamber']), 3)
        _, export, headers = self.client.call('/api/export?sector=Vivienda&format=csv')
        self.assertEqual(len(export.decode('utf-8-sig').splitlines()), 4)
        self.assertIn('attachment', headers['Content-Disposition'])
        self.assertEqual(self.client.call('/api/documents?from=2026-10-01&to=2026-01-01')[0],400)

    def test_02_guest_csrf_migration_persistence_and_logout(self):
        status, guest, headers = self.client.call('/api/guest', {'name':'Prueba visitante','interests':['Vivienda']})
        self.assertEqual(status,201)
        self.assertEqual(guest['user']['role'],'guest')
        self.assertIn('HttpOnly',headers['Set-Cookie'])
        self.assertEqual(self.client.call('/api/bookmarks',{'id':'DEMO-001','kind':'saved'},headers={'X-CSRF-Token':''})[0],403)
        self.assertEqual(self.client.call('/api/bookmarks',{'id':'DEMO-001','kind':'saved'})[0],200)
        self.assertEqual(self.client.call('/api/documents/DEMO-002/opinion',{'choice':'agree'})[0],401)
        self.assertEqual(self.register(self.client,'migration@example.test')[0],201)
        self.assertEqual(len(self.client.call('/api/bookmarks')[1]['items']),1)
        initialize(self.db)
        self.assertEqual(len(self.client.call('/api/bookmarks')[1]['items']),1)
        saved_cookie=self.client.cookie
        self.client.call('/api/logout',{})
        self.assertIsNone(self.client.call('/api/session')[1]['user'])
        self.assertEqual(self.client.call('/api/bookmarks',headers={'Cookie':saved_cookie})[0],401)
        self.assertEqual(self.client.call('/api/login',{'email':'migration@example.test','password':'Una frase de prueba 2026'})[0],200)
        self.assertEqual(len(self.client.call('/api/bookmarks')[1]['items']),1)
        self.client.call('/api/bookmarks',{'id':'DEMO-001','kind':'saved'},method='DELETE')
        self.assertEqual(self.client.call('/api/bookmarks')[1]['items'],[])

    def test_03_account_validation_vote_upsert_and_comment_privacy(self):
        bad={'name':'Prueba','email':'persona@example.test','password':'corta','confirm_password':'corta','consent':True}
        self.assertEqual(self.client.call('/api/register',bad)[0],400)
        self.assertEqual(self.register(self.client,'opinion@example.test')[0],201)
        self.assertEqual(self.register(Client(self.server.server_port),'opinion@example.test')[0],409)
        with sqlite3.connect(self.db) as db:
            stored=db.execute('SELECT password_hash FROM users WHERE email=?',('opinion@example.test',)).fetchone()[0]
        self.assertTrue(stored.startswith('pbkdf2_sha256$'))
        self.assertNotIn('Una frase',stored)
        for choice in ['agree','neutral']:
            self.assertEqual(self.client.call('/api/documents/DEMO-002/opinion',{'choice':choice})[0],200)
        opinion=self.client.call('/api/documents/DEMO-002/opinion')[1]
        self.assertEqual((opinion['total'],opinion['choice']), (1,'neutral'))
        self.client.call('/api/documents/DEMO-002/comments',{'body':'Comentario de prueba <script>sin ejecutar</script>'})
        self.assertEqual(len(self.client.call('/api/documents/DEMO-002/opinion')[1]['comments']),1)
        stranger=Client(self.server.server_port)
        self.assertEqual(stranger.call('/api/documents/DEMO-002/opinion')[1]['comments'],[])
        self.assertEqual(stranger.call('/api/login',{'email':'opinion@example.test','password':'incorrecta'})[0],401)
        self.assertEqual(stranger.call('/api/bookmarks')[0],401)

    def test_04_static_assets_and_request_boundaries(self):
        for path in ['/','/js/app.js','/styles.css','/assets/01_tus_derechos.gif','/assets/01_tus_derechos.png','/assets/fonts/Montserrat.ttf','/assets/fonts/IBMPlexSans.ttf']:
            status, body, headers=self.client.call(path)
            self.assertEqual(status,200,path)
            self.assertGreater(len(body),100,path)
            self.assertIn('Content-Security-Policy',headers)
        self.assertEqual(self.client.call('/%2e%2e/backend/server.py')[0],404)
        self.assertEqual(self.client.call('/api/guest',{},headers={'Origin':'https://untrusted.example'})[0],403)
        self.assertEqual(self.client.call('/api/health',headers={'Host':'untrusted.example'})[0],403)
        self.assertEqual(self.client.call('/api/documents/MISSING')[0],404)

    def test_05_filter_combination_and_user_isolation(self):
        _, meta, _=self.client.call('/api/meta')
        for key, values in meta['filters'].items():
            for value in values:
                _, data, _=self.client.call('/api/documents?'+urlencode({key:value}))
                self.assertGreater(data['total'],0)
                self.assertTrue(all(item[key]==value for item in data['items']))
        self.client.call('/api/guest',{})
        self.client.call('/api/bookmarks',{'id':'DEMO-003','kind':'followed'})
        other=Client(self.server.server_port)
        other.call('/api/guest',{})
        self.assertEqual(other.call('/api/bookmarks')[1]['items'],[])


if __name__=='__main__':
    unittest.main()
