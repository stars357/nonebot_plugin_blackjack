import sqlite3
import datetime
import random
from typing import Dict, List, Tuple, Optional, Union
from .sign import get_point, update_point, check_supreme_card, add_supreme_card
from .resource import (
    get_user_resource, update_user_resource, get_user_stamina, update_user_stamina,
    RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE, MAX_STAMINA, RESOURCE_PRICES
)
from .profession import get_tool_durability, update_tool_durability, get_special_resource, update_special_resource
from .common import (
    TOOL_IRON, TOOL_FINE_GOLD, TOOL_ALLOY, TOOL_ALLOY_PERM,
    TOOL_TYPE_PICKAXE, TOOL_TYPE_HOE, TOOL_TYPE_AXE,
    SPECIAL_BLUE_GEM, SPECIAL_SUPER_PLANT, SPECIAL_DEMON_BRANCH,
    TOOL_DURABILITY
)
from .db import db_tool

# 商品类型常量
ITEM_SUPREME_CARD = 0    # 至尊签到卡
ITEM_LUXURY_HOUSE = 1    # 400平大别野
ITEM_PRODUCTION_CARD = 2 # 生产加倍卡
ITEM_STAMINA_CARD = 3    # 体力恢复卡

# 商品价格
ITEM_PRICES = {
    ITEM_SUPREME_CARD: 200000,     # 至尊签到卡：200000金币/张
    ITEM_LUXURY_HOUSE: 3000000,    # 400平大别野：3000000金币/套
    ITEM_PRODUCTION_CARD: 3000,    # 生产加倍卡：3000金币/张
    ITEM_STAMINA_CARD: 1200        # 体力恢复卡：1200金币/张
}

# 彩票面额和奖励
LOTTERY_TYPES = {
    500: [
        (0.70, 100),   # 70%概率中100
        (0.20, 500),   # 20%概率中500
        (0.07, 750),   # 7%概率中750
        (0.02, 1000),  # 2%概率中1000
        (0.01, 5000)   # 1%概率中5000
    ],
    1000: [
        (0.70, 200),    # 70%概率中200
        (0.20, 1000),   # 20%概率中1000
        (0.07, 1500),   # 7%概率中1500
        (0.02, 2000),   # 2%概率中2000
        (0.01, 10000)   # 1%概率中10000
    ],
    5000: [
        (0.70, 1000),   # 70%概率中1000
        (0.20, 5000),   # 20%概率中5000
        (0.07, 7500),   # 7%概率中7500
        (0.02, 10000),  # 2%概率中10000
        (0.01, 50000)   # 1%概率中50000
    ],
    10000: [
        (0.70, 2000),    # 70%概率中2000
        (0.20, 10000),   # 20%概率中10000
        (0.07, 15000),   # 7%概率中15000
        (0.02, 20000),   # 2%概率中20000
        (0.01, 100000)   # 1%概率中100000
    ],
    20000: [
        (0.70, 4000),    # 70%概率中4000
        (0.20, 20000),   # 20%概率中20000
        (0.07, 30000),   # 7%概率中30000
        (0.02, 40000),   # 2%概率中40000
        (0.01, 200000)   # 1%概率中200000
    ]
}

# 资源价格波动记录
resource_price_changes: Dict[Tuple[int, int], Dict[str, float]] = {}

# 生产加倍卡使用记录 {(group_id, user_id): remaining_uses}
production_card_uses: Dict[Tuple[int, int], int] = {}

# 体力恢复卡每日购买记录 {(group_id, user_id, date): count}
stamina_card_purchases: Dict[Tuple[int, int, str], int] = {}

# 玩家市场挂单记录
market_listings: Dict[int, Dict] = {}

# 市场挂单ID计数器
market_listing_counter: Dict[int, int] = {}

def init_market_db():
    """初始化市场数据库"""
    # 创建物品表
    sql = """
    CREATE TABLE IF NOT EXISTS user_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        item_type INTEGER NOT NULL,  -- 0: 至尊签到卡, 1: 400平大别野, 2: 生产加倍卡, 3: 体力恢复卡
        amount INTEGER NOT NULL DEFAULT 0,
        UNIQUE(uid, belonging_group, item_type)
    )
    """
    db_tool.execute_update(sql)
    
    # 创建生产加倍卡使用记录表
    sql = """
    CREATE TABLE IF NOT EXISTS production_card_uses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        remaining_uses INTEGER NOT NULL DEFAULT 0,
        UNIQUE(uid, belonging_group)
    )
    """
    db_tool.execute_update(sql)
    
    # 创建体力恢复卡购买记录表
    sql = """
    CREATE TABLE IF NOT EXISTS stamina_card_purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        purchase_date DATE NOT NULL,
        count INTEGER NOT NULL DEFAULT 0,
        UNIQUE(uid, belonging_group, purchase_date)
    )
    """
    db_tool.execute_update(sql)
    
    # 创建资源价格表
    sql = """
    CREATE TABLE IF NOT EXISTS resource_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        belonging_group INTEGER NOT NULL,
        resource_type INTEGER NOT NULL,  -- 0: 食物, 1: 木材, 2: 矿石
        base_price REAL NOT NULL,
        current_price REAL NOT NULL,
        last_update DATE NOT NULL,
        daily_trade_volume INTEGER NOT NULL DEFAULT 0,
        UNIQUE(belonging_group, resource_type)
    )
    """
    db_tool.execute_update(sql)
    
    # 创建玩家市场挂单表
    sql = """
    CREATE TABLE IF NOT EXISTS market_listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        listing_id INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        seller_id INTEGER NOT NULL,
        item_type INTEGER NOT NULL,  -- 0: 资源, 1: 工具, 2: 特殊材料
        resource_type INTEGER,       -- 0: 食物, 1: 木材, 2: 矿石, NULL if item_type != 0
        tool_type INTEGER,           -- 工具类型，NULL if item_type != 1
        tool_category INTEGER,       -- 工具种类，NULL if item_type != 1
        special_resource_type INTEGER, -- 特殊材料类型，NULL if item_type != 2
        price_per_unit REAL NOT NULL,
        quantity INTEGER NOT NULL,
        listing_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(belonging_group, listing_id)
    )
    """
    db_tool.execute_update(sql)

