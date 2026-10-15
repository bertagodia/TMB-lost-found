"""Local request boundary adapted from PR #7 (WP3, d438386)."""
from fastapi.responses import JSONResponse

MAX_REQUEST = 58 * 1024 * 1024

def error_response(status, message, code):
    return JSONResponse({'error':message,'code':code},status_code=status)

class LocalMiddleware:
    """Bounded JSON bodies and same-origin loopback access, including chunked bodies."""
    def __init__(self, app, port):
        self.app = app
        self.hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def secure_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] = [*message.get('headers', []),
                    (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                    (b'x-frame-options', b'DENY')]
            await send(message)

        async def reject(status, message, code):
            await error_response(status, message, code)(scope, receive, secure_send)

        headers = {k.decode('latin-1').lower(): v.decode('latin-1') for k, v in scope['headers']}
        host = headers.get('host', '')
        if host not in self.hosts or (headers.get('origin') and headers['origin'] != 'http://' + host):
            return await reject(403, 'Accés local i mateix origen únicament.', 'local_access_only')
        if scope['method'] in {'POST', 'PATCH', 'PUT'}:
            if headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
                return await reject(415, 'Cal enviar JSON.', 'json_required')
            try:
                length = int(headers.get('content-length', '0'))
            except ValueError:
                return await reject(400, 'Content-Length invàlid.', 'invalid_length')
            if length < 0 or length > MAX_REQUEST:
                return await reject(413, 'Petició massa gran.', 'request_too_large')
            body = bytearray()
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > MAX_REQUEST:
                    return await reject(413, 'Petició massa gran.', 'request_too_large')
                if not message.get('more_body', False):
                    break
            if not body:
                return await reject(400, 'Petició buida.', 'empty_request')
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()

            return await self.app(scope, bounded_receive, secure_send)
        await self.app(scope, receive, secure_send)
