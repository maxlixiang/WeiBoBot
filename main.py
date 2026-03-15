import datetime
from telegram.ext import ApplicationBuilder
from config import TOKEN
from monitor import check_weibo
from handlers import daily_report

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    # 1. 注册每小时微博巡检 (3600秒)
    app.job_queue.run_repeating(check_weibo, interval=3600, first=5)
    
    # 2. 注册每日巡检日报 (比如设置在每天北京时间晚上 22:00)
    # 注意：VPS 如果是 UTC 时间，北京时间 22:00 对应 UTC 14:00
    report_time = datetime.time(hour=14, minute=0, second=0) 
    app.job_queue.run_daily(daily_report, time=report_time)
    
    print("🤖 微博监控机器人已启动...")
    app.run_polling()