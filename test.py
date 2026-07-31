#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""虎牙登录全链路诊断脚本 — 在 GitHub Actions 中运行，把输出全部贴回来"""

import os
import sys
import json
import time
import traceback

# ======================== 0. 环境信息 ========================
print("=" * 60)
print("[DIAG] 环境信息")
print("=" * 60)
print(f"Python:          {sys.version}")
print(f"CHROME_BIN:      {os.getenv('CHROME_BIN', '未设置')}")
print(f"CHROMEDRIVER_BIN:{os.getenv('CHROMEDRIVER_BIN', '未设置')}")
print(f"CHROMEWEBDRIVER: {os.getenv('CHROMEWEBDRIVER', '未设置')}")

for p in ["/usr/bin/google-chrome", "/usr/bin/chromium-browser",
          "/usr/local/bin/chromedriver",
          os.path.join(os.getenv("CHROMEWEBDRIVER", ""), "chromedriver"),
          "/usr/local/share/chrome_driver/chromedriver"]:
    print(f"  存在 {p}: {os.path.isfile(p)}")

# ======================== 1. 读取配置 ========================
print("\n" + "=" * 60)
print("[DIAG] config.py 配置")
print("=" * 60)
try:
    import config as cfg
    print(f"URLS:       {json.dumps(cfg.URLS, ensure_ascii=False, indent=2)}")
    print(f"LOGIN:      {json.dumps(cfg.LOGIN, ensure_ascii=False, indent=2)}")
except Exception as e:
    print(f"[ERROR] 无法导入 config: {e}")
    cfg = None

# ======================== 2. Cookie 解析 ========================
print("\n" + "=" * 60)
print("[DIAG] Cookie 解析")
print("=" * 60)
raw_cookie = os.getenv("HUYA_COOKIE", "")
print(f"原始长度: {len(raw_cookie)}")
print(f"原始前80字符: {raw_cookie[:80]}...")

pairs = []
for seg in raw_cookie.split(";"):
    seg = seg.strip()
    if not seg or "=" not in seg:
        continue
    k, v = seg.split("=", 1)
    pairs.append((k.strip(), v.strip()))

print(f"有效键值对数: {len(pairs)}")
for k, v in pairs:
    print(f"  {k} = {v[:20]}{'...' if len(v) > 20 else ''}")

# 关键 cookie 检查
key_names = {"yyeuid", "yyepwd", "udb_biztoken", "udb_uid", "huya_ua"}
found = {k for k, _ in pairs}
missing = key_names - found
print(f"关键cookie缺失: {missing if missing else '无'}")

