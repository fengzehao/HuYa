#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
from urllib.parse import urlsplit

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config as cfg


class HuYaAuto:
    def __init__(self):
        self.enable_push = True
        self.msg_logs = []
        self.failed = False
        self.cookie_invalid = False

        self.cookie = os.getenv("HUYA_COOKIE", "").strip()
        self.rooms = list(cfg.ROOMS)
        self.send_key = os.getenv("SEND_KEY", "").strip()

        if not self.cookie:
            print("[ERROR] 未设置 HUYA_COOKIE")
            sys.exit(1)

        self.driver = self._init_browser()
        self.wait = WebDriverWait(self.driver, cfg.TIMING.get("wait", 20))

    # ------------------------------------------------------------------ 初始化
    def _init_browser(self):
        opts = Options()
        # eager：DOMContentLoaded 后就返回，避免被广告/统计脚本拖到超时
        opts.page_load_strategy = "eager"
        for arg in (
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
            "--no-first-run",
            "--window-size=1920,1080",
            "--lang=zh-CN",
            "--disable-blink-features=AutomationControlled",
            "--blink-settings=imagesEnabled=false",
        ):
            opts.add_argument(arg)

        binary_path = os.getenv("CHROME_BIN", "/usr/bin/google-chrome")
        if os.path.isfile(binary_path):
            opts.binary_location = binary_path

        # 优先用 Actions 自带 chromedriver；找不到则交给 Selenium Manager 自动处理
        driver_path = os.getenv("CHROMEDRIVER_BIN", "")
        if driver_path and os.path.isfile(driver_path):
            service = Service(driver_path)
        else:
            service = Service()

        driver = webdriver.Chrome(service=service, options=opts)
        driver.set_page_load_timeout(cfg.TIMING.get("page_load_timeout", 120))
        driver.set_script_timeout(30)

        try:
            driver.execute_cdp_cmd("Network.enable", {})
            driver.execute_cdp_cmd(
                "Network.setBlockedURLs",
                {"urls": ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp",
                          "*.woff", "*.woff2", "*.ttf", "*.mp4", "*.flv", "*.m3u8"]},
            )
            # 仅去掉 UA 里的 Headless 标记，保留真实版本号，避免和 sec-ch-ua 不一致
            ua = driver.execute_script("return navigator.userAgent")
            driver.execute_cdp_cmd(
                "Network.setUserAgentOverride",
                {"userAgent": ua.replace("HeadlessChrome", "Chrome")},
            )
        except WebDriverException as e:
            print(f"[WARN] CDP 初始化失败（可忽略）: {type(e).__name__}")
        return driver

    # ------------------------------------------------------------------ 工具
    def _open(self, url):
        """打开页面；超时则 window.stop() 后继续，不抛异常。（仅用于登录/打卡流程）"""
        try:
            self.driver.get(url)
        except TimeoutException:
            print(f"[WARN] 页面加载超时，已停止加载并继续: {urlsplit(url).netloc}")
            try:
                self.driver.execute_script("window.stop();")
            except WebDriverException:
                pass

    def _page_state(self):
        """返回不含敏感信息的页面状态，便于从日志判断失败原因。"""
        try:
            u = urlsplit(self.driver.current_url)
            ready = self.driver.execute_script("return document.readyState")
            body_len = self.driver.execute_script(
                "return document.body ? document.body.innerText.length : -1")
            return (f"url={u.netloc}{u.path} title={self.driver.title!r} "
                    f"readyState={ready} bodyTextLen={body_len}")
        except WebDriverException as e:
            return f"无法读取页面状态: {type(e).__name__}"

    def _looks_like_login_page(self):
        try:
            u = urlsplit(self.driver.current_url)
            hay = (u.netloc + u.path).lower()
            return any(k in hay for k in ("login", "passport", "udb"))
        except WebDriverException:
            return False

    # ------------------------------------------------------------------ 推送
    def send_notification(self):
        if not self.enable_push or not self.send_key:
            return
        print("[PUSH] 正在发送推送通知...")
        try:
            content = "\n\n".join(self.msg_logs) or "无输出"
            title = "虎牙-任务失败" if self.failed else "虎牙-任务成功"
            res = requests.post(
                f"https://sctapi.ftqq.com/{self.send_key}.send",
                data={"title": title, "desp": content},
                timeout=10,
            )
            tag = "SUCCESS" if res.status_code == 200 else "FAILED"
            print(f"[{tag}] 推送状态: {res.status_code}")
        except Exception as e:
            print(f"[ERROR] 推送异常: {type(e).__name__}")

    # ------------------------------------------------------------------ 登录
    def _inject_cookies(self):
        # add_cookie 要求当前已在 huya.com 域下，robots.txt 体积最小
        self._open("https://www.huya.com/robots.txt")
        self.driver.delete_all_cookies()
        ok = bad = 0
        for line in self.cookie.split(";"):
            if "=" not in line:
                continue
            name, val = line.split("=", 1)
            try:
                self.driver.add_cookie({
                    "name": name.strip(), "value": val.strip(),
                    "domain": ".huya.com", "path": "/",
                })
                ok += 1
            except WebDriverException:
                bad += 1
        print(f"[LOGIN] 已注入 {ok} 条 cookie" + (f"，{bad} 条失败" if bad else ""))

    def _logged_in(self, driver):
        try:
            return bool(driver.find_elements(By.ID, cfg.LOGIN["huya_num"]))
        except WebDriverException:
            return False

    def login(self, retries=3):
        print("[LOGIN] 正在登录...")
        for attempt in range(1, retries + 1):
            try:
                self._inject_cookies()
                self._open(cfg.URLS["user_index"])
                WebDriverWait(self.driver, cfg.TIMING.get("login_wait", 30)).until(self._logged_in)
                print("[SUCCESS] 登录成功")
                return True
            except TimeoutException:
                print(f"[WARN] 第 {attempt}/{retries} 次未检测到登录态 | {self._page_state()}")
                if self._looks_like_login_page():
                    self.cookie_invalid = True
                    print("[ERROR] 被重定向到登录页，Cookie 已失效或被风控，请重新获取")
                    return False
            except WebDriverException as e:
                print(f"[WARN] 第 {attempt}/{retries} 次登录异常: {type(e).__name__}: "
                      f"{str(e).splitlines()[0] if str(e) else ''}")
            if attempt < retries:
                time.sleep(5 * attempt)
        print("[ERROR] 登录最终失败")
        return False

    # ------------------------------------------------------------------ 虎粮
    def _wait_page_ready(self, timeout=30):
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
        )

    def get_hl_count(self):
        """原有逻辑：打开支付页 -> 点背包 -> 读 li[data-num]。
        返回虎粮数量；识别失败返回 None（与 0 区分开）。"""
        print("[SEARCH] 正在查询虎粮数量...")
        try:
            self.driver.get(cfg.URLS["pay_index"])
            self._wait_page_ready()
            pack_tab = self.wait.until(
                EC.element_to_be_clickable((By.ID, cfg.PAY_PAGE["pack_tab"])))
            pack_tab.click()

            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li[data-num]")))
            n = self.driver.execute_script('''
                for (const item of document.querySelectorAll('li[data-num]')) {
                    if ((item.title || item.innerText || '').includes('虎粮'))
                        return item.getAttribute('data-num');
                }
                return 0;
            ''')
            count = int(n) if n else 0
            print(f"[COUNT] 识别到虎粮: {count}")
            return count
        except Exception as e:
            print(f"[ERROR] 虎粮数量识别失败: {type(e).__name__} | {self._page_state()}")
            return None

    def send_to_room(self, rid, count):
        """原有逻辑：进房间取 lp/gid -> 礼物面板 -> 悬停虎粮 -> 填数量 -> 赠送。"""
        if count <= 0:
            return "⏭️ 无粮跳过"
        try:
            self.driver.get(cfg.URLS["room_base"].format(rid))
            self._wait_page_ready()

            lp, gid = self.driver.execute_script(
                'return [document.body.getAttribute("data-lp"),'
                '        document.body.getAttribute("data-gid")]'
            )
            if not lp or not gid:
                return "❌ 获取参数失败"

            self.driver.get(cfg.URLS["gift_tab"].format(lp=lp, gid=gid))
            items = self.wait.until(
                EC.presence_of_all_elements_located(
                    (By.CLASS_NAME, cfg.GIFT["item_class"])
                )
            )

            hu_liang = next((i for i in items if "虎粮" in i.text), None)
            if not hu_liang:
                return "❌ 未找到虎粮"

            ActionChains(self.driver).move_to_element(hu_liang).pause(0.5).click().perform()

            inp = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, cfg.GIFT["input_css"]))
            )
            inp.click()
            inp.clear()
            inp.send_keys(str(count))

            self.wait.until(
                EC.element_to_be_clickable((By.CLASS_NAME, cfg.GIFT["send_class"]))
            ).click()

            try:
                self.wait.until(
                    EC.element_to_be_clickable((By.CLASS_NAME, cfg.GIFT["confirm_class"]))
                ).click()
            except Exception:
                pass

            time.sleep(8)
            return f"🚀 房间 {rid} 送出虎粮 {count} 个"
        except Exception as e:
            print(f"[ERROR] 房间 {rid} 送礼异常: {type(e).__name__} | {self._page_state()}")
            return f"❌ 房间 {rid} 送礼异常（可能未开播）"

    # ------------------------------------------------------------------ 打卡
    def daily_check_in(self, rid):
        try:
            self._open(cfg.URLS["room_base"].format(rid))
            badge = self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, cfg.CHECKIN["badge_css"])))
        except TimeoutException:
            print(f"[WARN] 房间 {rid} 未找到粉丝牌入口 | {self._page_state()}")
            return "⚠️ 未找到粉丝牌入口（未加入粉丝团/页面未加载）"
        except WebDriverException as e:
            return f"⚠️ 打卡异常: {type(e).__name__}"

        try:
            ActionChains(self.driver).move_to_element(badge).perform()
            btn = WebDriverWait(self.driver, 8).until(EC.element_to_be_clickable(
                (By.XPATH, cfg.CHECKIN["btn_xpath"])))
            btn.click()
            return "✅ 打卡成功"
        except TimeoutException:
            return "ℹ️ 已打卡"
        except WebDriverException as e:
            return f"⚠️ 打卡异常: {type(e).__name__}"

    # ------------------------------------------------------------------ 主流程
    def run(self):
        print("=" * 40)
        print("[HUYA] 虎牙自动任务启动")
        print("=" * 40)
        try:
            if not self.login():
                self.failed = True
                self.msg_logs.append(
                    "❌ 登录失败：Cookie 已失效或被风控，请重新获取 HUYA_COOKIE"
                    if self.cookie_invalid else
                    "❌ 登录失败：页面加载超时/登录元素未出现，请查看 Actions 日志")
                return

            total = self.get_hl_count()
            if total is None:
                self.failed = True
                self.msg_logs.append("⚠️ 虎粮数量识别失败，本次跳过送礼，仅打卡")
                total = 0
            else:
                self.msg_logs.append(f"今日虎粮总数: {total}")

            n_rooms = len(self.rooms)
            base, extra = divmod(total, n_rooms)
            for i, rid in enumerate(self.rooms):
                num = base + (1 if i < extra else 0)
                print(f"\n>>> 房间: {rid} (目标数量: {num})")
                g_res = self.send_to_room(rid, num)
                c_res = self.daily_check_in(rid)
                if g_res.startswith("❌"):
                    self.failed = True
                msg = f"{g_res}；{c_res}"
                print(f"结果: {msg}")
                self.msg_logs.append(msg)
        finally:
            self.send_notification()
            try:
                self.driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    bot = HuYaAuto()
    bot.run()
    sys.exit(1 if bot.failed else 0)
