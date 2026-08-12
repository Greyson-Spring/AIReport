"""一键手动更新所有公众号文章(通过消息任务触发)"""
import json
import os
import re
import sys
import urllib.request

BASE = 'http://localhost:8001/api/v1/wx'


def http(method, path, token=None, data=None, raw=False):
    headers = {}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    body = None
    if data is not None:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(data).encode()
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    resp = urllib.request.urlopen(req, timeout=90).read().decode('utf-8')
    return resp if raw else json.loads(resp)


def load_credentials():
    """从 ../.env 读取账号密码"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    user, pwd = 'admin', 'admin@123'
    try:
        with open(env_path, encoding='utf-8') as f:
            for line in f:
                m = re.match(r'(USERNAME|PASSWORD)\s*=\s*(.+)', line.strip())
                if m:
                    key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
                    if key == 'USERNAME':
                        user = val
                    else:
                        pwd = val
    except Exception:
        pass
    return user, pwd


def main():
    user, pwd = load_credentials()
    # 登录
    login = urllib.request.Request(
        BASE + '/auth/login',
        data=f'username={urllib.parse.quote(user)}&password={urllib.parse.quote(pwd)}'.encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'})
    token = json.loads(urllib.request.urlopen(login, timeout=30).read())['data']['access_token']
    print('[1/3] 登录成功')

    # 找"12h自动抓全部"任务
    tasks = http('GET', '/message_tasks', token)['data']
    if isinstance(tasks, dict):
        tasks = tasks.get('list', [])
    task = next((t for t in tasks if '12h' in (t.get('name') or '')), None)
    if not task:
        print('!! 没找到 12h-auto-fetch-all 任务')
        sys.exit(1)
    print(f'[2/3] 触发任务: {task.get("name")} (抓取所有公众号)')

    http('GET', '/message_tasks/' + task['id'] + '/run?isTest=false', token)
    print('[3/3] 已触发! 抓取在后台进行, 约需1-2分钟。')
    print('     之后打开网站 http://localhost:8001 查看文章是否更新。')


if __name__ == '__main__':
    import urllib.parse
    main()
