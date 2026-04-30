import httpx
import feedparser
import subprocess
import asyncio
import html
import os
import shutil
import sys
from bs4 import BeautifulSoup
from config import RSSHUB_BASE
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes
from utils import load_json, save_json
from config import STATS_FILE, ALLOWED_USERS, TARGETS_FILE
from monitor import check_weibo
import runtime_state


# ⚠️ 请确保这里的容器名与您部署 RSSHub 时填写的 container_name 一致
RSSHUB_CONTAINER_NAME = "rsshub" 
# 对应的环境配置文件路径
RSSHUB_ENV_PATH = "/app/rsshub.env"


def _format_duration(seconds):
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}天")
    if hours:
        parts.append(f"{hours}小时")
    parts.append(f"{minutes}分钟")
    return "".join(parts)


def _read_system_status():
    disk = shutil.disk_usage("/")
    disk_used_pct = disk.used / disk.total * 100

    load_text = "未知"
    if hasattr(os, "getloadavg"):
        load1, load5, load15 = os.getloadavg()
        load_text = f"{load1:.2f}, {load5:.2f}, {load15:.2f}"

    uptime_text = "未知"
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            uptime_text = _format_duration(float(f.read().split()[0]))
    except Exception:
        pass

    mem_text = "未知"
    try:
        meminfo = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                key, value = line.split(":", 1)
                meminfo[key] = int(value.strip().split()[0])
        total = meminfo["MemTotal"]
        available = meminfo.get("MemAvailable", 0)
        used_pct = (total - available) / total * 100
        mem_text = f"{used_pct:.1f}% ({(total - available) / 1024 / 1024:.1f}G / {total / 1024 / 1024:.1f}G)"
    except Exception:
        pass

    return {
        "uptime": uptime_text,
        "load": load_text,
        "memory": mem_text,
        "disk": f"{disk_used_pct:.1f}% ({disk.used / 1024 / 1024 / 1024:.1f}G / {disk.total / 1024 / 1024 / 1024:.1f}G)",
    }


async def _get_docker_status():
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            "ps",
            "--format",
            "{{.Names}}\t{{.Status}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=8)
        if process.returncode != 0:
            return f"Docker 查询失败：{stderr.decode(errors='ignore').strip() or '未知错误'}"

        wanted = {"weibobot", "rsshub", "redis"}
        statuses = {}
        for line in stdout.decode(errors="ignore").splitlines():
            if not line.strip():
                continue
            name, _, status = line.partition("\t")
            if name in wanted:
                statuses[name] = status
        return "\n".join(f"{name}: {statuses.get(name, '未运行')}" for name in sorted(wanted))
    except Exception as e:
        return f"Docker 查询失败：{e}"