def get_user_item(group_id: int, user_id: int, item_type: int) -> int:
    """获取用户物品数量"""
    init_market_db()
    
    sql = f"SELECT amount FROM user_items WHERE uid={user_id} AND belonging_group={group_id} AND item_type={item_type}"
    result = db_tool.execute_query(sql)
    
    if not result:
        # 创建新记录
        sql = f"INSERT INTO user_items (uid, belonging_group, item_type, amount) VALUES ({user_id}, {group_id}, {item_type}, 0)"
        db_tool.execute_update(sql)
        amount = 0
    else:
        amount = int(result[0][0])
    
    return amount

def update_user_item(group_id: int, user_id: int, item_type: int, amount: int) -> None:
    """更新用户物品数量"""
    init_market_db()
    
    # 确保数量不为负
    amount = max(0, amount)
    
    sql = f"SELECT id FROM user_items WHERE uid={user_id} AND belonging_group={group_id} AND item_type={item_type}"
    result = db_tool.execute_query(sql)
    
    if not result:
        # 创建新记录
        sql = f"INSERT INTO user_items (uid, belonging_group, item_type, amount) VALUES ({user_id}, {group_id}, {item_type}, {amount})"
    else:
        # 更新记录
        sql = f"UPDATE user_items SET amount={amount} WHERE uid={user_id} AND belonging_group={group_id} AND item_type={item_type}"
    
    db_tool.execute_update(sql)

def get_resource_price(group_id: int, resource_type: int) -> float:
    """获取资源当前价格"""
    init_market_db()
    
    today = datetime.date.today().isoformat()
    
    # 检查是否有价格记录
    sql = f"SELECT current_price, last_update, daily_trade_volume FROM resource_prices WHERE belonging_group={group_id} AND resource_type={resource_type}"
    result = db_tool.execute_query(sql)
    
    if not result:
        # 创建新记录，使用基准价格
        base_price = RESOURCE_PRICES[resource_type]
        sql = f"INSERT INTO resource_prices (belonging_group, resource_type, base_price, current_price, last_update, daily_trade_volume) VALUES ({group_id}, {resource_type}, {base_price}, {base_price}, '{today}', 0)"
        db_tool.execute_update(sql)
        price = base_price
    else:
        price, last_update, trade_volume = result[0]
        price = float(price)
        
        # 检查是否需要重置每日交易量
        if last_update != today:
            # 重置每日交易量
            sql = f"UPDATE resource_prices SET daily_trade_volume=0, last_update='{today}' WHERE belonging_group={group_id} AND resource_type={resource_type}"
            db_tool.execute_update(sql)
    
    return price

def update_resource_price(group_id: int, resource_type: int, trade_volume: int) -> float:
    """更新资源价格（根据交易量）"""
    init_market_db()
    
    # 获取当前价格和交易量
    sql = f"SELECT base_price, current_price, daily_trade_volume FROM resource_prices WHERE belonging_group={group_id} AND resource_type={resource_type}"
    result = db_tool.execute_query(sql)
    
    if not result:
        # 如果没有记录，先获取价格
        price = get_resource_price(group_id, resource_type)
        return price
    
    base_price, current_price, daily_trade_volume = result[0]
    base_price = float(base_price)
    current_price = float(current_price)
    daily_trade_volume = int(daily_trade_volume)
    
    # 更新交易量
    new_trade_volume = daily_trade_volume + abs(trade_volume)
    
    # 计算价格变化（每100单位交易量导致1%基准价格变化）
    price_change_percent = round((new_trade_volume - daily_trade_volume) / 100 * 0.01, 2)
    
    # 如果是购买，价格上涨；如果是出售，价格下跌
    if trade_volume > 0:  # 购买
        price_change = round(base_price * price_change_percent, 2)
    else:  # 出售
        price_change = round(-base_price * price_change_percent, 2)
    
    # 计算新价格
    new_price = round(current_price + price_change, 2)
    
    # 确保价格不超过每日最大波动（基准价格的50%）
    min_price = base_price * 0.5
    max_price = base_price * 1.5
    new_price = round(max(min_price, min(max_price, new_price)), 2)  # 保留两位小数
    
    # 更新数据库
    today = datetime.date.today().isoformat()
    sql = f"UPDATE resource_prices SET current_price={new_price}, daily_trade_volume={new_trade_volume}, last_update='{today}' WHERE belonging_group={group_id} AND resource_type={resource_type}"
    db_tool.execute_update(sql)
    
    return new_price

def get_production_card_uses(group_id: int, user_id: int) -> int:
    """获取用户生产加倍卡剩余使用次数"""
    # 先检查内存中是否有记录
    if (group_id, user_id) in production_card_uses:
        return production_card_uses[(group_id, user_id)]
    
    init_market_db()
    
    sql = f"SELECT remaining_uses FROM production_card_uses WHERE uid={user_id} AND belonging_group={group_id}"
    result = db_tool.execute_query(sql)
    
    if not result:
        # 创建新记录
        sql = f"INSERT INTO production_card_uses (uid, belonging_group, remaining_uses) VALUES ({user_id}, {group_id}, 0)"
        db_tool.execute_update(sql)
        remaining_uses = 0
    else:
        remaining_uses = int(result[0][0])
    
    # 更新内存记录
    production_card_uses[(group_id, user_id)] = remaining_uses
    
    return remaining_uses

