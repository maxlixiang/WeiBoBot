import httpx
import feedparser
import asyncio
from bs4 import BeautifulSoup
from telegram import InputMediaPhoto
from utils import load_json, save_json
from config import ALLOWED_USERS
import html

# 你的 RSSHub 地址和要监控的 UID
RSSHUB_URL = "http://131.143.214.250:1200/weibo/user/6328786524"

HISTORY_FILE = "history.json"
STATS_FILE = "stats.json"

async def check_weibo(context):
    """每小时执行一次的微博巡检任务"""
    history = load_json(HISTORY_FILE, {})
    stats = load_json(STATS_FILE, {"checks": 0, "new_posts": 0})
    
    stats["checks"] += 1 # 记录巡检次数
    
    try:
        # 1. 异步获取数据 (避免阻塞机器人)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(RSSHUB_URL)
            feed = feedparser.parse(resp.text)
            
        author_name = feed.feed.title if 'title' in feed.feed else "未知博主"
        
        # 2. 从旧到新遍历最新微博 (防止多条同时发时顺序颠倒)
        for entry in reversed(feed.entries[:5]):
            post_id = entry.link 
            
            # 如果这条微博没发过
            if post_id not in history:
                try:
                    # 解析 HTML 提取纯文本和图片
                    soup = BeautifulSoup(entry.description, 'html.parser')
                    clean_text = soup.get_text(separator='\n', strip=True)
                    images = [img['src'] for img in soup.find_all('img')]
                    
                    # 发送通知
                    await send_weibo_alert(context, author_name, clean_text, images, entry.link)
                    
                    # 只有发送成功了，才记录到历史和统计中
                    history[post_id] = True
                    stats["new_posts"] += 1
                    
                    # 【关键点 1】：每发完一条，强制让机器人休息 3 秒，防止触发 Telegram 频率限制
                    await asyncio.sleep(3)
                    
                except Exception as e:
                    # 【关键点 2】：把报错放在循环内部，一条失败不影响下一条
                    print(f"发送单条微博失败 ({post_id}): {e}")
                
        # 循环彻底结束后，再统一保存数据
        save_json(HISTORY_FILE, history)
        save_json(STATS_FILE, stats)
    except Exception as e:
         print(f"获取微博数据大循环失败: {e}")
async def send_weibo_alert(context, author, text, images, link):
    """负责将微博内容排版并发送到 Telegram (HTML安全模式)"""
    
    # 净化文本，将特殊字符（如 <, >）转义，防止 Telegram HTML 引擎报错
    safe_author = html.escape(author)
    safe_text = html.escape(text)
    
    # 使用 HTML 格式排版
    msg_text = f"📢 <b>{safe_author} 有新动态啦！</b>\n\n{safe_text}\n\n🔗 <a href='{link}'>点击查看原微博</a>"
    
    for uid in ALLOWED_USERS:
        # 如果没有图片
        if not images:
            await context.bot.send_message(chat_id=uid, text=msg_text, parse_mode='HTML', disable_web_page_preview=True)
        # 如果只有1张图
        elif len(images) == 1:
            await context.bot.send_photo(chat_id=uid, photo=images[0], caption=msg_text[:1024], parse_mode='HTML', read_timeout=60, write_timeout=60)
        # 如果有多张图
        else:
            media_group = []
            for i, img_url in enumerate(images[:10]): 
                if i == 0:
                    media_group.append(InputMediaPhoto(img_url, caption=msg_text[:1024], parse_mode='HTML'))
                else:
                    media_group.append(InputMediaPhoto(img_url))
            await context.bot.send_media_group(chat_id=uid, media=media_group, read_timeout=60, write_timeout=60)