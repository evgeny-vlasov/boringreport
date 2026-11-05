"""Receive the user's bot token over an SSH-forwarded loopback form."""
import http.server
import json
from pathlib import Path
import re
import secrets
import urllib.parse
import publisher

nonce = secrets.token_urlsafe(32)
route = '/' + nonce
config_path = publisher.CONFIG_DIR/'publishing.json'
config = json.loads(config_path.read_text())

class Setup(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def respond(self,code,body):
        self.send_response(code)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        if self.path != route:
            self.respond(404,'Not found')
            return
        self.respond(200,f'''<!doctype html><meta charset="utf-8"><title>Boring Report Telegram setup</title>
<style>body{{font:18px/1.6 system-ui;max-width:640px;margin:64px auto;padding:24px;color:#17212b;background:#f7f8f6}}input,button{{font:inherit;padding:12px;box-sizing:border-box;margin:8px 0}}input{{width:100%}}</style>
<h1>Connect the report bot</h1><p>Destination: <strong>{config['channel']}</strong>.</p>
<p>Add your bot as a channel administrator with <strong>Post Messages</strong> permission, then paste its BotFather token below. This form is forwarded securely to happys over SSH. The token is not printed or saved in this chat.</p>
<form method="post" action="{route}" autocomplete="off"><label>Bot token<input type="password" name="token" required autocomplete="off"></label><button>Verify and save on happys</button></form>''')

    def do_POST(self):
        if self.path != route:
            self.respond(404,'Not found')
            return
        length = int(self.headers.get('Content-Length','0'))
        if not 0 < length < 4096:
            self.respond(400,'Invalid request')
            return
        fields = urllib.parse.parse_qs(self.rfile.read(length).decode())
        token = fields.get('token',[''])[0].strip()
        if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{20,}',token):
            self.respond(400,'The bot token format is invalid. Return to the form and retry.')
            return
        try:
            me,chat = publisher.check_bot(config,token)
            publisher.save(publisher.CONFIG_DIR/'telegram.json',{'bot_token':token})
            config.update(channel_id=chat['id'],enabled=True,mode='auto')
            publisher.save(config_path,config)
        except (publisher.APIError,publisher.UncertainRequest) as error:
            import html
            self.respond(400,'<p>'+html.escape(str(error))+'</p><p>Return to the form after correcting the settings.</p>')
            return
        import html
        editing = ''
        try:
            account = publisher.telegraph('getAccountInfo',{'fields':['auth_url']})
            editing = '<p><a target="_blank" rel="noopener" href="'+html.escape(account['auth_url'],quote=True)+'">Open your Telegraph editing session</a>. Keep this login link private. It lets you edit the published articles in your browser.</p>'
        except (publisher.APIError,publisher.UncertainRequest):
            editing = '<p>Your Telegraph browser editing login can be prepared separately.</p>'
        self.respond(200,'<h1>Telegram bot saved on happys.</h1><p>Posting permission verified for '+html.escape(config['channel'])+'. You may close this tab.</p>'+editing)
        print('Bot connection verified:',me['username'],'channel:',config['channel'],flush=True)
        self.server.finished = True

server = http.server.ThreadingHTTPServer(('127.0.0.1',8766),Setup)
server.finished = False
server.timeout = 1
print('Open this secure local setup page: http://localhost:8766'+route,flush=True)
while not server.finished:
    server.handle_request()
server.server_close()
