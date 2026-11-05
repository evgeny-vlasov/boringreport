"""Run on happys with SSH forwarding localhost:8765 and an installed-app OAuth client JSON."""
import http.server
import json
import pathlib
import secrets
import sys
import urllib.parse
import urllib.request

client = json.loads(pathlib.Path(sys.argv[1]).read_text())['installed']
state = secrets.token_urlsafe(32)
redirect = 'http://localhost:8765/'
params = dict(client_id=client['client_id'], redirect_uri=redirect, response_type='code', scope='https://www.googleapis.com/auth/gmail.send', access_type='offline', prompt='consent', state=state)
print('Open this URL in your laptop browser:\n' + 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params), flush=True)

class Callback(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if query.get('state') != [state] or 'code' not in query:
            self.send_error(400)
            return
        body = urllib.parse.urlencode(dict(client_id=client['client_id'], client_secret=client['client_secret'], code=query['code'][0], redirect_uri=redirect, grant_type='authorization_code')).encode()
        with urllib.request.urlopen('https://oauth2.googleapis.com/token', body, timeout=60) as response:
            token = json.load(response)
        if not token.get('refresh_token'):
            self.send_error(400, 'No refresh token returned')
            return
        path = pathlib.Path.home() / '.config/boringreport/gmail.json'
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.touch(mode=0o600)
        path.chmod(0o600)
        path.write_text(json.dumps(dict(client_id=client['client_id'], client_secret=client['client_secret'], refresh_token=token['refresh_token'])))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Gmail authorization saved on happys. You may close this tab.')
        self.server.authorized = True

server = http.server.HTTPServer(('127.0.0.1',8765), Callback)
server.authorized = False
server.timeout = 600
while not server.authorized:
    server.handle_request()