def update_production_card_uses(group_id: int, user_id: int, remaining_uses: int) -> None:
    """更新用户生产加倍卡剩余使用次数"""
    init_market_db()
    
    # 确保次数不为负
    remaining_uses = max(0, remaining_uses)
    
    sql = f"SELECT id FROM production_card_uses WHERE uid={user_id} AND belonging_group={group_id}"
    result = db_tool.execute_query(sql)
    
    if not result:
        # 创建新记录
        sql = f"INSERT INTO production_card_uses (uid, belonging_group, remaining_uses) VALUES ({user_id}, {group_id}, {remaining_uses})"
    else:
        # 更新记录
        sql = f"UPDATE production_card_uses SET remaining_uses={remaining_uses} WHERE uid={user_id} AND belonging_group={group_id}"
    
    db_tool.execute_update(sql)
    
    # 更新内存记录
    production_card_uses[(group_id, user_id)] = remaining_uses

def get_stamina_card_purchases(group_id: int, user_id: int) -> int:
    """获取用户今日体力恢复卡购买次数"""
    today = datetime.date.today().isoformat()
    
    # 先检查内存中是否有记录
    if (group_id, user_id, today) in stamina_card_purchases:
        return stamina_card_purchases[(group_id, user_id, today)]
    
    init_market_db()
    
    sql = f"SELECT count FROM stamina_card_purchases WHERE uid={user_id} AND belonging_group={group_id} AND purchase_date='{today}'"
    result = db_tool.execute_query(sql)
    
    if not result:
        # 创建新记录
        sql = f"INSERT INTO stamina_card_purchases (uid, belonging_group, purchase_date, count) VALUES ({user_id}, {group_id}, '{today}', 0)"
        db_tool.execute_update(sql)
        count = 0
    else:
        count = int(result[0][0])
    
    # 更新内存记录
    stamina_card_purchases[(group_id, user_id, today)] = count
    
    return count

def update_stamina_card_purchases(group_id: int, user_id: int, count: int) -> None:
    """更新用户今日体力恢复卡购买次数"""
    today = datetime.date.today().isoformat()
    
    init_market_db()
    
    # 确保次数不为负
    count = max(0, count)
    
    sql = f"SELECT id FROM stamina_card_purchases WHERE uid={user_id} AND belonging_group={group_id} AND purchase_date='{today}'"
    result = db_tool.execute_query(sql)
    
    if not result:
        # 创建新记录
        sql = f"INSERT INTO stamina_card_purchases (uid, belonging_group, purchase_date, count) VALUES ({user_id}, {group_id}, '{today}', {count})"
    else:
        # 更新记录
        sql = f"UPDATE stamina_card_purchases SET count={count} WHERE uid={user_id} AND belonging_group={group_id} AND purchase_date='{today}'"
    
    db_tool.execute_update(sql)
    
    # 更新内存记录
    stamina_card_purchases[(group_id, user_id, today)] = count

def get_next_listing_id(group_id: int) -> int:
    """获取下一个市场挂单ID"""
    if group_id not in market_listing_counter:
        init_market_db()
        
        # 获取当前最大ID
        sql = f"SELECT MAX(listing_id) FROM market_listings WHERE belonging_group={group_id}"
        result = db_tool.execute_query(sql)
        
        if not result or result[0][0] is None:
            market_listing_counter[group_id] = 1
        else:
            market_listing_counter[group_id] = int(result[0][0]) + 1
    else:
        market_listing_counter[group_id] += 1
    
    return market_listing_counter[group_id]

# 系统商店功能
def buy_item(group_id: int, user_id: int, item_type: int, amount: int = 1) -> str:
    """购买商店物品"""
    # 检查物品类型是否有效
    if item_type not in ITEM_PRICES:
        return "无效的物品类型！"
    
    # 获取物品价格
    price = ITEM_PRICES[item_type] * amount
    
    # 获取用户金币
    user_coins = get_point(group_id, user_id)
    
    # 检查金币是否足够
    if user_coins < price:
        return f"金币不足！需要{price}金币，当前持有{user_coins}金币。"
    
    # 特殊物品限制检查
    if item_type == ITEM_SUPREME_CARD:
        # 至尊签到卡限制每人只能持有1张
        current_amount = get_user_item(group_id, user_id, item_type)
        if current_amount > 0 or check_supreme_card(user_id, group_id):
            return "你已经拥有至尊签到卡，无法再次购买！"
        if amount > 1:
            return "至尊签到卡每人只能持有1张！"
    
    elif item_type == ITEM_LUXURY_HOUSE:
        # 400平大别野限制每人只能持有1套
        current_amount = get_user_item(group_id, user_id, item_type)
        if current_amount > 0:
            return "你已经拥有400平大别野，无法再次购买！"
        if amount > 1:
            return "400平大别野每人只能持有1套！"
    
    elif item_type == ITEM_STAMINA_CARD:
        # 体力恢复卡每天限购1张
        daily_purchases = get_stamina_card_purchases(group_id, user_id)
        if daily_purchases >= 1:
            return "体力恢复卡每天限购1张，今天已经购买过了！"
        if amount > 1:
            return "体力恢复卡每天限购1张！"
        # 更新购买记录
        update_stamina_card_purchases(group_id, user_id, daily_purchases + 1)
    
    # 扣除金币
    update_point(group_id, user_id, user_coins - price)
    
    # 更新物品数量
    current_amount = get_user_item(group_id, user_id, item_type)
    update_user_item(group_id, user_id, item_type, current_amount + amount)
    
    # 如果是至尊签到卡，添加到签到卡表
    if item_type == ITEM_SUPREME_CARD:
        add_supreme_card(user_id, group_id)
    
    # 返回购买成功消息
    item_names = {
        ITEM_SUPREME_CARD: "至尊签到卡",
        ITEM_LUXURY_HOUSE: "400平大别野",
        ITEM_PRODUCTION_CARD: "生产加倍卡",
        ITEM_STAMINA_CARD: "体力恢复卡"
    }
    
    return f"购买成功！花费{price}金币购买了{amount}个{item_names[item_type]}。\n当前剩余金币：{user_coins - price}"