# ======================== 3. 启动浏览器 ========================
print("\n" + "=" * 60)
print("[DIAG] 启动浏览器")
print("=" * 60)

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-dev-shm-usage")
opts.add_argument("--disable-gpu")
opts.add_argument("--disable-extensions")
opts.add_argument("--disable-background-networking")
opts.add_argument("--disable-sync")
opts.add_argument("--no-first-run")
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--disable-blink-features=AutomationControlled")
opts.add_argument("--blink-settings=imagesEnabled=false")
opts.add_argument(
    "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

binary = os.getenv("CHROME_BIN", "/usr/bin/google-chrome")
if os.path.isfile(binary):
    opts.binary_location = binary
    print(f"浏览器路径: {binary}")

driver_path = (
    os.getenv("CHROMEDRIVER_BIN")
    or os.path.join(os.getenv("CHROMEWEBDRIVER", ""), "chromedriver")
    or "/usr/local/share/chrome_driver/chromedriver"
)
print(f"驱动路径:   {driver_path}")

try:
    driver = webdriver.Chrome(service=Service(driver_path), options=opts)
    driver.set_page_load_timeout(120)
    driver.set_script_timeout(60)
    print("[OK] 浏览器启动成功")
except Exception as e:
    print(f"[FATAL] 浏览器启动失败: {e}")
    traceback.print_exc()
    sys.exit(1)

# ======================== 4. 访问轻量页 + 注入 Cookie ========================
print("\n" + "=" * 60)
print("[DIAG] 注入 Cookie")
print("=" * 60)

try:
    t0 = time.time()
    driver.get("https://www.huya.com/robots.txt")
    print(f"[OK] robots.txt 加载 ({time.time()-t0:.1f}s), title={driver.title!r}")
except Exception as e:
    print(f"[WARN] robots.txt 加载异常: {e}")

injected = 0
failed = 0
for k, v in pairs:
    try:
        driver.add_cookie({"name": k, "value": v, "domain": ".huya.com", "path": "/"})
        injected += 1
    except Exception as e:
        print(f"  [FAIL] {k}: {e}")
        failed += 1

print(f"[OK] 注入成功 {injected} 条, 失败 {failed} 条")
print(f"[OK] 浏览器实际持有 cookie 数: {len(driver.get_cookies())}")
for c in driver.get_cookies():
    print(f"  {c['name']} (domain={c.get('domain','?')})")

# ======================== 5. 访问用户中心 ========================
print("\n" + "=" * 60)
print("[DIAG] 访问用户中心")
print("=" * 60)

target_url = cfg.URLS["user_index"] if cfg else "https://www.huya.com/u"
print(f"目标URL: {target_url}")

try:
    t0 = time.time()
    driver.get(target_url)
    elapsed = time.time() - t0
    print(f"[OK] 页面加载完成 ({elapsed:.1f}s)")
except TimeoutException:
    print("[WARN] 页面加载超时(120s)，尝试继续分析...")
except Exception as e:
    print(f"[ERROR] 页面加载异常: {e}")

print(f"最终URL:   {driver.current_url}")
print(f"页面Title: {driver.title}")

# ======================== 6. 页面内容分析 ========================
print("\n" + "=" * 60)
print("[DIAG] 页面内容分析")
print("=" * 60)

src = driver.page_source
print(f"页面HTML长度: {len(src)}")

checks = {
    "包含'登录'":   "登录" in src,
    "包含'注册'":   "注册" in src,
    "包含'我的'":   "我的" in src,
    "包含'个人中心'": "个人中心" in src,
    "包含'虎粮'":   "虎粮" in src,
    "包含'uid'":    "uid" in src.lower(),
    "被重定向到login": "login" in driver.current_url.lower(),
    "被重定向到captcha": "captcha" in driver.current_url.lower() or "verify" in driver.current_url.lower(),
}
for label, hit in checks.items():
    print(f"  {'✅' if hit else '❌'} {label}")

# 打印前2000字符帮助判断
print(f"\n--- 页面前2000字符 ---\n{src[:2000]}\n--- END ---")

# ======================== 7. 目标元素检测 ========================
print("\n" + "=" * 60)
print("[DIAG] 目标登录态元素检测")
print("=" * 60)

if cfg:
    elem_id = cfg.LOGIN.get("huya_num", "")
    print(f"等待元素 ID: {elem_id!r}")
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, elem_id))
        )
        print(f"[OK] 找到 #{elem_id}，登录态有效 ✅")
    except TimeoutException:
        print(f"[FAIL] 15s 内未找到 #{elem_id} ❌")
        # 尝试用其他方式找登录态
        alt_selectors = [
            (By.CSS_SELECTOR, ".user-name"),
            (By.CSS_SELECTOR, ".nick-name"),
            (By.CSS_SELECTOR, "[class*='user']"),
            (By.CSS_SELECTOR, "[class*='nick']"),
            (By.CSS_SELECTOR, "[class*='avatar']"),
        ]
        for by, sel in alt_selectors:
            try:
                els = driver.find_elements(by, sel)
                if els:
                    print(f"  [ALT] 找到 {sel} x{len(els)}, text={els[0].text[:50]!r}")
            except Exception:
                pass
else:
    print("[SKIP] 无 config，跳过元素检测")

# ======================== 8. 截图 ========================
print("\n" + "=" * 60)
print("[DIAG] 截图")
print("=" * 60)
try:
    driver.save_screenshot("debug_screenshot.png")
    print("[OK] 已保存 debug_screenshot.png")
except Exception as e:
    print(f"[WARN] 截图失败: {e}")

# ======================== 9. 清理 ========================
driver.quit()
print("\n[DIAG] 诊断完成")
