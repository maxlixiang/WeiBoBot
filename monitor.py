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
    """每小时执行一次的多目标微博巡检任务"""
    history = load_json(HISTORY_FILE, {})
    stats = load_json(STATS_FILE, {"checks": 0, "new_posts": 0})
    targets = load_json(TARGETS_FILE, {})
    
    if not targets:
        print("⚠️ 监控列表为空，跳过本次巡检。")
        return

    stats["checks"] += 1 
    
    try:
        # 遍历花名册里的每一个博主
        for uid, memo_name in targets.items():
            target_url = f"{RSSHUB_BASE}{uid}"
            
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.get(target_url)
                    feed = feedparser.parse(resp.text)
                    
                author_name = feed.feed.title if 'title' in feed.feed else memo_name
                
                for entry in reversed(feed.entries[:5]):
                    post_id = entry.link 
                    
                    if post_id not in history:
                        try:
                            soup = BeautifulSoup(entry.description, 'html.parser')
                            clean_text = soup.get_text(separator='\n', strip=True)
                            images = [img['src'] for img in soup.find_all('img')]
                            
                            await send_weibo_alert(context, author_name, clean_text, images, entry.link)
                            
                            history[post_id] = True
                            stats["new_posts"] += 1
                            await asyncio.sleep(3)
                            
                        except Exception as e:
                            print(f"发送单条微博失败 ({post_id}): {e}")
            except Exception as e:
                print(f"获取博主 {memo_name}({uid}) 数据失败: {e}")
            
            # 查完一个博主，稍微休息 2 秒防止被屏蔽
            await asyncio.sleep(2)
                
        save_json(HISTORY_FILE, history)
        save_json(STATS_FILE, stats)
    except Exception as e:
         print(f"获取微博数据大循环失败: {e}")

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