# 使用物品功能
def use_production_card(group_id: int, user_id: int) -> str:
    """使用生产加倍卡"""
    # 检查是否有生产加倍卡
    card_amount = get_user_item(group_id, user_id, ITEM_PRODUCTION_CARD)
    if card_amount <= 0:
        return "你没有生产加倍卡！"
    
    # 检查是否已有生产加倍效果
    remaining_uses = get_production_card_uses(group_id, user_id)
    if remaining_uses > 0:
        return f"你已经有生产加倍效果，剩余{remaining_uses}次使用次数！"
    
    # 减少物品数量
    update_user_item(group_id, user_id, ITEM_PRODUCTION_CARD, card_amount - 1)
    
    # 添加10次使用次数
    update_production_card_uses(group_id, user_id, 10)
    
    return "成功使用生产加倍卡！接下来10次生产时，产量将翻倍。"

def use_stamina_card(group_id: int, user_id: int) -> str:
    """使用体力恢复卡"""
    # 检查是否有体力恢复卡
    card_amount = get_user_item(group_id, user_id, ITEM_STAMINA_CARD)
    if card_amount <= 0:
        return "你没有体力恢复卡！"
    
    # 获取当前体力
    current_stamina = get_user_stamina(group_id, user_id)
    if current_stamina >= MAX_STAMINA:
        return f"你的体力已满（{MAX_STAMINA}/{MAX_STAMINA}），无需使用体力恢复卡！"
    
    # 减少物品数量
    update_user_item(group_id, user_id, ITEM_STAMINA_CARD, card_amount - 1)
    
    # 恢复100点体力，不超过上限
    new_stamina = min(MAX_STAMINA, current_stamina + 100)
    update_user_stamina(group_id, user_id, new_stamina)
    
    return f"成功使用体力恢复卡！体力恢复了100点，当前体力：{new_stamina}/{MAX_STAMINA}"

# 彩票系统
def buy_lottery(group_id: int, user_id: int, amount: int) -> str:
    """购买彩票"""
    # 检查彩票面额是否有效
    if amount not in LOTTERY_TYPES:
        return f"无效的彩票面额！可选面额：{', '.join(map(str, LOTTERY_TYPES.keys()))}"
    
    # 获取用户金币
    user_coins = get_point(group_id, user_id)
    
    # 检查金币是否足够
    if user_coins < amount:
        return f"金币不足！需要{amount}金币，当前持有{user_coins}金币。"
    
    # 扣除金币
    update_point(group_id, user_id, user_coins - amount)
    
    # 随机抽取奖励
    lottery_rewards = LOTTERY_TYPES[amount]
    rand = random.random()
    cumulative_prob = 0
    
    for prob, reward in lottery_rewards:
        cumulative_prob += prob
        if rand < cumulative_prob:
            # 中奖
            update_point(group_id, user_id, user_coins - amount + reward)
            return f"恭喜！你花费{amount}金币购买彩票，中奖{reward}金币！\n当前剩余金币：{user_coins - amount + reward}"
    
    # 理论上不会执行到这里，但为了安全起见
    return "彩票开奖出错，请联系管理员！"

# 系统收购功能
def sell_to_system(group_id: int, user_id: int, resource_type: int, amount: int) -> str:
    """将资源卖给系统"""
    # 检查资源类型是否有效
    if resource_type not in [RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE]:
        return "无效的资源类型！可选：食物、木材、矿石"
    
    # 检查数量是否有效
    if amount <= 0:
        return "请输入正确的数量！"
    
    # 获取用户资源数量
    user_resource = get_user_resource(group_id, user_id, resource_type)
    
    # 检查资源是否足够
    if user_resource < amount:
        resource_names = {RESOURCE_FOOD: "食物", RESOURCE_WOOD: "木材", RESOURCE_ORE: "矿石"}
        return f"资源不足！你只有{user_resource}个{resource_names[resource_type]}，无法出售{amount}个。"
    
    # 获取资源当前价格
    price = get_resource_price(group_id, resource_type)
    
    # 检查用户是否是商业联盟成员或富豪榜前三
    from .alliance import check_business_alliance_bonus
    from .casino import get_casino_leaderboard
    
    # 检查是否是商业联盟成员
    is_business_member = check_business_alliance_bonus(group_id, user_id)
    
    # 检查是否在富豪榜前三
    is_top_three = False
    
    # 直接查询数据库获取富豪榜前三名
    # 联合查询金币和银行存款，获取前三名用户
    sql = f"""
    SELECT s.uid, s.points + COALESCE(b.balance, 0) as total_wealth 
    FROM sign_in s 
    LEFT JOIN bank_accounts b ON s.uid = b.uid AND s.belonging_group = b.belonging_group 
    WHERE s.belonging_group = {group_id} 
    ORDER BY total_wealth DESC 
    LIMIT 3
    """
    top_three_users = db_tool.execute_query(sql)
    
    # 检查用户是否在前三名
    for top_user_id, _ in top_three_users:
        if top_user_id == user_id:
            is_top_three = True
            break
    
    # 计算总价值（根据特权决定是否扣除交易税）
    tax_free = is_business_member or is_top_three
    total_value = price * amount if tax_free else price * amount * 0.8
    tax_info = "（免交易税）" if tax_free else "（收取20%交易税）"
    
    # 更新用户资源
    update_user_resource(group_id, user_id, resource_type, user_resource - amount)
    
    # 更新用户金币
    user_coins = get_point(group_id, user_id)
    update_point(group_id, user_id, user_coins + total_value)
    
    # 更新资源价格（出售导致价格下跌）
    new_price = update_resource_price(group_id, resource_type, -amount)
    
    resource_names = {RESOURCE_FOOD: "食物", RESOURCE_WOOD: "木材", RESOURCE_ORE: "矿石"}
    return f"成功出售{amount}个{resource_names[resource_type]}给系统！\n单价：{price:.2f}金币{tax_info}\n获得金币：{total_value:.2f}\n当前金币：{(user_coins + total_value):.2f}"

