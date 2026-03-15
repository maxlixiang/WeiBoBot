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