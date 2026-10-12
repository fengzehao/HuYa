#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一配置文件：选择器、URL、超时"""

# 固定的目标房间号（多个房间用逗号分隔，如 [910323, 518512]）
ROOMS = [910323]

# 登录成功后用户中心页面会出现的元素 ID
LOGIN = {
    "huya_num": "huyaNum",
}

# 充值背包
PAY_PAGE = {
    "pack_tab": "packTab",
}

# 礼物面板
GIFT = {
    "item_class": "m-gift-item",
    "input_css": "input[type='number'][placeholder='自定义']",
    "send_class": "c-send",
    "confirm_class": "btn-success",
}

# 粉丝牌打卡
# 原来的 class 带有哈希后缀（FanClubHd--UAIAw8vo8FGSKqVwLp7A），虎牙前端一发版就会变，
# 这里改成前缀匹配，只要 class 前缀不变就能命中。
CHECKIN = {
    "badge_css": "[class*='FanClubHd']",
    "btn_xpath": "//a[contains(text(), '打卡')]",
}

# URL
URLS = {
    "user_index": "https://i.huya.com/",
    "room_base": "https://huya.com/{}",
    "pay_index": "https://hd.huya.com/pay/index.html?source=web",
    "gift_tab": "https://hd.huya.com/web/webPackageV2/index.html?lp={lp}&gid={gid}",
}

# 超时（秒）
TIMING = {
    "page_load_timeout": 120,  # 单次 driver.get 上限（与原版一致）
    "login_wait": 30,          # 等待登录态元素出现
    "wait": 20,               # 通用显式等待
}