# 玩家市场功能
def create_market_listing(group_id: int, user_id: int, item_type: int, resource_type: int = None, tool_type: int = None, tool_category: int = None, special_resource_type: int = None, price_per_unit: float = 0, quantity: int = 1) -> str:
    """创建市场挂单"""
    # 检查物品类型是否有效
    if item_type not in [0, 1, 2]:  # 0: 资源, 1: 工具, 2: 特殊材料
        return "无效的物品类型！可选：0(资源), 1(工具), 2(特殊材料)"
    
    # 检查数量和价格是否有效
    if quantity <= 0 or price_per_unit <= 0:
        return "请输入正确的数量和价格！"
    
    # 根据物品类型进行不同的处理
    if item_type == 0:  # 资源类型
        # 检查资源类型是否有效
        if resource_type not in [RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE]:
            return "无效的资源类型！可选：食物、木材、矿石"
        
        # 获取用户资源数量
        user_resource = get_user_resource(group_id, user_id, resource_type)
        
        # 检查资源是否足够
        if user_resource < quantity:
            resource_names = {RESOURCE_FOOD: "食物", RESOURCE_WOOD: "木材", RESOURCE_ORE: "矿石"}
            return f"资源不足！你只有{user_resource}个{resource_names[resource_type]}，无法上架{quantity}个。"
        
        # 获取资源当前市场价格
        market_price = get_resource_price(group_id, resource_type)
        
        # 检查价格是否在允许范围内（不能上下浮动超过市场基准价格的50%）
        min_price = market_price * 0.5
        max_price = market_price * 1.5
        if price_per_unit < min_price or price_per_unit > max_price:
            return f"价格超出允许范围！当前市场价格为{market_price}金币，允许的价格范围为{min_price}~{max_price}金币。"
        
        # 扣除用户资源
        update_user_resource(group_id, user_id, resource_type, user_resource - quantity)
        
        # 创建挂单
        listing_id = get_next_listing_id(group_id)
        
        init_market_db()
        sql = f"INSERT INTO market_listings (listing_id, belonging_group, seller_id, item_type, resource_type, tool_type, tool_category, special_resource_type, price_per_unit, quantity) VALUES ({listing_id}, {group_id}, {user_id}, {item_type}, {resource_type}, NULL, NULL, NULL, {price_per_unit}, {quantity})"
        db_tool.execute_update(sql)
        
        resource_names = {RESOURCE_FOOD: "食物", RESOURCE_WOOD: "木材", RESOURCE_ORE: "矿石"}
        return f"成功创建市场挂单！\n挂单ID：{listing_id}\n资源类型：{resource_names[resource_type]}\n单价：{price_per_unit}金币\n数量：{quantity}\n总价值：{price_per_unit * quantity}金币"
    
    elif item_type == 1:  # 工具类型
        # 检查工具类型和种类是否有效
        if tool_type not in [TOOL_IRON, TOOL_FINE_GOLD, TOOL_ALLOY, TOOL_ALLOY_PERM]:
            return "无效的工具类型！可选：铁质工具、精金工具、强化合金工具、强化合金工具【不毁】"
        
        if tool_category not in [TOOL_TYPE_PICKAXE, TOOL_TYPE_HOE, TOOL_TYPE_AXE]:
            return "无效的工具种类！可选：镐、锄、斧"
        
        # 获取用户工具耐久度
        durability = get_tool_durability(group_id, user_id, tool_type, tool_category)
        
        # 检查工具是否存在
        if durability <= 0 and tool_type != TOOL_ALLOY_PERM:
            tool_type_names = {TOOL_IRON: "铁质", TOOL_FINE_GOLD: "精金", TOOL_ALLOY: "强化合金", TOOL_ALLOY_PERM: "强化合金【不毁】"}
            tool_category_names = {TOOL_TYPE_PICKAXE: "镐", TOOL_TYPE_HOE: "锄", TOOL_TYPE_AXE: "斧"}
            return f"你没有{tool_type_names[tool_type]}{tool_category_names[tool_category]}，无法上架。"
        
        # 对于不毁版工具，检查是否为-1（无限耐久）
        if tool_type == TOOL_ALLOY_PERM and durability != -1:
            return "你没有强化合金工具【不毁】，无法上架。"
        
        # 移除用户工具
        update_tool_durability(group_id, user_id, tool_type, tool_category, 0)
        
        # 创建挂单
        listing_id = get_next_listing_id(group_id)
        
        init_market_db()
        sql = f"INSERT INTO market_listings (listing_id, belonging_group, seller_id, item_type, resource_type, tool_type, tool_category, special_resource_type, price_per_unit, quantity) VALUES ({listing_id}, {group_id}, {user_id}, {item_type}, NULL, {tool_type}, {tool_category}, NULL, {price_per_unit}, 1)"
        db_tool.execute_update(sql)
        
        tool_type_names = {TOOL_IRON: "铁质", TOOL_FINE_GOLD: "精金", TOOL_ALLOY: "强化合金", TOOL_ALLOY_PERM: "强化合金【不毁】"}
        tool_category_names = {TOOL_TYPE_PICKAXE: "镐", TOOL_TYPE_HOE: "锄", TOOL_TYPE_AXE: "斧"}
        return f"成功创建市场挂单！\n挂单ID：{listing_id}\n工具类型：{tool_type_names[tool_type]}{tool_category_names[tool_category]}\n单价：{price_per_unit}金币\n总价值：{price_per_unit}金币"
    
    elif item_type == 2:  # 特殊材料类型
        # 检查特殊材料类型是否有效
        if special_resource_type not in [SPECIAL_BLUE_GEM, SPECIAL_SUPER_PLANT, SPECIAL_DEMON_BRANCH]:
            return "无效的特殊材料类型！可选：海蓝宝石、超级植株、恶魔树枝干"
        
        # 获取用户特殊材料数量
        user_special_resource = get_special_resource(group_id, user_id, special_resource_type)
        
        # 检查特殊材料是否足够
        if user_special_resource < quantity:
            special_resource_names = {SPECIAL_BLUE_GEM: "海蓝宝石", SPECIAL_SUPER_PLANT: "超级植株", SPECIAL_DEMON_BRANCH: "恶魔树枝干"}
            return f"特殊材料不足！你只有{user_special_resource}个{special_resource_names[special_resource_type]}，无法上架{quantity}个。"
        
        # 扣除用户特殊材料
        update_special_resource(group_id, user_id, special_resource_type, user_special_resource - quantity)
        
        # 创建挂单
        listing_id = get_next_listing_id(group_id)
        
        init_market_db()
        sql = f"INSERT INTO market_listings (listing_id, belonging_group, seller_id, item_type, resource_type, tool_type, tool_category, special_resource_type, price_per_unit, quantity) VALUES ({listing_id}, {group_id}, {user_id}, {item_type}, NULL, NULL, NULL, {special_resource_type}, {price_per_unit}, {quantity})"
        db_tool.execute_update(sql)
        
        special_resource_names = {SPECIAL_BLUE_GEM: "海蓝宝石", SPECIAL_SUPER_PLANT: "超级植株", SPECIAL_DEMON_BRANCH: "恶魔树枝干"}
        return f"成功创建市场挂单！\n挂单ID：{listing_id}\n特殊材料类型：{special_resource_names[special_resource_type]}\n单价：{price_per_unit}金币\n数量：{quantity}\n总价值：{price_per_unit * quantity}金币"
    
    return "创建挂单失败，请检查参数是否正确。"

