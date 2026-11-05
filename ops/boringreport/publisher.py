#!/usr/bin/env python3
"""Publish the archived R report to Telegraph and Telegram without an LLM."""
import argparse
import datetime as dt
import fcntl
import hashlib
from html import escape, unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path('/home/fluffy/projects/boringreport-service')
CONFIG_DIR = Path.home() / '.config/boringreport'
STATE = Path.home() / '.local/state/boringreport'
PUBLIC_REPO = 'evgeny-vlasov/boringreport'
POST_FORMAT = 'four-posts-v1'

class APIError(RuntimeError):
    pass

class UncertainRequest(RuntimeError):
    pass

def save(path, value, private=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600 if private else 0o644)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)

def request_json(url, data, token=None, files=None, form=False):
    if files:
        boundary = 'boringreport-' + secrets.token_hex(16)
        chunks = []
        for name, value in data.items():
            chunks += [f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()]
        for name, path in files.items():
            chunks += [f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{path.name}"\r\nContent-Type: image/png\r\n\r\n'.encode(), path.read_bytes(), b'\r\n']
        chunks += [f'--{boundary}--\r\n'.encode()]
        body = b''.join(chunks)
        content_type = 'multipart/form-data; boundary=' + boundary
    elif form:
        encoded = {key:json.dumps(value,ensure_ascii=False) if isinstance(value,(list,dict,bool)) else value for key,value in data.items()}
        body = urllib.parse.urlencode(encoded).encode()
        content_type = 'application/x-www-form-urlencoded'
    else:
        body = json.dumps(data, ensure_ascii=False).encode()
        content_type = 'application/json'
    request = urllib.request.Request(url, body, {'Content-Type':content_type,'User-Agent':'BoringReport/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        # A 5xx can occur after acceptance, so do not assume it is safe to retry.
        if error.code >= 500:
            raise UncertainRequest('Provider returned a server error; outcome needs checking.') from None
        try:
            description = json.loads(error.read()).get('description', 'Request rejected')
        except (ValueError, UnicodeError):
            description = f'Request rejected (HTTP {error.code})'
        raise APIError(str(description).replace(token or '\x00','[redacted]')) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise UncertainRequest('Connection failed or response was unreadable; outcome needs checking.') from None
    if not result.get('ok'):
        description = result.get('description') or result.get('error') or 'Request rejected'
        raise APIError(str(description).replace(token or '\x00','[redacted]'))
    return result['result']

def telegraph(method, data=None):
    credentials = json.loads((CONFIG_DIR / 'telegraph.json').read_text())
    return request_json('https://api.telegra.ph/' + method, {'access_token':credentials['access_token'], **(data or {})}, credentials['access_token'], form=True)

def create_account():
    path = CONFIG_DIR / 'telegraph.json'
    if path.exists():
        return
    account = request_json('https://api.telegra.ph/createAccount', {'short_name':'boringreport-happys','author_name':'Boring Report','author_url':'https://t.me/dots_and_lines'}, form=True)
    save(path, {'access_token':account['access_token']})
    print('Dedicated Telegraph account saved securely on happys.')

def telegram(method, data=None, files=None, token=None):
    token = token or json.loads((CONFIG_DIR / 'telegram.json').read_text())['bot_token']
    return request_json(f'https://api.telegram.org/bot{token}/{method}', data or {}, token, files)

def check_bot(config, token=None):
    me = telegram('getMe', token=token)
    chat = telegram('getChat', {'chat_id':config.get('channel_id') or config['channel']}, token=token)
    if chat['type'] != 'channel':
        raise APIError('Configured destination is not a Telegram channel.')
    if config.get('channel_id') and chat['id'] != config['channel_id']:
        raise APIError('Channel ID differs from the configured destination.')
    if not config.get('channel_id') and '@' + chat.get('username','').lower() != config['channel'].lower():
        raise APIError('Channel username differs from the approved destination.')
    member = telegram('getChatMember', {'chat_id':chat['id'],'user_id':me['id']}, token=token)
    if member['status'] not in ['creator','administrator'] or (member['status'] != 'creator' and not member.get('can_post_messages')):
        raise APIError('Add the bot as a channel administrator with Post Messages permission.')
    return me, chat

class ArticleParser(HTMLParser):
    allowed = {'a','aside','b','blockquote','br','code','em','figcaption','figure','h3','h4','hr','i','img','li','ol','p','pre','s','strong','u','ul','video'}
    void = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    ignored = {'head','script','style','iframe','object','form','button','input'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes = []
        self.stack = [(None,self.nodes)]
        self.suppressed = []

    def handle_starttag(self, tag, attrs):
        if self.suppressed or tag in self.ignored:
            if tag not in self.void:
                self.suppressed.append(tag)
            return
        mapped = {'h1':'h3','h2':'h3'}.get(tag,tag)
        children = self.stack[-1][1]
        if mapped in self.allowed:
            node = {'tag':mapped}
            attributes = dict(attrs)
            key = 'href' if mapped == 'a' else 'src' if mapped in ['img','video'] else None
            if key and attributes.get(key):
                url = attributes[key]
                if urllib.parse.urlparse(url).scheme.lower() in ['https','http','mailto']:
                    node['attrs'] = {key:url}
            children.append(node)
            if tag not in self.void:
                node['children'] = []
                self.stack.append((tag,node['children']))
        elif tag not in self.void:
            self.stack.append((tag,children))

    def handle_endtag(self, tag):
        if self.suppressed:
            if tag in self.suppressed:
                index = len(self.suppressed)-1-self.suppressed[::-1].index(tag)
                del self.suppressed[index:]
            return
        for index in range(len(self.stack)-1,0,-1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        if not self.suppressed:
            self.stack[-1][1].append(text)

def article_nodes(html, image_url, lang):
    parser = ArticleParser()
    parser.feed(html)
    caption = 'Generated directly by R scripts. Regional markers are geographic references, not exact sites.' if lang == 'en' else 'Графика построена скриптами R. Региональные маркеры — географические ориентиры, не точные места.'
    nodes = [{'tag':'figure','children':[{'tag':'img','attrs':{'src':image_url}},{'tag':'figcaption','children':[caption]}]}, *parser.nodes]
    if len(json.dumps(nodes,ensure_ascii=False).encode()) > 64*1024:
        raise ValueError('Telegraph article exceeds the 64 KB content limit.')
    return nodes

def canonical_nodes(nodes):
    """Ignore Telegraph-added heading IDs and harmless HTML whitespace merging."""
    result, buffered = [], ''
    def flush():
        nonlocal buffered
        text = re.sub(r'\s+',' ',buffered).strip()
        if text:
            result.append(text)
        buffered = ''
    for node in nodes:
        if isinstance(node,str):
            buffered += node
            continue
        flush()
        clean = {'tag':node['tag']}
        attrs = {k:v for k,v in node.get('attrs',{}).items() if k in ['href','src']}
        if attrs:
            clean['attrs'] = attrs
        children = canonical_nodes(node.get('children',[]))
        if children:
            clean['children'] = children
        result.append(clean)
    flush()
    return result

def source_commit(issue):
    # Keep image URLs stable when unrelated operations code is committed.
    commit = subprocess.check_output(['git','log','-1','--format=%H','--',f'output/{issue}/'],cwd=ROOT,text=True).strip()
    if not commit:
        raise ValueError('No archived image commit exists for this issue.')
    for lang in ['ru','en']:
        path = f'output/{issue}/boring-report-{lang}.png'
        archived = subprocess.check_output(['git','show',f'{commit}:{path}'],cwd=ROOT)
        if archived != (ROOT / path).read_bytes():
            raise ValueError('Archive the exact rendered images before publication.')
    return commit

def image_url(issue, lang, commit):
    path = f'output/{issue}/boring-report-{lang}.png'
    url = f'https://raw.githubusercontent.com/{PUBLIC_REPO}/{commit}/{path}'
    with urllib.request.urlopen(url,timeout=45) as response:
        data = response.read(10*1024*1024)
        if response.headers.get_content_type() != 'image/png' or data != (ROOT/path).read_bytes():
            raise ValueError('Public image differs from the archived local render.')
    return url

def prepare(issue):
    create_account()
    commit = source_commit(issue)
    package = ROOT / 'data/issues' / issue
    data = json.loads((package/'issue.json').read_text())
    record_path = STATE / f'{issue}.publication.json'
    record = json.loads(record_path.read_text()) if record_path.exists() else {'issue':issue,'articles':{}}
    for lang in ['ru','en']:
        url = image_url(issue,lang,commit)
        nodes = article_nodes((package/f'report-{lang}.html').read_text(),url,lang)
        title = f'Boring Report №{data["issue_number"]:02d} — {issue} ({lang.upper()})'
        fingerprint = hashlib.sha256(json.dumps(nodes,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        article = record['articles'].setdefault(lang,{})
        if article.get('pending') and not article.get('path'):
            # Reconcile a lost createPage response, without blindly duplicating it.
            pages = telegraph('getPageList',{'offset':0,'limit':200})['pages']
            matches = [page for page in pages if page['title'] == title]
            if len(matches) != 1:
                raise UncertainRequest('Uncertain Telegraph creation: inspect the account before retrying.')
            article.update(path=matches[0]['path'],url=matches[0]['url'])
        if article.get('content_hash') != fingerprint:
            method = 'editPage' if article.get('path') else 'createPage'
            params = {'title':title,'author_name':data['brand'],'author_url':'https://t.me/dots_and_lines','content':nodes,'return_content':True}
            if article.get('path'):
                params['path'] = article['path']
            article['pending'] = True
            save(record_path,record)
            result = telegraph(method,params)
            article.update(path=result['path'],url=result['url'],content_hash=fingerprint,image_url=url,source_sha=commit,pending=False)
            save(record_path,record)
        live = telegraph('getPage',{'path':article['path'],'return_content':True})
        if canonical_nodes(live.get('content',[])) != canonical_nodes(nodes):
            raise ValueError('Telegraph page does not match the prepared article.')
    record['preview'] = preview(data,record,(package/'telegram-ru.html').read_text())
    save(record_path,record)
    print(json.dumps({'issue':issue,'articles':{lang:a['url'] for lang,a in record['articles'].items()},'channel_posts':record['preview']['posts']},ensure_ascii=False,indent=2))
    return record

def telegram_text(source):
    """Keep the prepared Russian message and links, translating block HTML to Telegram HTML."""
    parser = ArticleParser()
    parser.feed(source)
    inline = {'b','strong','i','em','u','s','code','pre','blockquote'}
    def render(nodes):
        parts = []
        for node in nodes:
            if isinstance(node,str):
                parts.append(escape(re.sub(r'\s+',' ',node),quote=False))
                continue
            tag = node['tag']
            content = render(node.get('children',[]))
            if tag in inline:
                parts.append(f'<{tag}>{content}</{tag}>')
            elif tag == 'a' and node.get('attrs',{}).get('href'):
                parts.append('<a href="'+escape(node['attrs']['href'],quote=True)+'">'+content+'</a>')
            elif tag == 'br':
                parts.append('\n')
            elif tag == 'li':
                parts.append('• '+content.strip()+'\n')
            elif tag in {'h3','h4'}:
                parts.append('<b>'+content.strip()+'</b>\n\n')
            elif tag in {'p','aside','ul','ol'}:
                parts.append(content.strip()+'\n\n')
            elif tag not in {'img','video','figure','figcaption'}:
                parts.append(content)
        return ''.join(parts)
    rendered = re.sub(r'(?m)^[ \t]+|[ \t]+$','',render(parser.nodes))
    text = re.sub(r'\n[ \t]*\n(?:[ \t]*\n)*','\n\n',rendered).strip()
    if not text:
        raise ValueError('The Russian Telegram message is empty.')
    return text

def visible_length(text):
    plain = unescape(re.sub(r'<[^>]*>','',text))
    return len(plain.encode('utf-16-le'))//2

def preview(data,record,source):
    date = dt.date.fromisoformat(data['issue_id'])
    title_ru = f'Boring Report №{data["issue_number"]:02d} — {date.strftime("%d.%m.%Y")}'
    title_en = f'Boring Report №{data["issue_number"]:02d} — {date.strftime("%d %b %Y")}'
    message = telegram_text(source)
    def link_text(lang,title,subtitle):
        url = record['articles'][lang]['url']
        if not url.startswith('https://telegra.ph/'):
            raise ValueError('Unexpected article URL.')
        return '<b><a href="'+escape(url,quote=True)+'">'+escape(title)+'</a></b>\n'+subtitle
    def text_post(key,text):
        if visible_length(text)>4096:
            raise ValueError(f'{key} exceeds Telegram\'s single-message limit; shorten its source before publishing.')
        return {'key':key,'method':'sendMessage','data':{'text':text,'parse_mode':'HTML','link_preview_options':{'is_disabled':False}}}
    return {'format':POST_FORMAT,'posts':[
        {'key':'ru_image','method':'sendPhoto','data':{'caption':title_ru},'files':{'photo':f'output/{data["issue_id"]}/boring-report-ru.png'}},
        text_post('ru_message',message),
        text_post('ru_article',link_text('ru',title_ru,'Полный выпуск · Русский')),
        text_post('en_article',link_text('en',title_en,'Full report · English')),
    ]}

def validate_plan(plan):
    fingerprint = []
    for step in plan['posts']:
        hashes = {}
        for name,relative in step.get('files',{}).items():
            path = ROOT/relative
            data = path.read_bytes()
            if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data)>10*1024*1024:
                raise ValueError('Invalid or oversized Telegram photo.')
            hashes[name] = hashlib.sha256(data).hexdigest()
        if step['method'] == 'sendMessage' and visible_length(step['data']['text'])>4096:
            raise ValueError('Oversized Telegram message.')
        fingerprint.append({'step':step,'file_hashes':hashes})
    return hashlib.sha256(json.dumps(fingerprint,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def publish(issue,config,scheduled=False):
    if scheduled and (not config.get('enabled') or config.get('mode') != 'auto'):
        print('Automatic channel publication is disabled.')
        return
    # Check known delivery state before changing an article or attempting a send.
    record_path = STATE / f'{issue}.publication.json'
    prior = json.loads(record_path.read_text()) if record_path.exists() else {}
    if prior.get('telegram',{}).get('status') == 'sent' or prior.get('telegram',{}).get('removed_by_owner_request'):
        print('Channel post already recorded; no duplicate sent.')
        return
    if prior.get('telegram',{}).get('status') in ['in_flight','uncertain']:
        raise UncertainRequest('Previous Telegram send has an unknown outcome; check the channel before retrying.')
    me, chat = check_bot(config)
    if not config.get('channel_id'):
        config['channel_id'] = chat['id']
        save(CONFIG_DIR/'publishing.json',config)
    record = prepare(issue)
    plan = record['preview']
    fingerprint = validate_plan(plan)  # Validate all four posts before sending the first.
    delivery = record.get('telegram',{})
    if delivery.get('message_ids') and delivery.get('format') != POST_FORMAT:
        raise UncertainRequest('A partial older-format publication needs operator review.')
    if delivery.get('plan_hash') and delivery['plan_hash'] != fingerprint:
        raise UncertainRequest('The post content changed during a partial publication; inspect it before resuming.')
    if delivery.get('channel_id') and delivery['channel_id'] != chat['id']:
        raise UncertainRequest('The destination changed during publication.')
    delivery.update(format=POST_FORMAT,channel_id=chat['id'],bot_id=me['id'],plan_hash=fingerprint)
    delivery.setdefault('posts',{})
    record['telegram'] = delivery
    for step in plan['posts']:
        post = delivery['posts'].setdefault(step['key'],{})
        if post.get('status') == 'sent':
            continue
        if post.get('status') in ['in_flight','uncertain']:
            raise UncertainRequest('A previous post has an unknown outcome; inspect the channel before retrying.')
        post['status'] = delivery['status'] = 'in_flight'
        save(record_path,record)
        files = {name:ROOT/path for name,path in step.get('files',{}).items()} or None
        try:
            result = telegram(step['method'],{'chat_id':str(chat['id']),**step['data']},files)
            if not isinstance(result,dict) or result.get('chat',{}).get('id') != chat['id'] or not result.get('message_id'):
                raise UncertainRequest('Unexpected Telegram delivery response; inspect the channel.')
        except APIError:
            post['status'],delivery['status'] = 'rejected','partial'
            save(record_path,record)
            raise
        except Exception:
            post['status'] = delivery['status'] = 'uncertain'
            save(record_path,record)
            raise
        post.update(status='sent',message_id=result['message_id'])
        delivery['message_ids'] = [delivery['posts'][s['key']]['message_id'] for s in plan['posts'] if delivery['posts'].get(s['key'],{}).get('status') == 'sent']
        delivery['status'] = 'partial'
        save(record_path,record)
        if step is not plan['posts'][-1]:
            time.sleep(1.1)
    delivery.update(status='sent',sent_at=dt.datetime.now(dt.timezone.utc).isoformat())
    save(record_path,record)
    print('Published four posts to',config['channel'],'message IDs:',delivery['message_ids'])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','publish','check'])
    parser.add_argument('--issue',type=dt.date.fromisoformat)
    parser.add_argument('--scheduled',action='store_true')
    args = parser.parse_args()
    config = json.loads((CONFIG_DIR/'publishing.json').read_text())
    STATE.mkdir(parents=True,exist_ok=True)
    with (STATE/'publisher.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.action == 'check':
            me,chat = check_bot(config)
            print('Bot:',me['username'],'channel:',chat.get('username',chat['id']),'posting permission verified.')
        elif not args.issue:
            parser.error('--issue is required for publication')
        elif args.action == 'prepare':
            prepare(args.issue.isoformat())
        else:
            publish(args.issue.isoformat(),config,args.scheduled)

if __name__ == '__main__':
    main()
