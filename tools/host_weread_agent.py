"""宿主机 weread 采集代理 (多账号池版)
作用: 通过CDP连到宿主机多个已登录的Chrome(微信读书), 在阅读器页执行fetch抓文章列表,
      支持账号池: 按公众号bookId哈希分摊到不同账号(Chrome端口), 并记录每账号错误状态。

启动: python host_weread_agent.py
账号: 通过环境变量 WEREAD_PORTS 指定Chrome端口, 如 WEREAD_PORTS=9222,9223
前置: 每个账号的Chrome以调试模式运行(--remote-debugging-port=<port> --remote-allow-origins=*),
      且登录了微信读书、打开着阅读器页。
"""
import json
import os
import sys
import time
import zlib
import urllib.request
import urllib.parse
import websocket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ===== 账号池配置 =====
CHROME_PORTS = [int(p) for p in os.environ.get('WEREAD_PORTS', '9222,9223').split(',') if p.strip()]
# 每个账号的状态: {port: {status, last_error, error_count, last_ok}}
ACCOUNT_STATUS = {
    p: {'status': 'unknown', 'last_error': '', 'error_count': 0, 'last_ok': 0, 'port': p}
    for p in CHROME_PORTS
}

READER_PATH = '/web/mp/reader/'
READER_URL = 'https://weread.qq.com/web/mp/reader/1b742a6224d505f5758535f33303831363733383033e66'
AGENT_PORT = 9000

# ===== 账号路由 =====
def cdp_base(port):
    return f'http://localhost:{port}'

def host_header(port):
    return f'localhost:{port}'

def pick_port(book_id):
    """按公众号bookId哈希(crc32, 稳定)分摊到账号池中的某个账号"""
    if not CHROME_PORTS:
        return None
    idx = zlib.crc32(str(book_id).encode('utf-8')) % len(CHROME_PORTS)
    return CHROME_PORTS[idx]

# ===== CDP 基础操作(带端口) =====
def get_tabs(port):
    req = urllib.request.Request(cdp_base(port) + '/json')
    req.add_header('Host', host_header(port))
    return json.loads(urllib.request.urlopen(req, timeout=5).read())

def find_reader_page(port):
    try:
        for t in get_tabs(port):
            if READER_PATH in (t.get('url') or ''):
                return t
    except Exception:
        return None
    return None

def find_any_page(port):
    try:
        for t in get_tabs(port):
            if t.get('type') == 'page':
                return t
    except Exception:
        pass
    return None

def reader_url_for(book_id=None):
    """阅读器页地址: 一律用写死的有效链接。
    注意: 用bookId拼的 /web/mp/reader/MP_WXS_xxx 对微信读书无效, 会跳走, 不能再用来开阅读器页"""
    return READER_URL

def open_reader_page(port, book_id=None):
    url = cdp_base(port) + '/json/new?' + urllib.parse.quote(reader_url_for(book_id), safe='')
    req = urllib.request.Request(url, method='PUT')
    req.add_header('Host', host_header(port))
    try:
        tab = json.loads(urllib.request.urlopen(req, timeout=8).read())
        time.sleep(7)
        return tab
    except Exception:
        return None

def recover_page(port, tab, book_id=None):
    try:
        ws_url = f'ws://localhost:{port}/devtools/page/' + tab['id']
        ws = websocket.create_connection(ws_url, timeout=10)
        ws.settimeout(10)
        ws.send(json.dumps({'id': 1, 'method': 'Page.navigate',
                            'params': {'url': reader_url_for(book_id)}}))
        time.sleep(7)
        ws.close()
        return True
    except Exception:
        return False

def _do_fetch(book_id, offset, port):
    tab = find_reader_page(port)
    if not tab:
        return json.dumps({'errCode': 'NO_READER_PAGE',
                           'errMsg': '没有找到微信读书阅读器页'}), None
    ws_url = f'ws://localhost:{port}/devtools/page/' + tab['id']
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

def _do_fetch_content(review_id, port):
    """在已登录的Chrome阅读器页里执行 fetch('/web/mp/content'), 拿文章正文HTML
    (不依赖WEREAD_COOKIE, 直接用Chrome的微信读书登录会话)"""
    tab = find_reader_page(port)
    if not tab:
        return json.dumps({'errCode': 'NO_READER_PAGE',
                           'errMsg': '没有找到微信读书阅读器页'}), None
    ws_url = f'ws://localhost:{port}/devtools/page/' + tab['id']
    try:
        ws = websocket.create_connection(ws_url, timeout=30)
        ws.settimeout(30)
    except Exception as e:
        return json.dumps({'errCode': 'CDP_CONNECT_FAIL', 'errMsg': str(e)}), tab
    js = ("fetch('/web/mp/content?reviewId=%s',{credentials:'include'})"
          ".then(r=>r.text())" % review_id)
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

