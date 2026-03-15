import datetime
from telegram.ext import ApplicationBuilder, CommandHandler
from config import TOKEN
from monitor import check_weibo
from handlers import daily_report, cmd_list, cmd_report, cmd_help

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.job_queue.run_repeating(check_weibo, interval=3600, first=5)
    
    report_time = datetime.time(hour=14, minute=0, second=0) 
    app.job_queue.run_daily(daily_report, time=report_time)
    
    # --- 注册交互指令 ---
    app.add_handler(CommandHandler("list", cmd_list))
    # 【新增】：注册 report 和 help 指令
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("help", cmd_help))
    
    print("🤖 微博多核监控机器人已启动...")
    app.run_polling()