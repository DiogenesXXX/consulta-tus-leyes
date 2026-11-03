"""Servidor de desarrollo local: API JSON y frontend en el mismo origen."""
import argparse
import csv
import hashlib
import hmac
import io
import json
import mimetypes
import re
import secrets
import sqlite3
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.database import initialize, connect, catalog
from backend.catalog import SECTORS, POLICIES, FILTER_KEYS, filter_catalog, summarize


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    result = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    return f'pbkdf2_sha256$600000${salt}${result}'


def verify_password(password, stored):
    try:
        _, rounds, salt, result = stored.split('$')
        candidate = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(result, candidate)
    except (ValueError, TypeError):
        return False


def text_field(body, key, minimum=0, maximum=200):
    value = body.get(key, '')
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise APIError(400, f'Revise el campo «{key}».')
    return value.strip()


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, db_path):
        self.db_path = str(db_path)
        initialize(db_path)
        self.limits = defaultdict(deque)
        self.limit_lock = threading.Lock()
        self.dummy_password = password_hash('not-a-real-account-password')
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'ConsultaTusLeyes/1.0'

    def log_message(self, fmt, *args):
        # Nunca registrar credenciales, cuerpos ni cookies.
        sys.stderr.write(f'[{self.log_date_time_string()}] {self.command} {urlsplit(self.path).path}\n')

    def reply(self, status, payload, content_type='application/json; charset=utf-8', cookie=None, filename=None):
        raw = json.dumps(payload, ensure_ascii=False).encode() if content_type.startswith('application/json') else payload
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Cache-Control', 'no-store' if self.path.startswith('/api/') else 'no-cache')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(raw)

    def body(self):
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            raise APIError(415, 'Envíe el contenido como JSON.')
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise APIError(400, 'Tamaño de solicitud inválido.')
        if size < 0 or size > 16384:
            raise APIError(413, 'La solicitud es demasiado grande.')
        try:
            body = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeError):
            raise APIError(400, 'El contenido JSON no es válido.')
        if not isinstance(body, dict):
            raise APIError(400, 'Se esperaba un objeto JSON.')
        return body

    def session(self, db, required=False, registered=False):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            token = cookie['ctl_session'].value if 'ctl_session' in cookie else ''
        except Exception:
            token = ''
        row = db.execute('SELECT * FROM sessions WHERE token_hash=? AND expires>?', (digest(token), int(time.time()))).fetchone()
        if not row and required:
            raise APIError(401, 'Entre con su cuenta o como visitante para continuar.')
        if registered and (not row or not row['user_id']):
            raise APIError(401, 'Entre con su cuenta para compartir su opinión.')
        return row

    def csrf(self, session):
        if not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
            raise APIError(403, 'La sesión cambió. Actualice la página e inténtelo otra vez.')

    def owner(self, session):
        return f'user:{session["user_id"]}' if session['user_id'] else f'guest:{session["token_hash"]}'

    def session_payload(self, db, session):
        if session is None:
            return {'user': None, 'csrf': None}
        if session['user_id']:
            user = dict(db.execute('SELECT id,name,email FROM users WHERE id=?', (session['user_id'],)).fetchone())
            user['role'] = 'user'
        else:
            user = {'id': None, 'name': session['guest_name'] or 'Visitante', 'role': 'guest', 'email': None}
        user['interests'] = json.loads(session['interests'])
        return {'user': user, 'csrf': session['csrf']}

    def new_session(self, db, user_id=None, name='', interests=None, previous=None):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        key = digest(token)
        age = 604800 if user_id else 86400
        db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?)', (key, user_id, name, json.dumps(interests or []), csrf, int(time.time()) + age))
        session = db.execute('SELECT * FROM sessions WHERE token_hash=?', (key,)).fetchone()
        if previous:
            if not previous['user_id'] and user_id:
                db.execute('INSERT OR IGNORE INTO bookmarks SELECT ?,document_id,kind,created_at FROM bookmarks WHERE owner=?', (self.owner(session), self.owner(previous)))
                db.execute('DELETE FROM bookmarks WHERE owner=?', (self.owner(previous),))
            db.execute('DELETE FROM sessions WHERE token_hash=?', (previous['token_hash'],))
        return session, f'ctl_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={age}'

    def limit(self):
        with self.server.limit_lock:
            key = self.client_address[0]
            attempts = self.server.limits[key]
            current = time.monotonic()
            while attempts and current - attempts[0] > 900:
                attempts.popleft()
            if len(attempts) >= 20:
                raise APIError(429, 'Demasiados intentos. Espere 15 minutos y vuelva a intentar.')
            attempts.append(current)

    def document(self, db, identifier):
        row = db.execute('SELECT payload FROM documents WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise APIError(404, 'No encontramos esa ficha.')
        return json.loads(row['payload'])

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def do_DELETE(self):
        self.dispatch()

    def dispatch(self):
        try:
            port = self.server.server_port
            if self.headers.get('Host') not in [f'127.0.0.1:{port}', f'localhost:{port}']:
                raise APIError(403, 'Este servidor solo permite acceso local.')
            if self.command not in ('GET', 'HEAD'):
                origin = self.headers.get('Origin')
                if origin and origin not in [f'http://127.0.0.1:{port}', f'http://localhost:{port}']:
                    raise APIError(403, 'Origen no permitido.')
            parsed = urlsplit(self.path)
            path = parsed.path.rstrip('/') or '/'
            params = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
            if not path.startswith('/api/'):
                if self.command not in ('GET', 'HEAD'):
                    raise APIError(405, 'Método no permitido.')
                return self.static(path)
            with connect(self.server.db_path) as db:
                self.api(db, path, params)
        except APIError as error:
            self.reply(error.status, {'error': error.message})
        except (ValueError, TypeError):
            self.reply(400, {'error': 'Revise los datos enviados, los filtros y las fechas.'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            import traceback
            traceback.print_exc()
            self.reply(500, {'error': 'No pudimos completar la operación. Inténtelo nuevamente.'})

    def static(self, path):
        root = (ROOT / 'frontend').resolve()
        target = (root / (unquote(path).lstrip('/') or 'index.html')).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise APIError(404, 'Archivo no encontrado.')
        kind = 'text/javascript' if target.suffix == '.js' else mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
        if kind.startswith('text/'):
            kind += '; charset=utf-8'
        self.reply(200, target.read_bytes(), kind)

    def api(self, db, path, params):
        method = 'GET' if self.command == 'HEAD' else self.command
        if method == 'GET' and path == '/api/health':
            return self.reply(200, {'ok': True, 'mode': 'demo', 'storage': 'sqlite'})
        if method == 'GET' and path == '/api/session':
            return self.reply(200, self.session_payload(db, self.session(db)))
        if method == 'GET' and path == '/api/meta':
            items = catalog(db)
            return self.reply(200, {'sectors': SECTORS, 'policies': POLICIES, 'filters': {k: sorted({i[k] for i in items}) for k in FILTER_KEYS}, 'demo': True})
        if method == 'POST' and path in ['/api/register', '/api/login', '/api/guest']:
            self.limit()
            body = self.body()
            previous = self.session(db)
            if path == '/api/guest':
                name = text_field(body, 'name', 0, 80)
                interests = body.get('interests', [])
                if not isinstance(interests, list) or any(not isinstance(x, str) or x not in SECTORS for x in interests) or len(interests) > 8:
                    raise APIError(400, 'Seleccione temas válidos.')
                session, cookie = self.new_session(db, name=name, interests=list(dict.fromkeys(interests)), previous=previous)
            else:
                email = text_field(body, 'email', 3, 254).lower()
                password = body.get('password', '')
                if not isinstance(password, str) or len(password) > 256:
                    raise APIError(400, 'Revise la contraseña.')
                if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                    raise APIError(400, 'Ingrese un correo electrónico válido.')
                if path == '/api/register':
                    name = text_field(body, 'name', 2, 80)
                    if len(password) < 12 or password != body.get('confirm_password'):
                        raise APIError(400, 'Use al menos 12 caracteres y confirme la misma contraseña.')
                    if body.get('consent') is not True:
                        raise APIError(400, 'Revise y acepte las condiciones de esta aplicación local.')
                    try:
                        user_id = db.execute('INSERT INTO users(name,email,password_hash,consent_at,created_at) VALUES (?,?,?,?,?)', (name, email, password_hash(password), now(), now())).lastrowid
                    except sqlite3.IntegrityError:
                        raise APIError(409, 'Ese correo ya tiene una cuenta. Puede iniciar sesión.')
                else:
                    user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
                    valid = verify_password(password, user['password_hash'] if user else self.server.dummy_password)
                    if not user or not valid:
                        raise APIError(401, 'El correo o la contraseña no coinciden.')
                    user_id = user['id']
                session, cookie = self.new_session(db, user_id=user_id, previous=previous)
            db.commit()
            return self.reply(201 if path != '/api/login' else 200, self.session_payload(db, session), cookie=cookie)
        if method == 'POST' and path == '/api/logout':
            session = self.session(db, required=True)
            self.csrf(session)
            if not session['user_id']:
                db.execute('DELETE FROM bookmarks WHERE owner=?', (self.owner(session),))
            db.execute('DELETE FROM sessions WHERE token_hash=?', (session['token_hash'],))
            db.commit()
            return self.reply(200, {'ok': True}, cookie='ctl_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
        if method == 'GET' and path in ['/api/documents', '/api/stats', '/api/export']:
            items = filter_catalog(catalog(db), params)
            if path == '/api/stats':
                return self.reply(200, summarize(items))
            if path == '/api/export':
                if params.get('format') == 'json':
                    return self.reply(200, {'demo': True, 'filters': params, 'items': items}, filename='consulta-leyes-demo.json')
                output = io.StringIO()
                fields = ['id', 'title', 'kind', 'sector', 'status', 'chamber', 'group', 'author', 'policy', 'date', 'demo']
                writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(items)
                return self.reply(200, ('\ufeff' + output.getvalue()).encode(), 'text/csv; charset=utf-8', filename='consulta-leyes-demo.csv')
            return self.reply(200, {'items': items, 'total': len(items), 'demo': True})
        if method == 'GET' and path == '/api/policies':
            items = filter_catalog(catalog(db), params)
            return self.reply(200, {'items': [dict(p, count=sum(i['policy'] == p['id'] for i in items)) for p in POLICIES], 'total': len(items), 'demo': True})
        match = re.fullmatch(r'/api/documents/([A-Za-z0-9-]+)(?:/(text|opinion|comments|feedback))?', path)
        if match:
            identifier, action = match.groups()
            doc = self.document(db, identifier)
            session = self.session(db)
            if method == 'GET' and action is None:
                marks = [] if session is None else [r['kind'] for r in db.execute('SELECT kind FROM bookmarks WHERE owner=? AND document_id=?', (self.owner(session), identifier))]
                return self.reply(200, dict(doc, saved='saved' in marks, followed='followed' in marks))
            if method == 'GET' and action == 'text':
                return self.reply(200, doc['full_text'].encode(), 'text/plain; charset=utf-8', filename=f'{identifier}.txt')
            if action in ['opinion', 'comments'] and doc['kind'] != 'proyecto':
                raise APIError(400, 'Las opiniones se recogen sobre proyectos.')
            if method == 'GET' and action == 'opinion':
                counts = {choice: 0 for choice in ['agree', 'neutral', 'disagree']}
                for row in db.execute('SELECT choice,COUNT(*) AS n FROM votes WHERE document_id=? GROUP BY choice', (identifier,)):
                    counts[row['choice']] = row['n']
                mine = db.execute('SELECT choice FROM votes WHERE document_id=? AND user_id=?', (identifier, session['user_id'])).fetchone() if session and session['user_id'] else None
                comments = db.execute("SELECT id,body,created_at,status,user_id FROM comments WHERE document_id=? AND (status='published' OR user_id=?) ORDER BY id DESC", (identifier, session['user_id'] if session else None)).fetchall()
                return self.reply(200, {'counts': counts, 'total': sum(counts.values()), 'choice': mine['choice'] if mine else None,
                                       'comments': [{k: r[k] for k in ['id', 'body', 'created_at', 'status']} for r in comments]})
            if method == 'POST' and action in ['opinion', 'comments', 'feedback']:
                session = self.session(db, required=True, registered=action != 'feedback')
                self.csrf(session)
                body = self.body()
                if action == 'opinion':
                    choice = body.get('choice')
                    if choice not in ['agree', 'neutral', 'disagree']:
                        raise APIError(400, 'Seleccione una de las tres respuestas.')
                    db.execute('INSERT INTO votes VALUES (?,?,?,?) ON CONFLICT(user_id,document_id) DO UPDATE SET choice=excluded.choice,updated_at=excluded.updated_at', (session['user_id'], identifier, choice, now()))
                elif action == 'comments':
                    message = text_field(body, 'body', 3, 1000)
                    db.execute('INSERT INTO comments(user_id,document_id,body,created_at) VALUES (?,?,?,?)', (session['user_id'], identifier, message, now()))
                else:
                    if type(body.get('helpful')) is not bool:
                        raise APIError(400, 'Respuesta inválida.')
                    db.execute('INSERT INTO feedback VALUES (?,?,?) ON CONFLICT(owner,document_id) DO UPDATE SET helpful=excluded.helpful', (self.owner(session), identifier, int(body['helpful'])))
                db.commit()
                return self.reply(200, {'ok': True, 'status': 'pending' if action == 'comments' else 'saved'})
        if path == '/api/bookmarks':
            session = self.session(db, required=True)
            owner = self.owner(session)
            if method == 'GET':
                rows = db.execute('SELECT b.kind,b.created_at,d.payload FROM bookmarks b JOIN documents d ON d.id=b.document_id WHERE b.owner=? ORDER BY b.created_at DESC', (owner,))
                return self.reply(200, {'items': [dict(json.loads(r['payload']), bookmark_kind=r['kind'], bookmarked_at=r['created_at']) for r in rows]})
            if method in ['POST', 'DELETE']:
                self.csrf(session)
                body = self.body()
                identifier, kind = body.get('id'), body.get('kind')
                if not isinstance(identifier, str) or kind not in ['saved', 'followed']:
                    raise APIError(400, 'Solicitud de guardado inválida.')
                self.document(db, identifier)
                if method == 'POST':
                    db.execute('INSERT OR IGNORE INTO bookmarks VALUES (?,?,?,?)', (owner, identifier, kind, now()))
                else:
                    db.execute('DELETE FROM bookmarks WHERE owner=? AND document_id=? AND kind=?', (owner, identifier, kind))
                db.commit()
                return self.reply(200, {'ok': True})
        raise APIError(404, 'Ruta de API no encontrada.')


def main():
    parser = argparse.ArgumentParser(description='Consulta tus leyes · servidor local')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'consulta.db')
    args = parser.parse_args()
    server = LocalServer(('127.0.0.1', args.port), args.db)
    print(f'Consulta tus leyes: http://127.0.0.1:{server.server_port}', flush=True)
    print('Catálogo de demostración. Para detener: Ctrl+C.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