def fetch_content(review_id, port_override=None):
    """按reviewId抓取文章正文, 账号报错时自动换下一个账号"""
    ports = [int(port_override)] if port_override else list(CHROME_PORTS)
    if not ports:
        return json.dumps({'errCode': 'NO_ACCOUNT', 'errMsg': '没有配置任何账号'})
    last_text = None
    for port in ports:
        text, tab = _do_fetch_content(review_id, port)
        # 页面异常 → 刷新后重试一次
        if text and 'NO_READER_PAGE' in text:
            if tab:
                print(f'[weread-agent] 账号{port} 无阅读器页, 刷新后重试...')
                recover_page(port, tab, None)
            else:
                print(f'[weread-agent] 账号{port} 自动打开阅读器页...')
                open_reader_page(port)
            time.sleep(2)
            text, _ = _do_fetch_content(review_id, port)
        # 拿到非错误包装的内容即返回
        if text and 'errCode' not in text and 'errMsg' not in text:
            return text
        last_text = text
    return last_text

def record_error(port, text):
    """记录账号的最近错误状态(供前端展示)"""
    try:
        d = json.loads(text)
        err = d.get('errCode')
        st = ACCOUNT_STATUS[port]
        if 'reviews' in d:
            st['status'] = 'ok'
            st['last_error'] = ''
            st['last_ok'] = int(time.time())
            st['error_count'] = 0
        elif isinstance(err, int):
            st['status'] = 'error'
            st['last_error'] = str(err)
            st['error_count'] = st.get('error_count', 0) + 1
        elif err in ('CDP_CONNECT_FAIL', 'CDP_RECV_FAIL'):
            st['status'] = 'chrome_down'
            st['last_error'] = str(err)
        elif err == 'NO_READER_PAGE':
            st['status'] = 'no_reader'
            st['last_error'] = 'NO_READER_PAGE'
        elif err == 'EVAL_ERROR':
            st['status'] = 'error'
            st['last_error'] = 'EVAL_ERROR'
        else:
            st['status'] = 'unknown'
            st['last_error'] = str(err or '')
    except Exception:
        pass

RETRY_ERR_CODES = {-2010, -2012, -2014, -2041}  # 认证/限流类错误, 换账号重试有效

def fetch_articles(book_id, offset=0, port_override=None):
    # 确定尝试的账号: 指定端口或按哈希路由的端口; 失败的账号会尝试下一个(自动failover)
    ports = [int(port_override)] if port_override else list(CHROME_PORTS)
    if not ports:
        return json.dumps({'errCode': 'NO_ACCOUNT', 'errMsg': '没有配置任何账号'})
    last_text = None
    for port in ports:
        text, tab = _do_fetch(book_id, offset, port)
        try:
            err = json.loads(text).get('errCode')
        except Exception:
            err = None
        # 页面异常 → 刷新重试一次(打开写死的有效阅读器页)
        if err in ('CDP_RECV_FAIL', 'CDP_CONNECT_FAIL', 'EVAL_ERROR', 'NO_READER_PAGE'):
            if tab:
                print(f'[weread-agent] 账号{port} 页面异常({err}), 刷新后重试...')
                recover_page(port, tab, book_id)
            else:
                print(f'[weread-agent] 账号{port} 没有阅读器页, 自动打开...')
                open_reader_page(port, book_id)
            time.sleep(2)
            text, _ = _do_fetch(book_id, offset, port)
            try:
                err = json.loads(text).get('errCode')
            except Exception:
                err = None
        record_error(port, text)
        # 成功 → 返回
        if 'reviews' in text:
            return text
        last_text = text
        # 认证/限流类错误 → 换下一个账号(自动failover)
        if isinstance(err, int) and err in RETRY_ERR_CODES:
            print(f'[weread-agent] 账号{port} 错误({err}), 自动换下一个账号尝试...')
            continue
        # 其他错误(-2003 bookId无效等)换账号也没用 → 停止
        break
    return last_text

def navigate_page(port, url):
    """导航某个账号的Chrome到指定URL(用于刷新登录页拿新二维码)"""
    tab = find_reader_page(port) or find_any_page(port)
    if not tab:
        try:
            u = cdp_base(port) + '/json/new?' + urllib.parse.quote(url, safe='')
            req = urllib.request.Request(u, method='PUT')
            req.add_header('Host', host_header(port))
            tab = json.loads(urllib.request.urlopen(req, timeout=8).read())
            time.sleep(8)
            return {'ok': True, 'url': url, 'opened': True}
        except Exception as e:
            return {'err': str(e)}
    try:
        ws_url = f'ws://localhost:{port}/devtools/page/' + tab['id']
        ws = websocket.create_connection(ws_url, timeout=10)
        ws.settimeout(10)
        ws.send(json.dumps({'id': 1, 'method': 'Page.navigate', 'params': {'url': url}}))
        time.sleep(8)  # 等页面加载
        ws.close()
        return {'ok': True, 'url': url}
    except Exception as e:
        return {'err': str(e)}