def _last_check_text():
    if runtime_state.LAST_CHECK_AT:
        return runtime_state.LAST_CHECK_AT.strftime("%Y-%m-%d %H:%M:%S")
    return "尚未执行"


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看机器人运行状态"""
    if update.effective_user.id not in ALLOWED_USERS:
        return

    targets = load_json(TARGETS_FILE, {})
    history = load_json("history.json", {})
    stats = load_json(STATS_FILE, {"checks": 0, "new_posts": 0})
    started_seconds = (runtime_state.datetime.now() - runtime_state.STARTED_AT).total_seconds()
    cookie_file_exists = os.path.exists(RSSHUB_ENV_PATH)

    msg = (
        "🧭 <b>WeiboBot 状态</b>\n\n"
        f"运行时长：<code>{_format_duration(started_seconds)}</code>\n"
        f"Python：<code>{html.escape(sys.version.split()[0])}</code>\n"
        f"RSSHub：<code>{html.escape(RSSHUB_BASE)}</code>\n"
        f"监控目标：<code>{len(targets)}</code> 个\n"
        f"历史记录：<code>{len(history)}</code> 条\n"
        f"本轮统计：巡检 <code>{stats.get('checks', 0)}</code> 次，新微博 <code>{stats.get('new_posts', 0)}</code> 条\n"
        f"最近巡检：<code>{html.escape(_last_check_text())}</code>\n"
        f"最近结果：<code>{html.escape(runtime_state.LAST_CHECK_RESULT)}</code>\n"
        f"Cookie 文件：<code>{'存在' if cookie_file_exists else '不存在'}</code>"
    )

    if runtime_state.LAST_ERROR:
        msg += f"\n最近错误：<code>{html.escape(runtime_state.LAST_ERROR[:300])}</code>"

    await update.message.reply_text(msg, parse_mode='HTML')


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """主动检查 RSSHub 微博路由是否可用"""
    if update.effective_user.id not in ALLOWED_USERS:
        return

    targets = load_json(TARGETS_FILE, {})
    if not targets:
        await update.message.reply_text("📭 当前监控列表为空，无法执行健康检查。")
        return

    uid_to_check = context.args[0] if context.args else next(iter(targets))
    if uid_to_check not in targets:
        await update.message.reply_text(f"❌ UID <code>{html.escape(str(uid_to_check))}</code> 不在监控列表中。", parse_mode='HTML')
        return

    status_msg = await update.message.reply_text("🩺 正在检查 RSSHub 微博路由...")
    target_url = f"{RSSHUB_BASE}{uid_to_check}"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(target_url)

        feed = feedparser.parse(resp.text)
        title = getattr(feed.feed, "title", "")
        has_rsshub_error = "RSSHub" in title and "Error" in title
        entries_count = len(feed.entries)

        status = "正常" if resp.status_code == 200 and entries_count > 0 and not has_rsshub_error else "异常"
        msg = (
            "🩺 <b>RSSHub 健康检查</b>\n\n"
            f"状态：<code>{status}</code>\n"
            f"UID：<code>{html.escape(str(uid_to_check))}</code>\n"
            f"HTTP：<code>{resp.status_code}</code>\n"
            f"RSS 条目：<code>{entries_count}</code>\n"
            f"标题：<code>{html.escape(str(title)[:200])}</code>\n"
            f"地址：<code>{html.escape(target_url)}</code>"
        )
        if status != "正常":
            msg += "\n\n可能原因：Cookie 失效、RSSHub 容器异常、微博限流、UID 错误或网络不可达。"
        await status_msg.edit_text(msg, parse_mode='HTML')
    except Exception as e:
        await status_msg.edit_text(f"❌ 健康检查失败：<code>{html.escape(str(e))}</code>", parse_mode='HTML')


async def cmd_server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看 VPS 和 Docker 容器状态"""
    if update.effective_user.id not in ALLOWED_USERS:
        return

    status_msg = await update.message.reply_text("🖥 正在读取服务器状态...")
    system_status = _read_system_status()
    docker_status = await _get_docker_status()

    msg = (
        "🖥 <b>服务器状态</b>\n\n"
        f"运行时长：<code>{html.escape(system_status['uptime'])}</code>\n"
        f"系统负载：<code>{html.escape(system_status['load'])}</code>\n"
        f"内存：<code>{html.escape(system_status['memory'])}</code>\n"
        f"磁盘：<code>{html.escape(system_status['disk'])}</code>\n\n"
        f"<b>Docker</b>\n<code>{html.escape(docker_status)}</code>"
    )
    await status_msg.edit_text(msg, parse_mode='HTML')


async def cmd_check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """立即执行一次正式巡检"""
    if update.effective_user.id not in ALLOWED_USERS:
        return

    status_msg = await update.message.reply_text("🔄 正在立即执行巡检...")
    await check_weibo(context)
    msg = (
        "✅ <b>巡检已完成</b>\n\n"
        f"时间：<code>{html.escape(_last_check_text())}</code>\n"
        f"结果：<code>{html.escape(runtime_state.LAST_CHECK_RESULT)}</code>"
    )
    if runtime_state.LAST_ERROR:
        msg += f"\n错误：<code>{html.escape(runtime_state.LAST_ERROR[:300])}</code>"
    await status_msg.edit_text(msg, parse_mode='HTML')


