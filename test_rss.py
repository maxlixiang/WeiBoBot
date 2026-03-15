import feedparser

def test_weibo_rss(uid):
    # 这是 RSSHub 的微博用户通用接口
    url = f"http://131.143.214.250:1200/weibo/user/{uid}"
    print(f"⏳ 正在请求数据，请稍候...\n🔗 目标链接: {url}\n")

    # 使用 feedparser 解析网页内容
    feed = feedparser.parse(url)

    # 检查是否成功抓取到内容
    if not feed.entries:
        print("❌ 获取失败！")
        print("原因可能是：\n1. UID 不正确\n2. 官方 RSSHub 节点正在被微博限制（请求过多）")
        return

    # 打印博主信息
    print(f"✅ 成功连接到博主：【{feed.feed.title}】\n")
    print("👇 下面是 TA 的最新 3 条微博：\n" + "="*40)

    # 遍历最新的 3 条微博并打印
    for i, entry in enumerate(feed.entries[:3]):
        # RSSHub 默认把微博正文放在 title 和 description 里
        print(f"[{i+1}] 发布时间: {entry.published}")
        print(f"📝 内容: {entry.title}")
        print(f"🔗 链接: {entry.link}")
        print("-" * 40)

if __name__ == '__main__':
    my_uid = input("🎯 请输入你想测试的微博 UID: ")
    test_weibo_rss(my_uid)