def click_element(port, text):
    import json as _json
    tab = find_reader_page(port) or find_any_page(port)
    if not tab:
        return _json.dumps({'err': 'no page tab'})
    ws_url = f'ws://localhost:{port}/devtools/page/' + tab['id']
    try:
        ws = websocket.create_connection(ws_url, timeout=10)
        ws.settimeout(10)
        js = (
            "(() => {"
            "const t = " + _json.dumps(text) + ";"
            "const els = [...document.querySelectorAll('*')].filter(e => e.children.length===0 && e.textContent.trim()===t);"
            "if (els.length) { els[0].click(); return 'clicked: '+t; }"
            "const els2 = [...document.querySelectorAll('*')].filter(e => e.children.length===0 && e.textContent.includes(t));"
            "if (els2.length) { els2[0].click(); return 'clicked(contains): '+t; }"
            "return 'not found: '+t;"
            "})()"
        )
        ws.send(_json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                             'params': {'expression': js, 'returnByValue': True}}))
        while True:
            m = _json.loads(ws.recv())
            if m.get('id') == 1:
                ws.close()
                return _json.dumps({'result': m.get('result', {}).get('result', {}).get('value')})
    except Exception as e:
        return _json.dumps({'err': str(e)})

def qr_with_playwright(port):
    """用Playwright连接Chrome, 可靠等二维码出现并截图(子进程方式, 避免多线程问题)"""
    import subprocess
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'weread_qr_capture.py')
    try:
        r = subprocess.run([sys.executable, script, str(port)],
                           capture_output=True, timeout=45)
        if r.returncode == 0 and r.stdout:
            import base64
            return base64.b64decode(r.stdout)
    except Exception:
        pass
    return None


def ensure_login_qr(port):
    """确保某账号Chrome显示微信读书登录二维码, 返回新鲜截图
    (先导航到微信读书首页, 点登录打开二维码, 等待后截图)"""
    # 1. 若页面不是weread, 导航到首页
    try:
        found = False
        for t in get_tabs(port):
            if t.get('type') == 'page':
                found = True
                if 'weread.qq.com' not in (t.get('url') or ''):
                    navigate_page(port, 'https://weread.qq.com/')
                break
        if not found:
            navigate_page(port, 'https://weread.qq.com/')
    except Exception:
        pass
    # 2. 点"登录"打开二维码弹窗(重试直到截到有内容的画面)
    last_img = None
    for _ in range(3):
        click_element(port, '登录')
        time.sleep(5)  # 等二维码加载
        last_img = capture_screenshot(port)
        if last_img and len(last_img) > 20000:
            break  # 有实际内容(二维码/登录页), 返回
    # 3. 返回截图(可能是二维码, 也可能是登录页, 前端每3秒刷新可再次触发)
    return last_img


def capture_screenshot(port):
    import base64
    tab = find_reader_page(port) or find_any_page(port)
    if not tab:
        return None
    ws_url = f'ws://localhost:{port}/devtools/page/' + tab['id']
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

def check_chrome_alive(port):
    """检测某账号的Chrome是否在运行"""
    try:
        req = urllib.request.Request(cdp_base(port) + '/json')
        req.add_header('Host', host_header(port))
        urllib.request.urlopen(req, timeout=3).read()
        return True
    except Exception:
        return False

def spawn_chrome(port=None):
    """启动一个新Chrome账号(添加账号用). 返回 {port, profile} 或 {err}"""
    import subprocess, shutil
    if port is None:
        used = set(CHROME_PORTS)
        port = 9222
        while port in used:
            port += 1
    chrome = (shutil.which('google-chrome') or shutil.which('chromium')
              or shutil.which('chromium-browser'))
    if not chrome:
        return {'err': 'no chrome binary found'}
    profile = os.path.expanduser(f'~/.weread-chrome-{port}')
    env = dict(os.environ)
    # 强制用服务器上的虚拟显示(Xvfb :99), 避免MobaXterm等X转发把Chrome弹到用户电脑上
    env['DISPLAY'] = ':99'
    cmd = [chrome, f'--remote-debugging-port={port}', '--remote-allow-origins=*',
           f'--user-data-dir={profile}', '--no-sandbox', '--disable-dev-shm-usage',
           'https://weread.qq.com/']
    # 启动并验证Chrome真的初始化了(重试3次)
    last = None
    for attempt in range(3):
        try:
            subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            return {'err': str(e)}
        time.sleep(8)
        if check_chrome_alive(port):
            last = 'ok'
            break
        # 没起来: 杀进程删配置重试(可能是损坏的profile)
        try:
            subprocess.run(['pkill', '-f', f'remote-debugging-port={port}'],
                           capture_output=True, timeout=5)
        except Exception:
            pass
        time.sleep(2)
        if os.path.exists(profile):
            import shutil as _sh
            _sh.rmtree(profile, ignore_errors=True)
    if last != 'ok':
        return {'err': f'Chrome启动失败(端口{port}), 已重试3次'}
    if port not in CHROME_PORTS:
        CHROME_PORTS.append(port)
        ACCOUNT_STATUS[port] = {'status': 'unknown', 'last_error': '',
                                'error_count': 0, 'last_ok': 0, 'port': port}
    return {'port': port, 'profile': profile}