async def daily_report(context):
    """每天固定时间发送的统计日报"""
    stats = load_json(STATS_FILE, {"checks": 0, "new_posts": 0})
    
    report_text = (
        "📈 **每日巡检日报** 📈\n\n"
        f"🤖 过去 24 小时内，本机器人共执行巡检 `{stats['checks']}` 次。\n"
        f"✨ 共为您捕获新微博 `{stats['new_posts']}` 条。\n\n"
        "保持专注，继续为您监控！"
    )
    
    for uid in ALLOWED_USERS:
        await context.bot.send_message(chat_id=uid, text=report_text, parse_mode='Markdown')
        
    save_json(STATS_FILE, {"checks": 0, "new_posts": 0})

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """响应 /list 指令，列出当前监控名单"""
    # 白名单校验
    if update.effective_user.id not in ALLOWED_USERS:
        return

    targets = load_json(TARGETS_FILE, {})
    
    if not targets:
        await update.message.reply_text("📭 当前监控列表为空，请在 targets.json 中添加。")
        return

    msg = "📋 <b>当前正在监控的微博列表：</b>\n\n"
    for uid, name in targets.items():
        msg += f"👤 <b>{html.escape(str(name))}</b> (<code>{html.escape(str(uid))}</code>)\n"
        
    msg += f"\n💡 共计 {len(targets)} 个目标。"
    
    await update.message.reply_text(msg, parse_mode='HTML')
    
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """响应 /report 指令，手动查看当前巡检统计"""
    if update.effective_user.id not in ALLOWED_USERS:
        return

    # 这里虽然有默认值，但如果文件存在且内容为 {}，load_json 依然会返回 {}
    stats = load_json(STATS_FILE, {"checks": 0, "new_posts": 0})
    
    # 【关键修改】：使用 .get(key, default) 替代直接索引
    checks_count = stats.get('checks', 0)
    posts_count = stats.get('new_posts', 0)
    
    msg = (
        "📊 <b>实时巡检状态报告</b>\n\n"
        f"⏳ 自上次日报以来：\n"
        f"🔄 累计巡检次数：<code>{checks_count}</code> 次\n"
        f"✨ 捕获新微博数：<code>{posts_count}</code> 条\n\n"
        "👌 机器人运行正常，正在持续监控中。"
    )
    await update.message.reply_text(msg, parse_mode='HTML')

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """响应 /help 指令，列出所有可用命令"""
    if update.effective_user.id not in ALLOWED_USERS:
        return

    help_text = (
        "🤖 <b>WeiboBot 指令指南</b>\n\n"
        "🔹 /list - 查看当前监控的博主名单\n"
        "🔹 /report - 立即查看当前的巡检统计数据\n"
        "🔹 /latest - 获取指定博主（或默认首位）的最新 3 条动态\n"
        "🔹 /status - 查看机器人运行状态\n"
        "🔹 /health - 检查 RSSHub 微博路由健康状态\n"
        "🔹 /server - 查看 VPS 与 Docker 容器状态\n"
        "🔹 /check_now - 立即执行一次正式巡检\n"
        "🔹 /help - 显示此帮助信息\n\n"
        "🔹 /set_cookie - 设置新的cookie信息\n"
        "💡 <b>使用小窍门：</b>\n"
        "发送 <code>/latest [UID]</code> 可精准查询。例如：<code>/latest 7888222767</code> \n\n"
        "💡 <i>提示：系统每小时自动巡检一次，每天 22:00 发送汇总日报。</i>"
    )
    await update.message.reply_text(help_text, parse_mode='HTML')
    
    
    
