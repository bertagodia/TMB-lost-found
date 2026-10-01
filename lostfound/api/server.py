"""Servidor de laboratorio local. No destinado a datos personales ni producción."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlsplit

from ..config import WEB_DIR


def make_handler(engine):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, payload, content_type='application/json; charset=utf-8'):
            content = payload.encode() if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if self.path == '/':
                self.respond(200, (WEB_DIR / 'index.html').read_text(), 'text/html; charset=utf-8')
            elif self.path in ('/app.js', '/styles.css'):
                mime = 'text/javascript' if self.path == '/app.js' else 'text/css'
                self.respond(200, (WEB_DIR / self.path[1:]).read_text(), mime + '; charset=utf-8')
            elif self.path == '/api/info':
                self.respond(200, {'count': len(engine.objects),
                                   'synthetic': all(o.get('synthetic') is True for o in engine.objects)})
            else:
                self.respond(404, {'error': 'Ruta desconocida'})

        def do_POST(self):
            if self.path != '/api/search':
                self.respond(404, {'error': 'Ruta desconocida'})
                return
            # Only the local UI may issue browser requests; no wildcard CORS.
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                self.respond(403, {'error': 'Origen no permitido'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('Solicitud vacía o demasiado grande')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('Se esperaba un objeto JSON')
                result = engine.search(body, policy=body.get('policy', 'soft'),
                                       window=int(body.get('window', 2)), k=int(body.get('k', 5)),
                                       min_score=float(body.get('min_score', 0)))
                self.respond(200, result)
            except (ValueError, TypeError, AttributeError) as exc:
                self.respond(400, {'error': str(exc)})

        def log_message(self, *_):
            pass  # Do not log descriptions.
    return Handler


def serve(engine, port):
    with ThreadingHTTPServer(('127.0.0.1', port), make_handler(engine)) as server:
        print(f'Laboratorio local: http://127.0.0.1:{port} · Ctrl+C para detener', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
