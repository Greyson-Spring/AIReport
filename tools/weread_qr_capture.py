"""用Playwright连接已运行的Chrome, 确保显示微信读书登录二维码, 输出base64截图
用法: python3 weread_qr_capture.py <port>
输出: base64编码的PNG(仅输出图片, 无其他干扰)
"""
import sys
import base64
from playwright.sync_api import sync_playwright

port = sys.argv[1] if len(sys.argv) > 1 else '9222'


def main():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        # 1. 打开微信读书首页
        page.goto("https://weread.qq.com/", timeout=30000)
        page.wait_for_timeout(4000)
        # 2. 点登录
        try:
            page.click("text=登录", timeout=8000)
        except Exception:
            pass
        # 3. 等二维码(图片)出现
        page.wait_for_selector("img", timeout=15000)
        page.wait_for_timeout(3000)
        # 4. 截图并输出base64
        img = page.screenshot()
        sys.stdout.buffer.write(base64.b64encode(img))
        sys.stdout.flush()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        sys.stderr.write(str(e))
        sys.exit(1)