async def cmd_set_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """远程更新 Cookie 并重启 RSSHub 容器"""
    if update.effective_user.id not in ALLOWED_USERS:
        return

    new_cookie = " ".join(context.args).strip()
    if not new_cookie:
        await update.message.reply_text("❌ 格式错误！请使用：`/set_cookie 你的Cookie字符串`")
        return

    status_msg = await update.message.reply_text("⏳ 正在更新 Cookie 并准备重启 RSSHub...")

    try:
        # 1. 将新 Cookie 写入挂载的 env 文件
        # 注意：这里假设 RSSHub 读取的是 WEIBO_COOKIES 变量
        with open(RSSHUB_ENV_PATH, "w") as f:
            f.write(f"WEIBO_COOKIES='{new_cookie}'\n")
        
        # 2. 调用系统命令重启 RSSHub 容器
        # 使用 asyncio.create_subprocess_shell 保证不阻塞机器人主进程
        process = await asyncio.create_subprocess_shell(
            f"docker restart {RSSHUB_CONTAINER_NAME}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            await status_msg.edit_text("✅ <b>更新成功！</b>\n\nRSSHub 已带着新 Cookie 重启完成。", parse_mode='HTML')
        else:
            error_log = html.escape(stderr.decode().strip())
            await status_msg.edit_text(f"⚠️ 容器重启失败！\n错误信息：<code>{error_log}</code>", parse_mode='HTML')

    except Exception as e:
        await status_msg.edit_text(f"❌ 发生意外错误：<code>{html.escape(str(e))}</code>", parse_mode='HTML')
    
async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """响应 /latest 指令，主动拉取博主的最新 3 条动态（支持多图）"""
    if update.effective_user.id not in ALLOWED_USERS:
        return

    targets = load_json(TARGETS_FILE, {})
    if not targets:
        await update.message.reply_text("📭 当前监控列表为空，无法抓取。")
        return

    uid_to_check = context.args[0] if context.args else next(iter(targets))
    
    if uid_to_check not in targets:
        await update.message.reply_text(f"❌ UID <code>{html.escape(str(uid_to_check))}</code> 不在您的监控列表中！", parse_mode='HTML')
        return

    memo_name = targets[uid_to_check]
    safe_memo_name = html.escape(memo_name)
    status_msg = await update.message.reply_text(f"🔍 正在为您拉取 <b>{safe_memo_name}</b> 的最新动态...", parse_mode='HTML')
    
    target_url = f"{RSSHUB_BASE}{uid_to_check}"
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(target_url)
            if resp.status_code != 200:
                await status_msg.edit_text(f"❌ 请求 RSSHub 失败，状态码：<code>{resp.status_code}</code>", parse_mode='HTML')
                return
                
            feed = feedparser.parse(resp.text)
            entries = feed.entries[:3]
            
            if not entries:
                await status_msg.edit_text(f"📭 <b>{safe_memo_name}</b> 最近没有发布任何内容。", parse_mode='HTML')
                return
                
            await status_msg.edit_text(f"✅ 成功拉取 <b>{safe_memo_name}</b> 的最新 {len(entries)} 条动态：", parse_mode='HTML')
            
            for entry in entries:
                soup = BeautifulSoup(entry.description, "html.parser")
                clean_text = soup.get_text(separator='\n').strip()
                display_text = clean_text[:200] + "..." if len(clean_text) > 200 else clean_text
                
                # 【新增】：提取所有图片链接
                img_tags = soup.find_all('img')
                images = [img.get('src') for img in img_tags if img.get('src')]
                
                safe_published = html.escape(getattr(entry, "published", "未知时间"))
                safe_text = html.escape(display_text)
                safe_link = html.escape(entry.link, quote=True)
                msg = f"🕒 {safe_published}\n\n📝 {safe_text}\n\n🔗 <a href='{safe_link}'>点击查看原微博</a>"
                
                chat_id = update.effective_chat.id
                
                # 【新增】：根据图片数量决定发送模式
                if not images:
                    # 没图片，发纯文本
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML', disable_web_page_preview=True)
                elif len(images) == 1:
                    # 单张图片
                    await context.bot.send_photo(chat_id=chat_id, photo=images[0], caption=msg[:1024], parse_mode='HTML')
                else:
                    # 多张图片 (Telegram 限制一个 MediaGroup 最多 10 张)
                    media_group = []
                    for i, img_url in enumerate(images[:10]): 
                        if i == 0:
                            # 第一张图带上文字说明
                            media_group.append(InputMediaPhoto(img_url, caption=msg[:1024], parse_mode='HTML'))
                        else:
                            media_group.append(InputMediaPhoto(img_url))
                    await context.bot.send_media_group(chat_id=chat_id, media=media_group)
                
                # ⚠️ 连续发送多条带图消息，安全休眠时间稍微拉长一点
                await asyncio.sleep(2) 
                
    except Exception as e:
        await status_msg.edit_text(f"❌ 抓取时发生意外错误：<code>{html.escape(str(e))}</code>", parse_mode='HTML')
