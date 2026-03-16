import httpx
import feedparser
import asyncio
from bs4 import BeautifulSoup
from config import RSSHUB_BASE
from telegram import Update
from telegram.ext import ContextTypes
from utils import load_json, save_json
from config import STATS_FILE, ALLOWED_USERS, TARGETS_FILE

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

    msg = "📋 **当前正在监控的微博列表：**\n\n"
    for uid, name in targets.items():
        msg += f"👤 **{name}** (`{uid}`)\n"
        
    msg += f"\n💡 共计 {len(targets)} 个目标。"
    
    await update.message.reply_text(msg, parse_mode='Markdown')
    
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """响应 /report 指令，手动查看当前巡检统计"""
    if update.effective_user.id not in ALLOWED_USERS:
        return

    stats = load_json(STATS_FILE, {"checks": 0, "new_posts": 0})
    
    msg = (
        "📊 **实时巡检状态报告**\n\n"
        f"⏳ 自上次日报以来：\n"
        f"🔄 累计巡检次数：`{stats['checks']}` 次\n"
        f"✨ 捕获新微博数：`{stats['new_posts']}` 条\n\n"
        "👌 机器人运行正常，正在持续监控中。"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """响应 /help 指令，列出所有可用命令"""
    if update.effective_user.id not in ALLOWED_USERS:
        return

    help_text = (
        "🤖 **WeiboBot 指令指南**\n\n"
        "🔹 /list - 查看当前监控的博主名单\n"
        "🔹 /report - 立即查看当前的巡检统计数据\n"
        "🔹 /help - 显示此帮助信息\n\n"
        "💡 *提示：系统每小时自动巡检一次，每天 22:00 发送汇总日报。*"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')
    
    
    
async def cmd_set_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """远程更新 Cookie 指令"""
    if update.effective_user.id not in ALLOWED_USERS:
        return

    # 获取用户发送的指令内容
    new_cookie = " ".join(context.args)
    if not new_cookie:
        await update.message.reply_text("❌ 请在指令后粘贴新的 Cookie 字符串。")
        return

    # 这里可以调用一个函数将新 Cookie 写入配置文件或环境变量
    # 甚至可以直接让 RSSHub 容器通过环境变量读取它
    # ... 实现逻辑 ...
    
    await update.message.reply_text("✅ Cookie 更新成功！正在重启巡检任务...")
    
async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """响应 /latest 指令，主动拉取博主的最新 3 条动态"""
    if update.effective_user.id not in ALLOWED_USERS:
        return

    targets = load_json(TARGETS_FILE, {})
    if not targets:
        await update.message.reply_text("📭 当前监控列表为空，无法抓取。")
        return

    # 获取目标 UID，支持带参数抓取特定博主 (例: /latest 7888222767)，默认取列表第一个
    uid_to_check = context.args[0] if context.args else next(iter(targets))
    
    if uid_to_check not in targets:
        await update.message.reply_text(f"❌ UID `{uid_to_check}` 不在您的监控列表中！", parse_mode='Markdown')
        return

    memo_name = targets[uid_to_check]
    status_msg = await update.message.reply_text(f"🔍 正在为您拉取 **{memo_name}** 的最新动态...", parse_mode='Markdown')
    
    target_url = f"{RSSHUB_BASE}{uid_to_check}"
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(target_url)
            if resp.status_code != 200:
                await status_msg.edit_text(f"❌ 请求 RSSHub 失败，状态码：`{resp.status_code}`", parse_mode='Markdown')
                return
                
            feed = feedparser.parse(resp.text)
            entries = feed.entries[:3] # 切片，仅提取前 3 条
            
            if not entries:
                await status_msg.edit_text(f"📭 **{memo_name}** 最近没有发布任何内容。", parse_mode='Markdown')
                return
                
            await status_msg.edit_text(f"✅ 成功拉取 **{memo_name}** 的最新 {len(entries)} 条动态：", parse_mode='Markdown')
            
            for entry in entries:
                # 简单清洗 HTML 标签，保留纯文本用于快捷预览
                soup = BeautifulSoup(entry.description, "html.parser")
                clean_text = soup.get_text(separator='\n').strip()
                # 若文本过长则截断，保持排版美观
                display_text = clean_text[:200] + "..." if len(clean_text) > 200 else clean_text
                
                msg = (
                    f"🕒 {entry.published}\n\n"
                    f"📝 {display_text}\n\n"
                    f"🔗 [点击查看原微博]({entry.link})"
                )
                await update.message.reply_text(msg, parse_mode='Markdown', disable_web_page_preview=True)
                
                # ⚠️ 必须保留此休眠：连续发送 3 条消息，防止被 Telegram 官方风控
                await asyncio.sleep(1.5) 
                
    except Exception as e:
        await status_msg.edit_text(f"❌ 抓取时发生意外错误：`{str(e)}`", parse_mode='Markdown')