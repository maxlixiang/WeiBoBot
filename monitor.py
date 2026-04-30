import httpx
import feedparser
import asyncio
from bs4 import BeautifulSoup
from telegram import InputMediaPhoto
from utils import load_json, save_json
from config import ALLOWED_USERS, TARGETS_FILE,RSSHUB_BASE
import html
import runtime_state
from archive import archive_weibo_post



HISTORY_FILE = "history.json"
STATS_FILE = "stats.json"

async def check_weibo(context):
    """带异常报警的多目标巡检任务"""
    runtime_state.LAST_CHECK_AT = runtime_state.datetime.now()
    runtime_state.LAST_CHECK_RESULT = "巡检中"
    runtime_state.LAST_ERROR = ""

    history = load_json(HISTORY_FILE, {})
    stats = load_json(STATS_FILE, {"checks": 0, "new_posts": 0})
    targets = load_json(TARGETS_FILE, {})
    
    if not targets:
        runtime_state.LAST_CHECK_RESULT = "跳过：监控列表为空"
        return

    stats["checks"] = stats.get("checks", 0) + 1 
    new_posts_before = stats.get("new_posts", 0)

    try:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                # 真正开始遍历每个监控目标
                for uid, memo_name in targets.items():
                    target_url = f"{RSSHUB_BASE}{uid}"
                    resp = await client.get(target_url)
                    
                    # --- Cookie/接口预警逻辑 ---
                    if resp.status_code != 200:
                        error_msg = f"🚨 **RSSHub 异常警报**\n\n状态码：`{resp.status_code}`\n原因：可能是微博 Cookie 过期或 RSSHub 实例被限制。\n请检查 VPS 上的 RSSHub 容器日志！"
                        await send_text_to_allowed_users(context, error_msg, parse_mode='Markdown')
                        runtime_state.LAST_CHECK_RESULT = f"失败：RSSHub 返回 {resp.status_code}"
                        runtime_state.LAST_ERROR = runtime_state.LAST_CHECK_RESULT
                        return # 发生错误直接停止本次巡检

                    feed = feedparser.parse(resp.text)
                    
                    if "RSSHub" in feed.feed.title and "Error" in feed.feed.title:
                        error_msg = "🚨 **Weibo Cookie 已失效！**\n\n检测到 RSSHub 报错，请立即更新微博 Cookie 并重启 RSSHub 服务。"
                        await send_text_to_allowed_users(context, error_msg, parse_mode='Markdown')
                        runtime_state.LAST_CHECK_RESULT = "失败：RSSHub 报错，可能是 Cookie 失效"
                        runtime_state.LAST_ERROR = runtime_state.LAST_CHECK_RESULT
                        return

                    # --- 核心抓取与比对逻辑 ---
                    # 检查最新的 5 条动态
                    for entry in feed.entries[:5]:
                        post_id = entry.link # 使用链接作为唯一标识符
                        
                        # 如果这条微博不在历史记录中，说明是新的！
                        if post_id not in history:
                            # 1. 标记为已处理
                            history[post_id] = True
                            stats["new_posts"] = stats.get("new_posts", 0) + 1
                            
                            # 2. 解析正文和图片
                            soup = BeautifulSoup(entry.description, "html.parser")
                            clean_text = soup.get_text(separator='\n').strip()
                            display_text = clean_text[:200] + "..." if len(clean_text) > 200 else clean_text
                            
                            img_tags = soup.find_all('img')
                            images = [img.get('src') for img in img_tags if img.get('src')]

                            archive_weibo_post(
                                uid=uid,
                                author=memo_name,
                                text=display_text,
                                images=images,
                                link=entry.link,
                                published=getattr(entry, "published", ""),
                            )
                            
                            # 3. 发送提醒
                            await send_weibo_alert(context, memo_name, display_text, images, entry.link)
                            
                            # 4. 休息两秒，防止触发 Telegram 频繁发送限制
                            await asyncio.sleep(2)

                found_count = stats.get("new_posts", 0) - new_posts_before
                runtime_state.LAST_CHECK_RESULT = f"成功：发现 {found_count} 条新微博"

        except Exception as e:
             runtime_state.LAST_CHECK_RESULT = "失败：巡检异常"
             runtime_state.LAST_ERROR = str(e)
             print(f"巡检时发生未知错误: {e}")
    finally:
        # 无论巡检是否中途失败，都保存已经处理过的记录，避免重复推送。
        save_json(HISTORY_FILE, history)
        save_json(STATS_FILE, stats)

async def send_text_to_allowed_users(context, text, parse_mode=None):
    """给白名单用户发送文本，单个用户失败不影响其他用户。"""
    for uid in ALLOWED_USERS:
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode=parse_mode)
        except Exception as e:
            print(f"发送 Telegram 文本失败: user={uid}: {e}")

async def send_weibo_alert(context, author, text, images, link):
    """负责将微博内容排版并发送到 Telegram (HTML安全模式)"""
    safe_author = html.escape(str(author))
    safe_text = html.escape(str(text))
    safe_link = html.escape(str(link), quote=True)
    
    msg_text = f"📢 <b>{safe_author} 有新动态啦！</b>\n\n{safe_text}\n\n🔗 <a href='{safe_link}'>点击查看原微博</a>"
    
    for uid in ALLOWED_USERS:
        try:
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
        except Exception as e:
            print(f"发送微博提醒失败: user={uid}: {e}")
