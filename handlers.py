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