def buy_from_market(group_id: int, user_id: int, listing_id: int, quantity: int) -> str:
    """从市场购买物品"""
    # 检查数量是否有效
    if quantity <= 0:
        return "请输入正确的数量！"
    
    # 获取挂单信息
    init_market_db()
    sql = f"SELECT seller_id, item_type, resource_type, tool_type, tool_category, special_resource_type, price_per_unit, quantity FROM market_listings WHERE belonging_group={group_id} AND listing_id={listing_id}"
    result = db_tool.execute_query(sql)
    
    if not result:
        return f"挂单不存在！ID：{listing_id}"
    
    seller_id, item_type, resource_type, tool_type, tool_category, special_resource_type, price_per_unit, available_quantity = result[0]
    
    # 检查是否是自己的挂单
    if seller_id == user_id:
        return "不能购买自己的挂单！"
    
    # 对于工具类型，只能购买1个
    if item_type == 1 and quantity > 1:
        return "工具类型每次只能购买1个！"
    
    # 检查数量是否足够
    if available_quantity < quantity:
        return f"挂单数量不足！只有{available_quantity}个，无法购买{quantity}个。"
    
    # 计算总价值
    total_price = price_per_unit * quantity
    
    # 获取用户金币
    user_coins = get_point(group_id, user_id)
    
    # 检查金币是否足够
    if user_coins < total_price:
        return f"金币不足！需要{total_price}金币，当前持有{user_coins}金币。"
    
    # 更新用户金币（扣除购买金额）
    update_point(group_id, user_id, user_coins - total_price)
    
    # 检查卖家是否是商业联盟成员或富豪榜前三
    from .alliance import check_business_alliance_bonus
    from .casino import get_casino_leaderboard
    
    # 检查是否是商业联盟成员
    is_business_member = check_business_alliance_bonus(group_id, seller_id)
    
    # 检查是否在富豪榜前三
    is_top_three = False
    leaderboard = get_casino_leaderboard(group_id, 3)
    if not isinstance(leaderboard, str):
        return "获取富豪榜失败"
    
    # 解析富豪榜信息，检查用户是否在前三名
    for line in leaderboard.split('\n'):
        if line.startswith("1.") or line.startswith("2.") or line.startswith("3."):
            if f"用户{seller_id}:" in line:
                is_top_three = True
                break
    
    # 计算卖家收入（根据特权决定是否扣除交易税）
    tax_free = is_business_member or is_top_three
    seller_income = total_price if tax_free else total_price * 0.95
    tax_info = "（免交易税）" if tax_free else "（收取5%交易税）"
    
    # 更新卖家金币
    seller_coins = get_point(group_id, seller_id)
    update_point(group_id, seller_id, seller_coins + seller_income)
    
    # 根据物品类型更新用户物品
    item_description = ""
    if item_type == 0:  # 资源类型
        user_resource = get_user_resource(group_id, user_id, resource_type)
        update_user_resource(group_id, user_id, resource_type, user_resource + quantity)
        resource_names = {RESOURCE_FOOD: "食物", RESOURCE_WOOD: "木材", RESOURCE_ORE: "矿石"}
        item_description = f"资源类型：{resource_names[resource_type]}"
        
        # 更新资源价格（购买导致价格上涨）
        new_price = update_resource_price(group_id, resource_type, quantity)
    
    elif item_type == 1:  # 工具类型
        # 获取工具耐久度
        if tool_type == TOOL_ALLOY_PERM:
            durability = -1  # 无限耐久
        else:
            durability = TOOL_DURABILITY[tool_type]  # 获取工具的最大耐久度
        
        # 更新用户工具
        update_tool_durability(group_id, user_id, tool_type, tool_category, durability)
        
        tool_type_names = {TOOL_IRON: "铁质", TOOL_FINE_GOLD: "精金", TOOL_ALLOY: "强化合金", TOOL_ALLOY_PERM: "强化合金【不毁】"}
        tool_category_names = {TOOL_TYPE_PICKAXE: "镐", TOOL_TYPE_HOE: "锄", TOOL_TYPE_AXE: "斧"}
        item_description = f"工具类型：{tool_type_names[tool_type]}{tool_category_names[tool_category]}"
    
    elif item_type == 2:  # 特殊材料类型
        user_special_resource = get_special_resource(group_id, user_id, special_resource_type)
        update_special_resource(group_id, user_id, special_resource_type, user_special_resource + quantity)
        
        # 检查卖家是否是商业联盟成员或富豪榜前三
        from .alliance import check_business_alliance_bonus
        from .casino import get_casino_leaderboard
        
        # 检查是否是商业联盟成员
        is_business_member = check_business_alliance_bonus(group_id, seller_id)
        
        # 检查是否在富豪榜前三
        is_top_three = False
        leaderboard = get_casino_leaderboard(group_id, 3)
        if not isinstance(leaderboard, str):
            return "获取富豪榜失败"
        
        # 解析富豪榜信息，检查用户是否在前三名
        for line in leaderboard.split('\n'):
            if line.startswith("1.") or line.startswith("2.") or line.startswith("3."):
                if f"用户{seller_id}:" in line:
                    is_top_three = True
                    break
        
        special_resource_names = {SPECIAL_BLUE_GEM: "海蓝宝石", SPECIAL_SUPER_PLANT: "超级植株", SPECIAL_DEMON_BRANCH: "恶魔树枝干"}
        item_description = f"特殊材料类型：{special_resource_names[special_resource_type]}"
    
    # 更新挂单数量
    new_quantity = available_quantity - quantity
    if new_quantity > 0:
        sql = f"UPDATE market_listings SET quantity={new_quantity} WHERE belonging_group={group_id} AND listing_id={listing_id}"
    else:
        sql = f"DELETE FROM market_listings WHERE belonging_group={group_id} AND listing_id={listing_id}"
    
    db_tool.execute_update(sql)
    
    return f"成功从市场购买！\n{item_description}\n单价：{price_per_unit}金币\n数量：{quantity}\n总花费：{total_price}金币\n当前金币：{user_coins - total_price}"

