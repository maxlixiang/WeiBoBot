import httpx
import feedparser
import asyncio
from bs4 import BeautifulSoup
from telegram import InputMediaPhoto
from utils import load_json, save_json
from config import ALLOWED_USERS, TARGETS_FILE
import html

# 替换成你的 RSSHub 基础链接
RSSHUB_BASE = "http://131.143.214.250:1200/weibo/user/"

HISTORY_FILE = "history.json"
STATS_FILE = "stats.json"

async def check_weibo(context):
    """带异常报警的多目标巡检任务"""
    history = load_json(HISTORY_FILE, {})
    stats = load_json(STATS_FILE, {"checks": 0, "new_posts": 0})
    targets = load_json(TARGETS_FILE, {})
    
    if not targets:
        return

    stats["checks"] += 1 
    
    # 获取任意一个博主 UID 用作“哨兵测试”
    first_uid = next(iter(targets))
    target_url = "http://131.143.214.250:1200/weibo/user/wrong_id"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(target_url)
            
            # --- 【新增】Cookie/接口预警逻辑 ---
            if resp.status_code != 200:
                error_msg = f"🚨 **RSSHub 异常警报**\n\n状态码：`{resp.status_code}`\n原因：可能是微博 Cookie 过期或 RSSHub 实例被限制。\n请检查 VPS 上的 RSSHub 容器日志！"
                for uid in ALLOWED_USERS:
                    await context.bot.send_message(chat_id=uid, text=error_msg, parse_mode='Markdown')
                return # 发生错误直接停止本次巡检，避免重复报错

            feed = feedparser.parse(resp.text)
            
            # RSSHub 报错通常会在标题里写 "RSSHub 发生错误"
            if "RSSHub" in feed.feed.title and "Error" in feed.feed.title:
                error_msg = "🚨 **Weibo Cookie 已失效！**\n\n检测到 RSSHub 报错，请立即更新微博 Cookie 并重启 RSSHub 服务。"
                for uid in ALLOWED_USERS:
                    await context.bot.send_message(chat_id=uid, text=error_msg, parse_mode='Markdown')
                return

        # --- 以下是正常的遍历逻辑（保持不变） ---
        for uid, memo_name in targets.items():
            # ... 这里的抓取代码保持和你之前的一致即可 ...
            # 为了篇幅简洁，这里省略重复的抓取循环
            pass

        save_json(HISTORY_FILE, history)
        save_json(STATS_FILE, stats)

    except Exception as e:
         print(f"巡检时发生未知错误: {e}")

async def send_weibo_alert(context, author, text, images, link):
    """负责将微博内容排版并发送到 Telegram (HTML安全模式)"""
    safe_author = html.escape(author)
    safe_text = html.escape(text)
    
    msg_text = f"📢 <b>{safe_author} 有新动态啦！</b>\n\n{safe_text}\n\n🔗 <a href='{link}'>点击查看原微博</a>"
    
    for uid in ALLOWED_USERS:
        if not images:
            await context.bot.send_message(chat_id=uid, text=msg_text, parse_mode='HTML', disable_web_page_preview=True)
        elif len(images) == 1:
            await context.bot.send_photo(chat_id=uid, photo=images[0], caption=msg_text[:1024], parse_mode='HTML', read_timeout=60, write_timeout=60)
        else:
            media_group = []
            for i, img_url in enumerate(images[:10]): 
                if i == 0:
                    media_group.append(InputMediaPhoto(img_url, caption=msg_text[:1024], parse_mode='HTML'))
                else:
                    media_group.append(InputMediaPhoto(img_url))
            await context.bot.send_media_group(chat_id=uid, media=media_group, read_timeout=60, write_timeout=60)