def remove_chrome(port):
    """停止一个Chrome账号并删除其用户数据(登录态). 返回 {removed: port}"""
    import subprocess
    import time
    import shutil
    try:
        subprocess.run(['pkill', '-9', '-f', f'remote-debugging-port={port}'],
                       capture_output=True, timeout=10)
    except Exception:
        pass
    # 等进程完全退出释放文件句柄(渲染进程较多, 1秒不够, 多等一会)
    time.sleep(3)
    profile = os.path.expanduser(f'~/.weread-chrome-{port}')
    if os.path.exists(profile):
        # 删除失败重试几次(Chrome进程未完全释放时rmtree会失败)
        for attempt in range(3):
            try:
                shutil.rmtree(profile)
                break
            except Exception:
                time.sleep(2)
        if os.path.exists(profile):
            print(f'[weread-agent] 警告: 账号{port}用户数据删除不完整({profile})')
        else:
            print(f'[weread-agent] 已删除账号{port}的用户数据({profile})')
    if port in CHROME_PORTS:
        CHROME_PORTS.remove(port)
    ACCOUNT_STATUS.pop(port, None)
    return {'removed': port}

# ===== HTTP 接口 =====
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
            if self.path.startswith('/spawn'):
                result = spawn_chrome()
            elif self.path.startswith('/remove'):
                port = int(body.get('port', 0))
                result = remove_chrome(port)
            elif self.path.startswith('/content'):
                # 抓文章正文: 在已登录Chrome里 fetch /web/mp/content?reviewId=...
                review_id = str(body.get('review_id', ''))
                port_override = int(body['port']) if body.get('port') else None
                result = fetch_content(review_id, port_override)
            else:
                book_id = str(body.get('book_id', ''))
                offset = int(body.get('offset', 0))
                port_override = int(body['port']) if body.get('port') else None
                result = fetch_articles(book_id, offset, port_override)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            if isinstance(result, str):
                self.wfile.write(result.encode('utf-8'))
            else:
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'errCode': 'AGENT_ERROR', 'errMsg': str(e)}).encode('utf-8'))

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if self.path.startswith('/status'):
            # 账号池状态(供前端展示)
            result = {}
            for port in CHROME_PORTS:
                st = dict(ACCOUNT_STATUS[port])
                st['chrome_alive'] = check_chrome_alive(port)
                result[str(port)] = st
            self._json_result(result)
        elif self.path.startswith('/qr'):
            # 优先用Playwright可靠出二维码; 失败退回CDP
            port = int(qs.get('port', [CHROME_PORTS[0]])[0])
            img = qr_with_playwright(port)
            if not img:
                img = ensure_login_qr(port)
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
        elif self.path.startswith('/navigate'):
            port = int(qs.get('port', [CHROME_PORTS[0]])[0])
            url = qs.get('url', ['https://weread.qq.com/'])[0]
            self._json_result(navigate_page(port, url))
        elif self.path.startswith('/click'):
            port = int(qs.get('port', [CHROME_PORTS[0]])[0])
            text = qs.get('text', ['扫码登录'])[0]
            self._json_result(click_element(port, text))
        elif self.path.startswith('/accounts'):
            # 账号列表
            self._json_result([{'port': p, **ACCOUNT_STATUS[p]} for p in CHROME_PORTS])
        else:
            # 健康检查
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'weread-agent ok')

    def _json_result(self, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print('[weread-agent] ' + (fmt % args))


if __name__ == '__main__':
    print(f'宿主机 weread 采集代理(账号池)启动, 监听端口 {AGENT_PORT}')
    print(f'账号(Chrome端口): {CHROME_PORTS}')
    print('状态查询: GET /status  账号列表: GET /accounts')
    ThreadingHTTPServer(('0.0.0.0', AGENT_PORT), Handler).serve_forever()
