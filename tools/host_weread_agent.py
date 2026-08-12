"""宿主机 weread 采集代理
作用: 通过CDP连到宿主机已登录的Edge(微信读书), 在阅读器页执行fetch抓文章列表,
      以HTTP接口暴露给Docker容器内的WeRSS采集器调用。

启动: python host_weread_agent.py
前置: 宿主机Edge以调试模式运行(--remote-debugging-port=9222 --remote-allow-origins=*),
      并且登录了微信读书、打开着阅读器页。
"""
import json
import time
import urllib.request
import urllib.parse
import websocket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CDP_BASE = 'http://localhost:9222'
READER_PATH = '/web/mp/reader/'
# 阅读器页URL(任意一个公众号的阅读器页即可查询所有公众号)
READER_URL = 'https://weread.qq.com/web/mp/reader/1b742a6224d505f5758535f33303831363733383033e66'
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


def open_reader_page():
    """自动打开一个阅读器页(用 /json/new 新建标签页)"""
    url = CDP_BASE + '/json/new?' + urllib.parse.quote(READER_URL, safe='')
    req = urllib.request.Request(url, method='PUT')
    req.add_header('Host', 'localhost:9222')
    try:
        tab = json.loads(urllib.request.urlopen(req, timeout=8).read())
        time.sleep(7)  # 等页面加载
        return tab
    except Exception:
        return None


def recover_page(tab):
    """刷新(重载)阅读器页，解决页面卡住/无响应的问题"""
    try:
        ws_url = 'ws://localhost:9222/devtools/page/' + tab['id']
        ws = websocket.create_connection(ws_url, timeout=10)
        ws.settimeout(10)
        ws.send(json.dumps({'id': 1, 'method': 'Page.navigate', 'params': {'url': READER_URL}}))
        time.sleep(7)  # 等重载完成
        ws.close()
        return True
    except Exception:
        return False


def _do_fetch(book_id, offset):
    """单次抓取, 返回 (结果文本, 阅读器页tab或None)"""
    tab = find_reader_page()
    if not tab:
        return json.dumps({'errCode': 'NO_READER_PAGE',
                           'errMsg': '没有找到微信读书阅读器页'}), None
    ws_url = 'ws://localhost:9222/devtools/page/' + tab['id']
    try:
        ws = websocket.create_connection(ws_url, timeout=30)
        ws.settimeout(30)
    except Exception as e:
        return json.dumps({'errCode': 'CDP_CONNECT_FAIL', 'errMsg': str(e)}), tab
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
    return text, tab


def fetch_articles(book_id, offset=0):
    """带自动恢复的抓取: 页面卡住→刷新重试, 没有页面→自动打开"""
    text, tab = _do_fetch(book_id, offset)
    try:
        err = json.loads(text).get('errCode')
    except Exception:
        err = None

    # 需要恢复的情况: 页面无响应 / 连接失败 / 页面执行异常 / 没有阅读器页
    if err in ('CDP_RECV_FAIL', 'CDP_CONNECT_FAIL', 'EVAL_ERROR', 'NO_READER_PAGE'):
        if tab:
            print(f'[weread-agent] 页面异常({err}), 刷新阅读器页后重试...')
            recover_page(tab)
        else:
            print('[weread-agent] 没有阅读器页, 自动打开一个...')
            open_reader_page()
        time.sleep(2)
        text, _ = _do_fetch(book_id, offset)
    return text


def capture_screenshot():
    """截取浏览器当前画面(用于微信读书扫码登录)"""
    import base64
    tab = find_reader_page()
    if not tab:
        try:
            for t in get_tabs():
                if t.get('type') == 'page':
                    tab = t
                    break
        except Exception:
            pass
    if not tab:
        return None
    ws_url = 'ws://localhost:9222/devtools/page/' + tab['id']
    try:
        ws = websocket.create_connection(ws_url, timeout=10)
        ws.settimeout(10)
        ws.send(json.dumps({'id': 1, 'method': 'Page.captureScreenshot',
                            'params': {'format': 'png'}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get('id') == 1:
                data = msg.get('result', {}).get('data')
                ws.close()
                return base64.b64decode(data) if data else None
    except Exception:
        pass
    return None


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
        if self.path.startswith('/qr'):
            # 截取浏览器画面(微信读书登录二维码)返回给浏览器查看
            img = capture_screenshot()
            if img:
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Content-Length', str(len(img)))
                self.end_headers()
                self.wfile.write(img)
            else:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'screenshot failed')
        else:
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
