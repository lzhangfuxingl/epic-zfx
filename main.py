import requests
import os
from datetime import datetime, timedelta, timezone
import html
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

# 定义北京时间时区
beijing_tz = timezone(timedelta(hours=8))

def get_epic_free_games():
    url = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US"
    try:
        res = requests.get(url).json()
        game_list = res['data']['Catalog']['searchStore']['elements']

        free_games = []
        for game in game_list:
            # 1. 基础过滤
            promotions = game.get('promotions')
            if not promotions: continue
            if not promotions.get('promotionalOffers'): continue

            offers = promotions['promotionalOffers']
            if not offers: continue

            is_free = False
            start_date = "未知"
            end_date = "未知"
            end_date_str = "未知"
            time_diff = "未知"
            is_new_game = False  # 标记是否为新上架的游戏

            for offer_group in offers:
                for offer in offer_group['promotionalOffers']:
                    if offer['discountSetting']['discountPercentage'] == 0:
                        is_free = True

                        # Time formatting
                        raw_end_date = offer.get('endDate')
                        print(f"json读取截止时间: {raw_end_date}")
                        raw_start_date = offer.get('startDate')  # 获取开始时间
                        print(f"json读取开始时间: {raw_start_date}")

                        # 处理开始时间
                        if raw_start_date:
                            try:
                                dt_start_utc = datetime.strptime(raw_start_date.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                                dt_start_utc = dt_start_utc.replace(tzinfo=timezone.utc)
                                dt_start_beijing = dt_start_utc.astimezone(beijing_tz)
                                start_date = dt_start_beijing.strftime("%Y-%m-%d")
                            except:
                                start_date = raw_start_date

                        # 处理截止时间
                        if raw_end_date:
                            try:
                                dt_end_utc = datetime.strptime(raw_end_date.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                                dt_end_utc = dt_end_utc.replace(tzinfo=timezone.utc)  # 添加 UTC 时区
                                dt_end_beijing = dt_end_utc.astimezone(beijing_tz)  # 转换为北京时间
                                end_date_str = dt_end_beijing.strftime("%Y-%m-%d %H:%M:%S") + " (北京时间)"
                                end_date = dt_end_beijing.strftime("%Y-%m-%d")
                            except:
                                end_date_str = raw_end_date
                                end_date = raw_end_date

                        print(f"处理后的开始日期: {start_date}")
                        print(f"处理后的结束日期: {end_date}")
                        print(f"处理后的截止时间: {end_date_str}")
                        # 【核心逻辑】判断游戏是否“刚上架”
                        # 只有在促销开始的 72 小时内检测到，才算“新消息”并推送。
                        # 72小时是为了容错（GitHub Action 可能会排队延迟几分钟）
                        if raw_start_date:
                            try:
                                dt_start_utc = datetime.strptime(raw_start_date.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                                dt_start_utc = dt_start_utc.replace(tzinfo=timezone.utc)  # 添加 UTC 时区
                                dt_start_beijing = dt_start_utc.astimezone(beijing_tz)  # 转换为北京时间
                                print(f"促销开始时间（北京时间）: {dt_start_beijing}")
                                # 获取当前北京时间
                                now_beijing = datetime.now(timezone.utc).astimezone(beijing_tz)
                                print(f"当前北京时间: {now_beijing}")
                                # 计算时间差
                                time_diff = now_beijing - dt_start_beijing
                                print(f"时间差: {time_diff}")

                                # 如果时间差小于 28 小时，说明是刚出的新游戏 -> 推送
                                # 如果时间差大于 28 小时，说明是昨天的旧消息 -> 不推送
                                if time_diff < timedelta(hours=140):
                                    is_new_game = True
                                else:
                                    print(f"跳过旧游戏: {game.get('title')} (已上架 {time_diff})")
                            except Exception as e:
                                print(f"时间解析错误: {e}")
                                # 如果时间解析失败，为了保险起见，默认它是新的，防止漏发
                                is_new_game = True
                        else:
                            is_new_game = True  # 没有开始时间的数据，默认发送

                        break

            # 只有当它是免费 且 是新上架的游戏时，才加入列表
            if is_free and is_new_game:
                title = game.get('title')
                description = game.get('description', '暂无描述')
                slug = game.get('productSlug') or game.get('urlSlug')
                link = f"https://store.epicgames.com/p/{slug}" if slug else "https://store.epicgames.com/free-games"

                image_url = ""
                for img in game.get('keyImages', []):
                    if img.get('type') == 'Thumbnail':
                        image_url = img.get('url')
                        break
                    elif img.get('type') == 'OfferImageWide':
                        image_url = img.get('url')

                free_games.append({
                    "title": title,
                    "description": description,
                    "image": image_url,
                    "end_date": end_date,
                    "start_date": start_date,
                    "end_time": end_date_str,
                    "time_diff": time_diff
                })

        return free_games

    except Exception as e:
        print(f"获取 Epic 数据出错: {e}")
        return []


def send_notice_by_mail(title, description, image_url, start_date, end_date, end_time,time_diff):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")

    print("开始发送邮件...")

    if not gmail_user or not gmail_password:
        raise ValueError("请设置环境变量 GMAIL_USER 和 GMAIL_APP_PASSWORD")

    print("发件人邮箱：" + gmail_user)

    email_list_str = os.environ.get("EMAIL_LIST", "")
    if not email_list_str:
        raise ValueError("请设置环境变量 EMAIL_LIST，多个邮箱用逗号分隔")
    to_emails = [email.strip() for email in email_list_str.split(",")]

    print("收件人列表:", to_emails)

    # 配置 SMTP 服务器信息
    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    subject = "Epic喜加一提醒"+"("+start_date+"~"+end_date+")"

    # 替换 HTML 中的标题内容
    html_content = f"""<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{subject}</title>
        <style type="text/css">
            * {{
                margin: 0;
                padding: 0;
            }}
        </style>
    </head>
    <body>
        <div style="width: 100vw;height: 100vh;background: #f0f9ff;
                    display: flex; flex-direction: column;justify-content: right;align-items: center;">
            <h2 style="margin-top: 5vh">🔥{subject}🔥</h2>
            <img src="{image_url}"
                 alt="游戏宣传图" style="width: 35vw; height: 50vh;"/>
            <h2 style="margin-top: 1.5vh">🎮 {title}</h2>
            <h3 style="margin-top: 0.6vh">⏰ 截止: {end_time}</h3>
            <h3 style="margin-top: 0.6vh; width: 50vw; text-align: justify;">📝{description}</h3>
            <h3 style="margin-top: 0.6vh">📆已发布时间: {time_diff}</h3>
        </div>
    </body>
</html>"""

    # 创建邮件对象
    max_retries = 3
    retry_delay = 5  # 重试间隔（秒）

    for to_email in to_emails:
        # 创建邮件对象
        email_msg = MIMEMultipart()
        email_msg['From'] = gmail_user
        email_msg['To'] = to_email
        email_msg['Subject'] = subject

        # 添加 HTML 内容
        email_msg.attach(MIMEText(html_content, 'html'))

        for attempt in range(max_retries):
            try:
                with smtplib.SMTP(smtp_server, smtp_port, timeout=60) as server:
                    server.starttls()  # 启用 TLS 加密
                    server.login(gmail_user, gmail_password)
                    server.sendmail(gmail_user, to_email, email_msg.as_string())
                print(f"✅ 邮件发送成功至 {to_email}！")
                break
            except Exception as e:
                print(f"❌ 第 {attempt + 1} 次尝试失败: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    print(f"❌ 所有重试均失败，无法发送邮件至 {to_email}")


if __name__ == "__main__":
    print("⏳ 开始检查 Epic 免费游戏 (每日去重版)...")
    games = get_epic_free_games()

    if games:
        print(f"🎉 发现 {len(games)} 个新上架的免费游戏")
        for g in games:
            safe_title = html.escape(g['title'])
            safe_desc = html.escape(g['description'])
            send_notice_by_mail(safe_title, safe_desc, g['image'],g['start_date'], g['end_date'], g['end_time'],g['time_diff'])
    else:
        print("🤷‍♂️ 今天没有新上架的免费游戏 (可能是旧游戏已通知过)")