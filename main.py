#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import requests

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

import config as cfg

class HuYaAuto:
    def __init__(self):
        # ============ 配置项 ============
        self.debug = False  # 开启调试
        self.enable_push = True  # 推送开关已开启
        # ================================
        
        self.msg_logs = []
        self.cookie = os.getenv('HUYA_COOKIE', '').strip()
        self.rooms = self._parse_rooms(os.getenv('HUYA_ROOMS', ''))
        self.send_key = os.getenv('SEND_KEY', '').strip()

        if not self.cookie:
            print("[ERROR] 未设置 HUYA_COOKIE"); sys.exit(1)
        if not self.rooms:
            self.rooms = [910323]

        self.driver = self._init_browser()
        self.wait = WebDriverWait(self.driver, 20)

    def _parse_rooms(self, rooms_str):
        if not rooms_str: 
            return []
        return [int(s.strip()) for s in rooms_str.split(',') if s.strip().isdigit()]

    def _init_browser(self):
        opts = Options()
        if not self.debug:
            opts.add_argument('--headless=new')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--disable-gpu')
        opts.add_argument('--disable-extensions')
        opts.add_argument('--disable-background-networking')
        opts.add_argument('--disable-default-apps')
        opts.add_argument('--disable-sync')
        opts.add_argument('--disable-translate')
        opts.add_argument('--metrics-recording-only')
        opts.add_argument('--no-first-run')
        opts.add_argument('--window-size=1920,1080')
        opts.add_argument('--disable-blink-features=AutomationControlled')
        opts.add_argument('--blink-settings=imagesEnabled=false')
        opts.add_argument('--disable-features=VizDisplayCompositor,TranslateUI')
        opts.add_argument('--disable-ipc-flooding-protection')
        opts.add_argument(
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        )
        
        binary_path = os.getenv('CHROME_BIN', '/usr/bin/google-chrome')
        if os.path.isfile(binary_path):
            opts.binary_location = binary_path

        driver_path = (
            os.getenv('CHROMEDRIVER_BIN')
            or os.path.join(os.getenv('CHROMEWEBDRIVER', ''), 'chromedriver')
            or '/usr/local/share/chromedriver-linux64/chromedriver'
        )

        driver = webdriver.Chrome(service=Service(driver_path), options=opts)
        driver.set_page_load_timeout(120)
        driver.set_script_timeout(60)
        
        driver.execute_cdp_cmd('Network.setBlockedURLs', {
            'urls': ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.webp',
                 '*.woff', '*.woff2', '*.ttf', '*.mp4', '*.flv', '*.m3u8']
        })
        driver.execute_cdp_cmd('Network.enable', {})
        return driver
        
    def _wait_page_ready(self, timeout=30):
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
        )

    def send_notification(self):
        """新增：Server酱推送方法"""
        if not self.enable_push or not self.send_key:
            return
            
        print("[PUSH] 正在发送推送通知...")
        try:
            content = "\n\n".join(self.msg_logs)
            title = "虎牙-任务失败" if "失败" in content else "虎牙-任务成功"
            res = requests.post(
                f"https://sctapi.ftqq.com/{self.send_key}.send",
                data={"title": title, "desp": content},
                timeout=10,
            )
            tag = "SUCCESS" if res.status_code == 200 else "FAILED"
            print(f"[{tag}] 推送状态: {res.status_code}")
        except Exception as e:
            print(f"[ERROR] 推送异常: {e}")

    def login(self, retries=2):
        print("[LOGIN] 正在登录...")
        for attempt in range(1, retries + 1):
            try:
                try:
                    self.driver.get("https://www.huya.com/robots.txt")
                except TimeoutException:
                    pass
                injected = 0
                for line in self.cookie.split(';'):
                    if '=' not in line:
                        continue
                    name, val = line.split('=', 1)
                    self.driver.add_cookie({
                        'name': name.strip(),
                        'value': val.strip(),
                        'domain': '.huya.com',
                        'path': '/',
                    })
                    injected += 1
                print(f"[LOGIN] 已注入 {injected} 条 cookie")
                try:
                    self.driver.get(cfg.URLS["user_index"])
                except TimeoutException:
                    print("[WARN] 用户中心加载超时，尝试继续...")
                self._wait_page_ready(timeout=30)
                self.wait.until(
                    EC.presence_of_element_located((By.ID, cfg.LOGIN["huya_num"]))
                )
                print("[SUCCESS] 登录成功")
                return True
            except Exception as e:
                print(f"[WARN] 第 {attempt}/{retries} 次登录失败: {type(e).__name__}: {e}")
                if attempt < retries:
                    time.sleep(5)
        print("[ERROR] 登录最终失败")
        return False

    def get_hl_count(self):
        print("[SEARCH] 正在查询虎粮数量...")
        try:
            self.driver.get(cfg.URLS["pay_index"])
            self._wait_page_ready()
            pack_tab = self.wait.until(
                EC.element_to_be_clickable((By.ID, cfg.PAY_PAGE["pack_tab"]))
            )
            pack_tab.click()
            
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'li[data-num]'))
            )
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
        except: 
            print("[ERROR] 虎粮数量识别失败")
            return 0

    def send_to_room_in_situ(self, rid, count):
        if count <= 0: 
            return "无粮跳过"
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
            except:
                pass
                
            time.sleep(8) 
            return f"🚀 房间 {rid} 送出虎粮 {count} 个"
        except Exception as e:
            if self.debug: 
                print(f"  [DEBUG] 送礼异常: {e}")
            return "❌ 过程异常"

    def daily_check_in(self, rid):
        try:
            self.driver.get(cfg.URLS["room_base"].format(rid))
            self._wait_page_ready()

            badge = self.wait.until(
                EC.presence_of_element_located(
                    (By.CLASS_NAME, "FanClubHd--UAIAw8vo8FGSKqVwLp7A")
                )
            )
            ActionChains(self.driver).move_to_element(badge).perform()

            btn = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), '打卡')]"))
            )
            btn.click()
            return "✅ 打卡成功"
        except Exception:
            return "ℹ️ 已打卡"

    def run(self):
        print("=" * 40)
        print(f"[HUYA] 虎牙自动任务启动 (Debug: {self.debug})")
        print("=" * 40)
        try:
            if not self.login(): 
                self.msg_logs.append("登录失败")
                return
            total = self.get_hl_count()
            self.msg_logs.append(f"今日虎粮总数: {total}")
            
            if total <= 0:
                print("[DONE] 暂无虎粮，结束运行")
                return
            
            n_rooms = len(self.rooms)
            base, extra = divmod(total, n_rooms)

            for i, rid in enumerate(self.rooms):
                num = base + (1 if i < extra else 0)
                print(f"\n>>> 房间: {rid} (目标数量: {num})")
                
                g_res = self.send_to_room_in_situ(rid, num)
                c_res = self.daily_check_in(rid)

                msg = f"{g_res}；{c_res}"
                print(f"结果: {msg}")
                self.msg_logs.append(msg)
        finally:
            if self.enable_push:
                self.send_notification()
            if hasattr(self, 'driver'):
                self.driver.quit()

if __name__ == '__main__':
    HuYaAuto().run()
