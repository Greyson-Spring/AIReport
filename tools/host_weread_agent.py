"""宿主机 weread 采集代理
作用: 通过CDP连到宿主机已登录的Edge(微信读书), 在阅读器页执行fetch抓文章列表,
      以HTTP接口暴露给Docker容器内的WeRSS采集器调用。

启动: python host_weread_agent.py
前置: 宿主机Edge以调试模式运行(--remote-debugging-port=9222 --remote-allow-origins=*),
      并且登录了微信读书、打开着阅读器页。
"""
import json
import urllib.request
import websocket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CDP_BASE = 'http://localhost:9222'
READER_PATH = '/web/mp/reader/'
AGENT_PORT = 9000


def get_tabs():
    req = urllib.request.Request(CDP_BASE + '/json')
    req.add_header('Host', 'localhost:9222')
    return json.loads(urllib.request.urlopen(req, timeout=5).read())


def find_reader_page():
    try:
        for t in get_tabs():
            if READER_PATH in (t.get('url') or ''):
                return t
    except Exception as e:
        return None
    return None


def fetch_articles(book_id, offset=0):
    tab = find_reader_page()
    if not tab:
        return json.dumps({'errCode': 'NO_READER_PAGE',
                           'errMsg': '没有找到微信读书阅读器页，请先在Edge中打开阅读器页'})
    ws_url = 'ws://localhost:9222/devtools/page/' + tab['id']
    try:
        ws = websocket.create_connection(ws_url, timeout=30)
        ws.settimeout(30)
    except Exception as e:
        return json.dumps({'errCode': 'CDP_CONNECT_FAIL', 'errMsg': str(e)})
    js = ("fetch('/web/mp/articles?bookId=%s&offset=%d',{credentials:'include'})"
          ".then(r=>r.text())" % (book_id, int(offset)))
    try:
        ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate', 'params': {
            'expression': js, 'awaitPromise': True, 'returnByValue': True}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get('id') == 1:
                res = msg.get('result', {}).get('result', {})
                if res.get('exceptionDetails'):
                    text = json.dumps({'errCode': 'EVAL_ERROR',
                                       'errMsg': res['exceptionDetails'].get('text', '')})
                else:
                    text = res.get('value', '')
                break
    except Exception as e:
        text = json.dumps({'errCode': 'CDP_RECV_FAIL', 'errMsg': str(e)})
    finally:
        try:
            ws.close()
        except Exception:
            pass
    return text


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
            book_id = str(body.get('book_id', ''))
            offset = int(body.get('offset', 0))
            result = fetch_articles(book_id, offset)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(result.encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'errCode': 'AGENT_ERROR', 'errMsg': str(e)}).encode('utf-8'))

    def do_GET(self):
        # 健康检查
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'weread-agent ok')

    def log_message(self, fmt, *args):
        print('[weread-agent] ' + (fmt % args))


if __name__ == '__main__':
    print(f'宿主机 weread 采集代理启动, 监听端口 {AGENT_PORT}...')
    print(f'CDP: {CDP_BASE} (需Edge以调试模式运行并打开阅读器页)')
    ThreadingHTTPServer(('0.0.0.0', AGENT_PORT), Handler).serve_forever()