def cancel_market_listing(group_id: int, user_id: int, listing_id: int) -> str:
    """取消市场挂单"""
    # 获取挂单信息
    init_market_db()
    sql = f"SELECT seller_id, item_type, resource_type, tool_type, tool_category, special_resource_type, quantity FROM market_listings WHERE belonging_group={group_id} AND listing_id={listing_id}"
    result = db_tool.execute_query(sql)
    
    if not result:
        return f"挂单不存在！ID：{listing_id}"
    
    seller_id, item_type, resource_type, tool_type, tool_category, special_resource_type, quantity = result[0]
    
    # 检查是否是自己的挂单
    if seller_id != user_id:
        return "只能取消自己的挂单！"
    
    # 返还物品
    item_description = ""
    if item_type == 0:  # 资源类型
        user_resource = get_user_resource(group_id, user_id, resource_type)
        update_user_resource(group_id, user_id, resource_type, user_resource + quantity)
        resource_names = {RESOURCE_FOOD: "食物", RESOURCE_WOOD: "木材", RESOURCE_ORE: "矿石"}
        item_description = f"资源类型：{resource_names[resource_type]}"
    
    elif item_type == 1:  # 工具类型
        # 获取工具耐久度
        if tool_type == TOOL_ALLOY_PERM:
            durability = -1  # 无限耐久
        else:
            durability = TOOL_DURABILITY[tool_type]  # 获取工具的最大耐久度
        
        # 更新用户工具
        update_tool_durability(group_id, user_id, tool_type, tool_category, durability)
        
        tool_type_names = {TOOL_IRON: "铁质", TOOL_FINE_GOLD: "精金", TOOL_ALLOY: "强化合金", TOOL_ALLOY_PERM: "强化合金【不毁】"}
        tool_category_names = {TOOL_TYPE_PICKAXE: "镐", TOOL_TYPE_HOE: "锄", TOOL_TYPE_AXE: "斧"}
        item_description = f"工具类型：{tool_type_names[tool_type]}{tool_category_names[tool_category]}"
    
    elif item_type == 2:  # 特殊材料类型
        user_special_resource = get_special_resource(group_id, user_id, special_resource_type)
        update_special_resource(group_id, user_id, special_resource_type, user_special_resource + quantity)
        
        special_resource_names = {SPECIAL_BLUE_GEM: "海蓝宝石", SPECIAL_SUPER_PLANT: "超级植株", SPECIAL_DEMON_BRANCH: "恶魔树枝干"}
        item_description = f"特殊材料类型：{special_resource_names[special_resource_type]}"
    
    # 删除挂单
    sql = f"DELETE FROM market_listings WHERE belonging_group={group_id} AND listing_id={listing_id}"
    db_tool.execute_update(sql)
    
    return f"成功取消市场挂单！\n挂单ID：{listing_id}\n{item_description}\n返还数量：{quantity}"

