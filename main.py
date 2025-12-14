import requests
import os
from datetime import datetime
import html

# 1. 获取 GitHub Secrets
BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
CHAT_ID = os.environ.get("TG_CHAT_ID")

def fetch_epic_data(locale="en-US"):
    """
    通用函数：根据语言获取 Epic 数据
    """
    # 加上 locale 参数来请求不同语言的数据
    url = f"https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale={locale}&country=CN&allowCountries=CN"
    try:
        res = requests.get(url).json()
        return res['data']['Catalog']['searchStore']['elements']
    except Exception as e:
        print(f"获取 {locale} 数据出错: {e}")
        return []

def get_epic_free_games():
    # 1. 获取英文数据 (作为主数据，图片通常更全)
    games_en = fetch_epic_data("en-US")
    # 2. 获取中文数据 (用来提取中文标题)
    games_cn = fetch_epic_data("zh-CN")

    if not games_en:
        return []

    # 创建一个字典，方便通过 ID 查找中文标题
    # 格式: { "游戏ID": "中文标题" }
    cn_title_map = {}
    if games_cn:
        for g in games_cn:
            cn_title_map[g['id']] = g['title']

    free_games = []

    for game in games_en:
        # ---------------- 过滤逻辑 ----------------
        promotions = game.get('promotions')
        if not promotions: continue
        if not promotions.get('promotionalOffers'): continue
        
        # 注释掉 offerType 过滤，防止漏掉大作
        # offer_type = game.get('offerType')
        # if offer_type and offer_type != 'BASE_GAME': continue

        offers = promotions['promotionalOffers']
        if not offers: continue

        is_free = False
        end_date_str = "未知"

        for offer_group in offers:
            for offer in offer_group['promotionalOffers']:
                if offer['discountSetting']['discountPercentage'] == 0:
                    is_free = True
                    raw_date = offer.get('endDate')
                    if raw_date:
                        try:
                            dt = datetime.strptime(raw_date.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                            end_date_str = dt.strftime("%Y-%m-%d %H:%M") + " (UTC)"
                        except:
                            end_date_str = raw_date
                    break
        
        # ---------------- 提取信息 ----------------
        if is_free:
            title_en = game.get('title')
            game_id = game.get('id')
            
            # 【新】尝试获取中文标题
            title_cn = cn_title_map.get(game_id)
            
            # 如果中文名存在且和英文名不一样，就组合显示
            # 例如: "Hogwarts Legacy (霍格沃茨之遗)"
            if title_cn and title_cn != title_en:
                display_title = f"{title_en} <br/>({title_cn})"
            else:
                display_title = title_en

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
                "title": display_title,
                "description": description,
                "link": link,
                "image": image_url,
                "end_date": end_date_str
            })
            
    return free_games

def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ 错误：未设置 Token 或 Chat ID")
        return
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML", 
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"❌ 推送错误: {e}")

if __name__ == "__main__":
    print("⏳ 开始检查 Epic 免费游戏 (双语版)...")
    games = get_epic_free_games()
    
    if games:
        print(f"🎉 发现 {len(games)} 个免费游戏")
        for g in games:
            # 标题已经是处理过的 HTML 格式 (含<br/>)，不需要再 escape
            safe_title = g['title'] 
            safe_desc = html.escape(g['description'])
            
            msg = (
                f"<a href='{g['image']}'>&#8205;</a>"
                f"🔥 <b>Epic 喜加一提醒</b> 🔥\n\n"
                f"🎮 <b>{safe_title}</b>\n"
                f"⏰ 截止: {g['end_date']}\n\n"
                f"📝 {safe_desc}\n\n"
                f"🔗 <a href='{g['link']}'>点击领取游戏</a>"
            )
            send_telegram_message(msg)
    else:
        print("🤷‍♂️ 当前没有检测到免费游戏")
