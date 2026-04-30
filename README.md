🤖 WeiboBot: 微博多核监控机器人

这是一套基于 Python 和 RSSHub 构建的自动化微博监控系统。它能够精准监控指定博主的动态，支持多图推送、每日日报，并具备远程热更新 Cookie 的高级运维能力。

✨ 核心特性

- 实时 / 定时监控：默认每小时自动巡检，确保动态不漏抓。
- 多图智能推送：自动解析微博正文中的图片，支持 Telegram Media Group 媒体组发送。
- 远程热更新：通过 Telegram 指令 `/set_cookie` 远程修改 Cookie 并自动重启 RSSHub 容器。
- 运行报告：每日 22:00 发送巡检统计日报，支持通过指令实时查看运行状态。
- 容器化部署：全套流程基于 Docker 编排，支持 GitHub Actions 自动化部署。

📂 项目结构

表格

|文件名|职责描述|
|---|---|
|main.py|程序入口，负责机器人指令注册与 JobQueue 任务调度。|
|monitor.py|监控逻辑核心，负责 RSS 抓取、数据对比、正文解析与消息推送。|
|handlers.py|交互指令处理器，涵盖从数据查询到 Docker 容器控制的逻辑。|
|rsshub.env|跨容器通信桥梁，用于在不同容器间传递 WEIBO_COOKIES。|
|targets.json|监控目标池，存储博主 UID 与备注名称。|
|docker-compose.yml|定义容器编排，实现路径挂载与 docker.sock 权限穿透。|

🚀 快速部署

1. 准备环境：确保服务器已安装 Docker 与 Docker Compose。
2. 配置文件：创建 `.env` 并填入 `BOT_TOKEN` 和 `ALLOWED_USERS`。在 `targets.json` 中添加博主 UID。
3. 启动服务：
    
    bash
    
    运行
    
    ```
    docker compose up -d --build
    ```
    

权限声明：WeiboBot 容器需挂载 `/var/run/docker.sock` 以获得控制 RSSHub 重启的权限。

🎮 常用指令

- `/list`：查看当前正在监控的博主清单。
- `/report`：实时查看自上次日报以来的巡检次数与捕获数量。
- `/latest [UID]`：主动获取特定博主的最新 3 条动态。
- `/set_cookie [Cookie]`：远程更新微博凭证，一键解决 503 报错。

🛡️ 稳健运行小锦囊 (Maintenance Tips)

为了确保监控系统长期稳定，请收好以下维护建议：

1. 频率与风控调优
    
    - 建议：默认巡检间隔为 3600 秒。
    - 风险预警：如需提速，请谨慎调整 `main.py` 中的 `interval`。频率过高（如低于 10 分钟）极易导致 Cookie 被微博暂时封禁。
    
2. 健康检查
    
    - 观察指标：若 `/report` 显示巡检次数增加但新微博始终为 0，且已知博主有更新，说明 Cookie 可能已失效。
    - 日志诊疗：怀疑运行异常时，使用以下命令查看实时日志：
        
        bash
        
        运行
        
        ```
        docker logs -f weibobot --tail 50
        ```
        
    
3. 数据维护
    
    - 目标增减：直接修改宿主机的 `targets.json` 即可实时生效，机器人将在下一次巡检周期自动加载新名单，无需手动重启。
    
4. 远程更新
    
    - 异常状态确认：若 `/set_cookie` 后仍报 503，请确认 RSSHub 容器是否成功读取了不带单引号的变量。
    - 重载配置：极端情况下，进入 RSSHub 目录执行以下命令是最彻底的刷新方式：
        
        bash
        
        运行
        
        ```
        docker compose up -d --force-recreate
        ```