def get_market_listings(group_id: int) -> str:
    """获取市场挂单列表"""
    init_market_db()
    sql = f"SELECT listing_id, seller_id, item_type, resource_type, tool_type, tool_category, special_resource_type, price_per_unit, quantity FROM market_listings WHERE belonging_group={group_id} ORDER BY listing_time DESC"
    results = db_tool.execute_query(sql)
    
    if not results:
        return "当前市场没有挂单！"
    
    resource_names = {RESOURCE_FOOD: "食物", RESOURCE_WOOD: "木材", RESOURCE_ORE: "矿石"}
    tool_type_names = {TOOL_IRON: "铁质", TOOL_FINE_GOLD: "精金", TOOL_ALLOY: "强化合金", TOOL_ALLOY_PERM: "强化合金【不毁】"}
    tool_category_names = {TOOL_TYPE_PICKAXE: "镐", TOOL_TYPE_HOE: "锄", TOOL_TYPE_AXE: "斧"}
    special_resource_names = {SPECIAL_BLUE_GEM: "海蓝宝石", SPECIAL_SUPER_PLANT: "超级植株", SPECIAL_DEMON_BRANCH: "恶魔树枝干"}
    
    message = "当前市场挂单列表：\n"
    for listing_id, seller_id, item_type, resource_type, tool_type, tool_category, special_resource_type, price_per_unit, quantity in results:
        if item_type == 0:  # 资源类型
            message += f"ID: {listing_id} | 卖家: {seller_id} | 资源: {resource_names[resource_type]} | 单价: {price_per_unit}金币 | 数量: {quantity}\n"
        elif item_type == 1:  # 工具类型
            message += f"ID: {listing_id} | 卖家: {seller_id} | 工具: {tool_type_names[tool_type]}{tool_category_names[tool_category]} | 价格: {price_per_unit}金币\n"
        elif item_type == 2:  # 特殊材料类型
            message += f"ID: {listing_id} | 卖家: {seller_id} | 特殊材料: {special_resource_names[special_resource_type]} | 单价: {price_per_unit}金币 | 数量: {quantity}\n"
    
    return message

# 获取物品信息
def get_item_info(group_id: int, user_id: int) -> str:
    """获取用户物品信息"""
    # 获取用户物品数量
    supreme_card = get_user_item(group_id, user_id, ITEM_SUPREME_CARD)
    luxury_house = get_user_item(group_id, user_id, ITEM_LUXURY_HOUSE)
    production_card = get_user_item(group_id, user_id, ITEM_PRODUCTION_CARD)
    stamina_card = get_user_item(group_id, user_id, ITEM_STAMINA_CARD)
    
    # 获取生产加倍卡剩余使用次数
    production_card_remaining = get_production_card_uses(group_id, user_id)
    
    # 构建消息
    message = "你的物品信息：\n"
    message += f"至尊签到卡：{supreme_card}张 (被动效果：签到奖励×100)\n"
    message += f"400平大别野：{luxury_house}套 (被动效果：无法被抢劫)\n"
    message += f"生产加倍卡：{production_card}张 (使用后10次生产产量翻倍)\n"
    message += f"体力恢复卡：{stamina_card}张 (使用后恢复100点体力)\n"
    
    if production_card_remaining > 0:
        message += f"\n当前生产加倍效果剩余次数：{production_card_remaining}次"
    
    return message

# 获取商店信息
def get_shop_info() -> str:
    """获取系统商店信息"""
    message = "系统商店商品列表：\n"
    message += f"1. 至尊签到卡：{ITEM_PRICES[ITEM_SUPREME_CARD]}金币/张 (每位玩家只能持有1张，被动效果为签到奖励乘100)\n"
    message += f"2. 400平大别野：{ITEM_PRICES[ITEM_LUXURY_HOUSE]}金币/套 (每位玩家只能持有1套，被动效果为无法被抢劫)\n"
    message += f"3. 生产加倍卡：{ITEM_PRICES[ITEM_PRODUCTION_CARD]}金币/张 (效果为接下来10次生产时，产量翻倍，需主动使用)\n"
    message += f"4. 体力恢复卡：{ITEM_PRICES[ITEM_STAMINA_CARD]}金币/张 (效果为回复100体力，不能超过最大体力值，需主动使用，每天限购1张)\n"
    
    message += "\n彩票面额：\n"
    message += "500面额：70%概率中100，20%概率中500，7%概率中750，2%概率中1000，1%概率中5000\n"
    message += "1000面额：70%概率中200，20%概率中1000，7%概率中1500，2%概率中2000，1%概率中10000\n"
    message += "5000面额：70%概率中1000，20%概率中5000，7%概率中7500，2%概率中10000，1%概率中50000\n"
    message += "10000面额：70%概率中2000，20%概率中10000，7%概率中15000，2%概率中20000，1%概率中100000\n"
    message += "20000面额：70%概率中4000，20%概率中20000，7%概率中30000，2%概率中40000，1%概率中200000\n"
    
    return message

# 获取资源价格信息
def get_resource_price_info(group_id: int) -> str:
    """获取资源价格信息"""
    food_price = get_resource_price(group_id, RESOURCE_FOOD)
    wood_price = get_resource_price(group_id, RESOURCE_WOOD)
    ore_price = get_resource_price(group_id, RESOURCE_ORE)
    
    message = "当前资源市场价格：\n"
    message += f"食物：{food_price}金币/单位\n"
    message += f"木材：{wood_price}金币/单位\n"
    message += f"矿石：{ore_price}金币/单位\n"
    message += "\n注意：\n"
    message += "1. 系统收购价格为市场价格的80%（收取20%交易税）\n"
    message += "2. 玩家市场交易收取5%交易税\n"
    message += "3. 每100单位交易量导致1%基准价格变化\n"
    message += "4. 每日价格最大波动为基准价格的50%\n"
    
    return message