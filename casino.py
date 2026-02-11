import sqlite3
import datetime
import random
import time
from typing import Dict, List, Tuple, Optional, Union
from .card import Card
from .game import Deck
from .sign import get_point, update_point
from .bank import get_bank_balance, update_bank_balance, update_user_status, STATUS_HOSPITAL

# 筹码价格波动字典 {group_id: float} - 存储筹码与金币的兑换比率
chip_rate: Dict[int, float] = {}

# 赌场奖池字典 {group_id: float} - 存储每个群的赌场奖池金额
casino_pool: Dict[int, float] = {}

# 赌场惩罚CD字典 {(group_id, user_id): datetime} - 存储玩家的赌场惩罚结束时间
casino_punishment: Dict[Tuple[int, int], datetime.datetime] = {}

# 21点游戏字典 {(group_id, user_id): game_info} - 存储进行中的21点游戏，直接与用户ID绑定
blackjack_games: Dict[Tuple[int, int], Dict] = {}

# 存储BlackJackGame对象的字典 {(group_id, user_id): BlackJackGame} - 存储进行中的新版21点游戏，直接与用户ID绑定
blackjack_game_objects: Dict[Tuple[int, int], 'BlackJackGame'] = {}

def init_casino_db():
    """初始化赌场数据库"""
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 创建筹码表
    sql = """
    CREATE TABLE IF NOT EXISTS casino_chips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        chips REAL NOT NULL DEFAULT 0,
        UNIQUE(uid, belonging_group)
    )
    """
    cursor.execute(sql)
    
    # 创建赌场奖池表
    sql = """
    CREATE TABLE IF NOT EXISTS casino_pool (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        belonging_group INTEGER NOT NULL,
        pool_amount REAL NOT NULL DEFAULT 1000000,
        last_refresh DATE,
        UNIQUE(belonging_group)
    )
    """
    cursor.execute(sql)
    
    # 创建筹码价格表
    sql = """
    CREATE TABLE IF NOT EXISTS chip_rate (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        belonging_group INTEGER NOT NULL,
        rate REAL NOT NULL DEFAULT 1.0,
        last_update DATE,
        UNIQUE(belonging_group)
    )
    """
    cursor.execute(sql)
    
    # 创建赌场记录表
    sql = """
    CREATE TABLE IF NOT EXISTS casino_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        game_type TEXT NOT NULL,
        bet_amount REAL NOT NULL,
        win_amount REAL NOT NULL,
        game_result TEXT NOT NULL,
        game_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    cursor.execute(sql)
    
    # 创建赌场惩罚表
    sql = """
    CREATE TABLE IF NOT EXISTS casino_punishment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        end_time TIMESTAMP NOT NULL,
        UNIQUE(uid, belonging_group)
    )
    """
    cursor.execute(sql)
    
    conn.commit()
    cursor.close()
    conn.close()

def get_chip_rate(group_id: int) -> float:
    """获取当前筹码兑换比率"""
    init_casino_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 检查是否已有记录
    sql = f"SELECT rate, last_update FROM chip_rate WHERE belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    today = datetime.date.today().isoformat()
    
    if result is None:
        # 创建新记录，默认比率为1.0
        rate = 1.0
        sql = f"INSERT INTO chip_rate (belonging_group, rate, last_update) VALUES ({group_id}, {rate}, '{today}')"
        cursor.execute(sql)
        conn.commit()
    else:
        rate, last_update = result
        rate = float(rate)
        
        # 检查是否需要更新价格（每天更新一次）
        if last_update != today:
            # 随机波动15%
            fluctuation = random.uniform(-0.15, 0.15)
            # 在计算过程中就保留两位小数，确保精度一致
            rate = round(max(0.5, min(1.5, round(rate * (1 + fluctuation), 2))), 2)  # 限制在0.5-1.5之间，保留两位小数
            
            # 更新数据库
            sql = f"UPDATE chip_rate SET rate={rate}, last_update='{today}' WHERE belonging_group={group_id}"
            cursor.execute(sql)
            conn.commit()
    
    cursor.close()
    conn.close()
    
    # 更新内存中的价格
    chip_rate[group_id] = rate
    
    return rate

def get_casino_pool(group_id: int) -> float:
    """获取赌场奖池金额"""
    init_casino_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 检查是否已有记录
    sql = f"SELECT pool_amount, last_refresh FROM casino_pool WHERE belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    today = datetime.date.today().isoformat()
    
    if result is None:
        # 创建新记录，默认奖池为100万
        pool_amount = 1000000.0
        sql = f"INSERT INTO casino_pool (belonging_group, pool_amount, last_refresh) VALUES ({group_id}, {pool_amount}, '{today}')"
        cursor.execute(sql)
        conn.commit()
    else:
        pool_amount, last_refresh = result
        pool_amount = float(pool_amount)
        
        # 检查是否需要刷新奖池（每天第一次查询且金额小于100万时刷新）
        if last_refresh != today and pool_amount < 1000000:
            pool_amount = 1000000.0
            sql = f"UPDATE casino_pool SET pool_amount={pool_amount}, last_refresh='{today}' WHERE belonging_group={group_id}"
            cursor.execute(sql)
            conn.commit()
    
    cursor.close()
    conn.close()
    
    # 更新内存中的奖池
    casino_pool[group_id] = pool_amount
    
    return pool_amount

def update_casino_pool(group_id: int, amount: float) -> None:
    """更新赌场奖池金额"""
    init_casino_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 获取当前奖池金额
    current_pool = get_casino_pool(group_id)
    new_pool = max(0, current_pool + amount)  # 确保奖池不会为负
    
    # 更新数据库
    sql = f"UPDATE casino_pool SET pool_amount={new_pool} WHERE belonging_group={group_id}"
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()
    
    # 更新内存中的奖池
    casino_pool[group_id] = new_pool

def get_user_chips(group_id: int, user_id: int) -> float:
    """获取用户筹码数量"""
    init_casino_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 检查用户是否有筹码记录
    sql = f"SELECT chips FROM casino_chips WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 创建新记录
        sql = f"INSERT INTO casino_chips (uid, belonging_group, chips) VALUES ({user_id}, {group_id}, 0)"
        cursor.execute(sql)
        conn.commit()
        chips = 0.0
    else:
        chips = float(result[0])
    
    cursor.close()
    conn.close()
    return chips

def update_user_chips(group_id: int, user_id: int, chips: float) -> None:
    """更新用户筹码数量"""
    init_casino_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 检查用户是否有筹码记录
    sql = f"SELECT id FROM casino_chips WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 创建新记录
        sql = f"INSERT INTO casino_chips (uid, belonging_group, chips) VALUES ({user_id}, {group_id}, {chips})"
    else:
        # 更新记录
        sql = f"UPDATE casino_chips SET chips={chips} WHERE uid={user_id} AND belonging_group={group_id}"
    
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()

def check_casino_punishment(group_id: int, user_id: int) -> Tuple[bool, str]:
    """检查用户是否处于赌场惩罚状态"""
    # 先检查内存中是否有记录
    if (group_id, user_id) in casino_punishment:
        end_time = casino_punishment[(group_id, user_id)]
        if datetime.datetime.now() < end_time:
            remaining = end_time - datetime.datetime.now()
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            return False, f"你因为赌场欠债被惩罚中，还有{hours}小时{minutes}分钟才能进行赌场相关操作"
        else:
            # 惩罚已结束，删除记录
            del casino_punishment[(group_id, user_id)]
            return True, ""
    
    # 检查数据库
    init_casino_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT end_time FROM casino_punishment WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 没有惩罚记录
        cursor.close()
        conn.close()
        return True, ""
    else:
        end_time = datetime.datetime.fromisoformat(result[0])
        if datetime.datetime.now() < end_time:
            # 仍在惩罚期内
            remaining = end_time - datetime.datetime.now()
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            
            # 更新内存记录
            casino_punishment[(group_id, user_id)] = end_time
            
            cursor.close()
            conn.close()
            return False, f"你因为赌场欠债被惩罚中，还有{hours}小时{minutes}分钟才能进行赌场相关操作"
        else:
            # 惩罚已结束，删除记录
            sql = f"DELETE FROM casino_punishment WHERE uid={user_id} AND belonging_group={group_id}"
            cursor.execute(sql)
            conn.commit()
            cursor.close()
            conn.close()
            return True, ""

def apply_casino_punishment(group_id: int, user_id: int) -> None:
    """对用户应用赌场惩罚"""
    # 设置惩罚结束时间（12小时后）
    end_time = datetime.datetime.now() + datetime.timedelta(hours=12)
    
    # 更新内存记录
    casino_punishment[(group_id, user_id)] = end_time
    
    # 更新数据库
    init_casino_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT id FROM casino_punishment WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 创建新记录
        sql = f"INSERT INTO casino_punishment (uid, belonging_group, end_time) VALUES ({user_id}, {group_id}, '{end_time.isoformat()}')"
    else:
        # 更新记录
        sql = f"UPDATE casino_punishment SET end_time='{end_time.isoformat()}' WHERE uid={user_id} AND belonging_group={group_id}"
    
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()
    
    # 同时将用户送进医院10分钟
    hospital_end_time = datetime.datetime.now() + datetime.timedelta(minutes=10)
    update_user_status(group_id, user_id, STATUS_HOSPITAL, hospital_end_time)

def add_casino_record(group_id: int, user_id: int, game_type: str, bet_amount: float, win_amount: float, game_result: str) -> None:
    """添加赌场游戏记录"""
    init_casino_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"INSERT INTO casino_records (uid, belonging_group, game_type, bet_amount, win_amount, game_result) VALUES ({user_id}, {group_id}, '{game_type}', {bet_amount}, {win_amount}, '{game_result}')"
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()

def get_today_casino_records(group_id: int, user_id: int) -> List[Tuple]:
    """获取用户今日赌场记录"""
    init_casino_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    today = datetime.date.today().isoformat()
    sql = f"SELECT game_type, bet_amount, win_amount, game_result, game_time FROM casino_records WHERE uid={user_id} AND belonging_group={group_id} AND date(game_time)='{today}' ORDER BY game_time DESC"
    cursor.execute(sql)
    results = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return results

def get_today_casino_profit(group_id: int, user_id: int) -> float:
    """获取用户今日赌场盈亏"""
    init_casino_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    today = datetime.date.today().isoformat()
    sql = f"SELECT SUM(win_amount - bet_amount) FROM casino_records WHERE uid={user_id} AND belonging_group={group_id} AND date(game_time)='{today}'"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if result[0] is None:
        return 0.0
    else:
        return float(result[0])

def get_today_casino_king(group_id: int) -> Tuple[int, float]:
    """获取今日赌王（赢得最多筹码的玩家）"""
    init_casino_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    today = datetime.date.today().isoformat()
    sql = f"SELECT uid, SUM(win_amount) as profit FROM casino_records WHERE belonging_group={group_id} AND date(game_time)='{today}' GROUP BY uid ORDER BY profit DESC LIMIT 1"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if result is None:
        return 0, 0.0
    else:
        return int(result[0]), float(result[1])

def get_casino_info(group_id: int) -> str:
    """获取赌场信息"""
    # 获取赌场奖池
    pool_amount = get_casino_pool(group_id)
    
    # 获取筹码兑换比率
    rate = get_chip_rate(group_id)
    
    # 获取今日赌王（赢得最多筹码的玩家）
    king_id, king_profit = get_today_casino_king(group_id)
    king_info = f"今日暂无赌王" if king_id == 0 else f"今日赌王ID：{king_id}，总赢得：{king_profit}筹码"
    
    # 构建回复消息
    message = f"===== 赌场信息 =====\n"
    message += f"赌场奖池：{pool_amount}筹码\n"
    message += f"当前筹码兑换比率：1:{rate:.2f}\n"
    message += f"{king_info}"
    
    return message

def get_user_casino_records(group_id: int, user_id: int) -> str:
    """获取用户赌场明细"""
    # 获取今日赌场记录
    records = get_today_casino_records(group_id, user_id)
    
    # 获取今日盈亏
    profit = get_today_casino_profit(group_id, user_id)
    
    # 构建回复消息
    message = f"===== 赌场明细 =====\n"
    message += f"今日总盈亏：{profit}筹码\n\n"
    
    if not records:
        message += "今日暂无赌场记录"
    else:
        message += "今日赌场记录：\n"
        for i, (game_type, bet_amount, win_amount, game_result, game_time) in enumerate(records, 1):
            profit = win_amount - bet_amount
            profit_str = f"+{profit}" if profit > 0 else str(profit)
            message += f"{i}. [{game_time}] {game_type} - 下注：{bet_amount}，结果：{game_result}，盈亏：{profit_str}\n"
    
    return message

def get_casino_leaderboard(group_id: int, limit: int = 10) -> str:
    """获取赌场富豪榜"""
    init_casino_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 联合查询金币和银行存款
    sql = f"""
    SELECT s.uid, s.points + COALESCE(b.balance, 0) as total_wealth 
    FROM sign_in s 
    LEFT JOIN bank_accounts b ON s.uid = b.uid AND s.belonging_group = b.belonging_group 
    WHERE s.belonging_group = {group_id} 
    ORDER BY total_wealth DESC 
    LIMIT {limit}
    """
    cursor.execute(sql)
    results = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    if not results:
        return "暂无财富排行数据"
    
    message = "===== 财富排行榜 =====\n"
    message += "排名  用户ID  总财富  特权\n"
    
    for rank, (uid, total_wealth) in enumerate(results, 1):
        # 获取特权信息
        privileges = ""
        if rank <= 3:
            privileges = "免税"
        
        message += f"{rank}. 用户{uid}: {total_wealth:.2f} 金币 {privileges}\n"
    
    return message

def buy_chips(group_id: int, user_id: int, amount: float) -> str:
    """购买筹码"""
    # 导入筹码购买限制相关函数
    from .chip_purchase_limit import add_chip_purchase_record, calculate_price_increase
    
    # 检查是否处于惩罚状态
    allowed, message = check_casino_punishment(group_id, user_id)
    if not allowed:
        return message
    
    # 检查金额是否合法（必须是100的倍数）
    if amount < 100 or amount % 100 != 0:
        return "筹码最小额度为100，只能购买以100为倍数的筹码数量"
    
    # 获取当前筹码兑换比率
    rate = get_chip_rate(group_id)
    
    # 获取用户当前持有的筹码数量
    user_chips = get_user_chips(group_id, user_id)
    
    # 计算价格增加比例
    price_increase = calculate_price_increase(group_id, user_id, user_chips)
    
    # 应用价格增加
    adjusted_rate = rate * price_increase
    
    # 计算需要的金币数量 - 购买时，1筹码需要adjusted_rate金币
    coins_needed = amount * adjusted_rate
    
    # 检查用户金币是否足够
    user_coins = get_point(group_id, user_id)
    if user_coins < coins_needed:
        price_increase_percentage = (price_increase - 1.0) * 100
        if price_increase > 1.0:
            return f"你的金币不足，当前筹码兑换比率为1:{adjusted_rate:.2f}（已增加{price_increase_percentage:.1f}%），需要{coins_needed:.2f}金币才能购买{amount}筹码"
        else:
            return f"你的金币不足，当前筹码兑换比率为1:{adjusted_rate:.2f}，需要{coins_needed:.2f}金币才能购买{amount}筹码"
    
    # 扣除金币并增加筹码
    update_point(group_id, user_id, user_coins - coins_needed)
    
    update_user_chips(group_id, user_id, user_chips + amount)
    
    # 添加筹码购买记录
    add_chip_purchase_record(group_id, user_id, amount)
    
    # 构建回复消息
    price_increase_percentage = (price_increase - 1.0) * 100
    if price_increase > 1.0:
        return f"购买成功！花费{coins_needed:.2f}金币购买了{amount:.2f}筹码，当前筹码兑换比率为1:{adjusted_rate:.2f}（已增加{price_increase_percentage:.1f}%）\n当前持有筹码：{(user_chips + amount):.2f}"
    else:
        return f"购买成功！花费{coins_needed:.2f}金币购买了{amount:.2f}筹码，当前筹码兑换比率为1:{adjusted_rate:.2f}\n当前持有筹码：{(user_chips + amount):.2f}"

def sell_chips(group_id: int, user_id: int, amount: float) -> str:
    """卖出筹码"""
    # 导入筹码消耗记录相关函数
    from .chip_purchase_limit import add_chip_consumption_record
    
    # 检查是否处于惩罚状态
    allowed, message = check_casino_punishment(group_id, user_id)
    if not allowed:
        return message
    
    # 检查用户筹码是否足够
    user_chips = get_user_chips(group_id, user_id)
    if user_chips < amount:
        return f"你的筹码不足，当前持有筹码：{user_chips}"
    
    # 获取当前筹码兑换比率
    rate = get_chip_rate(group_id)
    
    # 计算可获得的金币数量 - 出售时，1筹码可以获得rate金币
    coins_gained = amount * rate
    
    # 扣除筹码并增加金币
    update_user_chips(group_id, user_id, user_chips - amount)
    
    user_coins = get_point(group_id, user_id)
    update_point(group_id, user_id, user_coins + coins_gained)
    
    # 添加筹码消耗记录
    add_chip_consumption_record(group_id, user_id, amount)
    
    return f"卖出成功！卖出{amount:.2f}筹码获得了{coins_gained:.2f}金币，当前筹码兑换比率为1:{rate:.2f}\n当前持有筹码：{(user_chips - amount):.2f}"

def start_blackjack_game(group_id: int, user_id: int, bet_amount: float) -> str:
    """开始21点游戏"""
    # 导入筹码消耗记录相关函数
    from .chip_purchase_limit import add_chip_consumption_record
    
    # 检查是否处于惩罚状态
    allowed, message = check_casino_punishment(group_id, user_id)
    if not allowed:
        return message
    
    # 检查用户是否已有进行中的游戏
    if (group_id, user_id) in blackjack_games:
        return "你已经有一场进行中的游戏，请先完成当前游戏"
    
    # 检查用户筹码是否足够
    user_chips = get_user_chips(group_id, user_id)
    if user_chips < bet_amount:
        return f"你的筹码不足，当前持有筹码：{user_chips}"
    
    # 检查赌场奖池是否足够
    casino_amount = get_casino_pool(group_id)
    if casino_amount < bet_amount * 2:  # 确保赌场至少有足够支付最高赔率的筹码
        return f"赌场资金不足，当前赌场资金：{casino_amount}"
    
    # 初始化牌组
    cards = []
    for i in range(52):
        cards.append(Card(i))
    random.shuffle(cards)
    
    # 发牌
    player_cards = [cards.pop(), cards.pop()]
    dealer_cards = [cards.pop(), cards.pop()]
    
    # 计算点数
    player_points = calculate_points(player_cards)
    dealer_points = calculate_points(dealer_cards)
    
    # 存储游戏信息
    blackjack_games[(group_id, user_id)] = {
        "bet_amount": bet_amount,
        "player_cards": player_cards,
        "dealer_cards": dealer_cards,
        "remaining_cards": cards,
        "status": "playing"  # playing, player_stand, ended
    }
    
    # 添加筹码消耗记录（下注时消耗筹码）
    add_chip_consumption_record(group_id, user_id, bet_amount)
    
    # 检查是否有blackjack（前两张牌就是21点）
    if player_points == 21:
        return end_blackjack_game(group_id, user_id, "blackjack")
    
    # 构建回复消息
    message = f"游戏开始！\n"
    message += f"你的下注：{bet_amount}筹码\n"
    message += f"你的手牌：{' '.join(str(card) for card in player_cards)} (点数：{player_points})\n"
    message += f"庄家手牌：{dealer_cards[0]} ? (明牌点数：{dealer_cards[0].value if dealer_cards[0].value < 10 else 10})\n"
    message += "\n你可以选择：\n"
    message += "- 发送'赌场叫牌'继续要牌\n"
    message += "- 发送'赌场停牌'停止要牌，庄家开始行动"
    
    return message

def calculate_points(cards: List[Card]) -> int:
    """计算手牌点数"""
    points = 0
    ace_count = 0
    
    for card in cards:
        if card.value == 1:  # A
            ace_count += 1
        elif card.value >= 10:  # 10, J, Q, K
            points += 10
        else:  # 2-9
            points += card.value
    
    # 处理A的点数
    for _ in range(ace_count):
        if points + 11 <= 21:
            points += 11
        else:
            points += 1
    
    return points

def player_hit(group_id: int, user_id: int) -> str:
    """玩家叫牌"""
    # 检查游戏是否存在
    if (group_id, user_id) not in blackjack_games:
        return "你没有进行中的游戏"
    
    game = blackjack_games[(group_id, user_id)]
    
    # 检查游戏状态
    if game["status"] != "playing":
        return "当前游戏状态不允许叫牌"
    
    # 抽一张牌
    new_card = game["remaining_cards"].pop()
    game["player_cards"].append(new_card)
    
    # 计算新的点数
    player_points = calculate_points(game["player_cards"])
    
    # 构建回复消息
    message = f"你抽到了：{new_card}\n"
    message += f"你的手牌：{' '.join(str(card) for card in game['player_cards'])} (点数：{player_points})\n"
    message += f"庄家手牌：{game['dealer_cards'][0]} ? (明牌点数：{game['dealer_cards'][0].value if game['dealer_cards'][0].value < 10 else 10})\n"
    
    # 检查是否爆牌
    if player_points > 21:
        return message + "\n" + end_blackjack_game(group_id, user_id, "player_bust")
    
    # 检查是否达到五小龙条件（5张牌且点数不超过21）
    if len(game["player_cards"]) == 5 and player_points <= 21:
        return message + "\n" + end_blackjack_game(group_id, user_id, "five_dragon")
    
    # 游戏继续
    message += "\n你可以选择：\n"
    message += "- 发送'赌场叫牌'继续要牌\n"
    message += "- 发送'赌场停牌'停止要牌，庄家开始行动"
    
    return message

def player_stand(group_id: int, user_id: int) -> str:
    """玩家停牌"""
    # 检查游戏是否存在
    if (group_id, user_id) not in blackjack_games:
        return "你没有进行中的游戏"
    
    game = blackjack_games[(group_id, user_id)]
    
    # 检查游戏状态
    if game["status"] != "playing":
        return "当前游戏状态不允许停牌"
    
    # 更新游戏状态
    game["status"] = "player_stand"
    
    # 庄家行动（补牌直到17点或以上）
    dealer_points = calculate_points(game["dealer_cards"])
    message = f"你选择了停牌，你的最终点数为{calculate_points(game['player_cards'])}\n庄家开始行动...\n"
    message += f"庄家的手牌：{' '.join(str(card) for card in game['dealer_cards'])} (点数：{dealer_points})\n"
    
    # 庄家补牌直到17点或以上
    while dealer_points < 17:
        new_card = game["remaining_cards"].pop()
        game["dealer_cards"].append(new_card)
        dealer_points = calculate_points(game["dealer_cards"])
        message += f"庄家抽到了：{new_card}\n"
        message += f"庄家的手牌：{' '.join(str(card) for card in game['dealer_cards'])} (点数：{dealer_points})\n"
    
    # 判断胜负
    player_points = calculate_points(game["player_cards"])
    
    # 庄家爆牌，玩家获胜
    if dealer_points > 21:
        message += "\n庄家爆牌！"
        return message + "\n" + end_blackjack_game(group_id, user_id, "dealer_bust")
    
    # 比较点数
    if player_points > dealer_points:
        message += "\n你的点数大于庄家！"
        return message + "\n" + end_blackjack_game(group_id, user_id, "player_win")
    elif player_points < dealer_points:
        message += "\n你的点数小于庄家！"
        return message + "\n" + end_blackjack_game(group_id, user_id, "dealer_win")
    else:
        message += "\n点数相同！"
        return message + "\n" + end_blackjack_game(group_id, user_id, "push")

def end_blackjack_game(group_id: int, user_id: int, result: str) -> str:
    """结束21点游戏并结算"""
    # 检查游戏是否存在
    if (group_id, user_id) not in blackjack_games:
        return "找不到指定的游戏"
    
    game = blackjack_games[(group_id, user_id)]
    bet_amount = game["bet_amount"]
    player_cards = game["player_cards"]
    dealer_cards = game["dealer_cards"]
    
    # 计算点数
    player_points = calculate_points(player_cards)
    dealer_points = calculate_points(dealer_cards)
    
    # 获取用户当前筹码
    user_chips = get_user_chips(group_id, user_id)
    
    # 获取赌场奖池
    casino_amount = get_casino_pool(group_id)
    
    # 根据不同结果计算赔率和输赢
    win_amount = 0.0
    message = ""
    
    if result == "blackjack":  # 玩家获得21点（前两张牌），赔率1.5
        win_amount = bet_amount * 1.5
        message = f"恭喜！你获得了Blackjack！赢得{win_amount}筹码！\n"
        
        # 检查是否有足够筹码支付
        if win_amount > user_chips + bet_amount:
            # 尝试从银行扣除
            bank_balance = get_bank_balance(group_id, user_id)
            coins_needed = (win_amount - user_chips - bet_amount) * get_chip_rate(group_id)
            
            if bank_balance >= coins_needed:
                # 银行有足够金币
                update_bank_balance(group_id, user_id, bank_balance - coins_needed)
                message += f"你的筹码不足以支付赢得的筹码，已从银行扣除{coins_needed}金币\n"
            else:
                # 银行也没有足够金币，触发倾家荡产
                message += "你的筹码和银行存款不足以支付赢得的筹码，触发【倾家荡产】！\n"
                message += "你被暴打一顿并送进了医院，12小时内不能进行赌场相关操作\n"
                apply_casino_punishment(group_id, user_id)
                
                # 记录游戏
                add_casino_record(group_id, user_id, "21点", bet_amount, 0, "倾家荡产")
                
                # 更新用户筹码（清零）
                update_user_chips(group_id, user_id, 0)
                
                # 删除游戏记录
                del blackjack_games[(group_id, user_id)]
                
                return message
        
        # 更新用户筹码
        update_user_chips(group_id, user_id, user_chips + win_amount)
        
        # 更新赌场奖池
        update_casino_pool(group_id, -win_amount)
        
        # 记录游戏
        add_casino_record(group_id, user_id, "21点", bet_amount, win_amount, "Blackjack")
    
    elif result == "five_dragon":  # 五小龙，赔率2
        win_amount = bet_amount * 2
        message = f"恭喜！你获得了五小龙！赢得{win_amount}筹码！\n"
        
        # 检查是否有足够筹码支付
        if win_amount > user_chips + bet_amount:
            # 尝试从银行扣除
            bank_balance = get_bank_balance(group_id, user_id)
            coins_needed = (win_amount - user_chips - bet_amount) * get_chip_rate(group_id)
            
            if bank_balance >= coins_needed:
                # 银行有足够金币
                update_bank_balance(group_id, user_id, bank_balance - coins_needed)
                message += f"你的筹码不足以支付赢得的筹码，已从银行扣除{coins_needed}金币\n"
            else:
                # 银行也没有足够金币，触发倾家荡产
                message += "你的筹码和银行存款不足以支付赢得的筹码，触发【倾家荡产】！\n"
                message += "你被暴打一顿并送进了医院，12小时内不能进行赌场相关操作\n"
                apply_casino_punishment(group_id, user_id)
                
                # 记录游戏
                add_casino_record(group_id, user_id, "21点", bet_amount, 0, "倾家荡产")
                
                # 更新用户筹码（清零）
                update_user_chips(group_id, user_id, 0)
                
                # 删除游戏记录
                del blackjack_games[(group_id, user_id)]
                
                return message
        
        # 更新用户筹码
        update_user_chips(group_id, user_id, user_chips + win_amount)
        
        # 更新赌场奖池
        update_casino_pool(group_id, -win_amount)
        
        # 记录游戏
        add_casino_record(group_id, user_id, "21点", bet_amount, win_amount, "五小龙")
    
    elif result == "player_win" or result == "dealer_bust":  # 普通获胜或庄家爆牌，赔率1
        win_amount = bet_amount
        message = f"恭喜！你赢了！赢得{win_amount}筹码！\n"
        
        # 更新用户筹码
        update_user_chips(group_id, user_id, user_chips + win_amount)
        
        # 更新赌场奖池
        update_casino_pool(group_id, -win_amount)
        
        # 记录游戏
        add_casino_record(group_id, user_id, "21点", bet_amount, win_amount, "获胜")
    
    elif result == "player_bust" or result == "dealer_win":  # 玩家爆牌或庄家获胜，玩家输
        win_amount = -bet_amount
        message = f"很遗憾，你输了！损失{bet_amount}筹码\n"
        
        # 更新用户筹码
        update_user_chips(group_id, user_id, user_chips - bet_amount)
        
        # 更新赌场奖池
        update_casino_pool(group_id, bet_amount)
        
        # 记录游戏
        add_casino_record(group_id, user_id, "21点", bet_amount, 0, "失败")
    
    elif result == "push":  # 平局，返还筹码
        message = "平局！筹码已返还\n"
        
        # 记录游戏
        add_casino_record(group_id, user_id, "21点", bet_amount, bet_amount, "平局")
    
    # 删除游戏记录
    del blackjack_games[(group_id, user_id)]
    
    # 显示当前筹码
    current_chips = get_user_chips(group_id, user_id)
    message += f"当前持有筹码：{current_chips}"
    
    return message


# 以下是新版21点游戏的相关函数
from .game import BlackJackGame, GameStatus

def create_blackjack_game(group_id: int, creator_id: int, bet_amount: float, creator_name: str) -> Tuple[int, str]:
    """创建新版21点游戏
    
    Args:
        group_id: 群组ID
        creator_id: 创建者ID
        bet_amount: 下注金额
        creator_name: 创建者名称
        
    Returns:
        Tuple[int, str]: 游戏ID和创建结果消息
    """
    # 导入筹码消耗记录相关函数
    from .chip_purchase_limit import add_chip_consumption_record
    
    # 检查是否处于惩罚状态
    allowed, message = check_casino_punishment(group_id, creator_id)
    if not allowed:
        return -1, message
    
    # 检查用户筹码是否足够
    user_chips = get_user_chips(group_id, creator_id)
    if user_chips < bet_amount:
        return -1, f"你的筹码不足，当前持有筹码：{user_chips}"
    
    # 检查赌场奖池是否足够
    casino_amount = get_casino_pool(group_id)
    if casino_amount < bet_amount * 2:  # 确保赌场至少有足够支付最高赔率的筹码
        return -1, f"赌场资金不足，当前赌场资金：{casino_amount}"
    
    # 创建新游戏
    game_id = get_next_game_id(group_id)
    
    # 创建BlackJackGame对象
    game = BlackJackGame(game_id, group_id, creator_id, bet_amount, creator_name)
    
    # 存储游戏对象
    blackjack_game_objects[(group_id, game_id)] = game
    
    # 添加筹码消耗记录（下注时消耗筹码）
    add_chip_consumption_record(group_id, creator_id, bet_amount)
    
    # 构建回复消息
    message = f"21点游戏创建成功！游戏ID：{game_id}\n"
    message += f"创建者：{creator_name}\n"
    message += f"下注金额：{bet_amount}筹码\n"
    message += f"等待对手加入...\n"
    message += f"其他玩家可发送'加入21点 {game_id}'参与游戏"
    
    return game_id, message

def get_blackjack_game(group_id: int, game_id: int) -> Optional[BlackJackGame]:
    """获取21点游戏对象
    
    Args:
        group_id: 群组ID
        game_id: 游戏ID
        
    Returns:
        Optional[BlackJackGame]: 游戏对象，如果不存在则返回None
    """
    return blackjack_game_objects.get((group_id, game_id))

def update_blackjack_game(game: BlackJackGame) -> None:
    """更新21点游戏对象
    
    Args:
        game: 游戏对象
    """
    blackjack_game_objects[(game.group_id, game.game_id)] = game

def delete_blackjack_game(group_id: int, game_id: int) -> None:
    """删除21点游戏对象
    
    Args:
        group_id: 群组ID
        game_id: 游戏ID
    """
    if (group_id, game_id) in blackjack_game_objects:
        del blackjack_game_objects[(group_id, game_id)]

def set_casino_punishment(group_id: int, user_id: int, end_time: datetime.datetime) -> None:
    """设置赌场惩罚
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        end_time: 惩罚结束时间
    """
    # 更新内存记录
    casino_punishment[(group_id, user_id)] = end_time
    
    # 更新数据库
    init_casino_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT id FROM casino_punishment WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 创建新记录
        sql = f"INSERT INTO casino_punishment (uid, belonging_group, end_time) VALUES ({user_id}, {group_id}, '{end_time.isoformat()}')"
    else:
        # 更新记录
        sql = f"UPDATE casino_punishment SET end_time='{end_time.isoformat()}' WHERE uid={user_id} AND belonging_group={group_id}"
    
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()


def play_blackjack(group_id: int, user_id: int, bet_amount: float) -> str:
    """21点游戏入口函数
    
    这个函数是对start_blackjack_game的包装，用于处理21点游戏的开始逻辑
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        bet_amount: 下注金额
        
    Returns:
        str: 游戏开始结果消息
    """
    # 直接调用start_blackjack_game函数
    return start_blackjack_game(group_id, user_id, bet_amount)

def casino_hit(group_id: int, user_id: int) -> str:
    """赌场21点叫牌入口函数
    
    这个函数是对player_hit的包装，用于处理赌场21点的叫牌逻辑
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        
    Returns:
        str: 叫牌结果消息
    """
    # 直接调用player_hit函数
    result = player_hit(group_id, user_id)
    
    # 检查游戏是否已经结束，如果结束则删除新版21点游戏对象
    if (group_id, user_id) in blackjack_game_objects:
        game = blackjack_game_objects[(group_id, user_id)]
        if game.status == GameStatus.FINISHED:
            delete_blackjack_game(group_id, user_id)
    
    return result

def casino_stand(group_id: int, user_id: int) -> str:
    """赌场21点停牌入口函数
    
    这个函数是对player_stand的包装，用于处理赌场21点的停牌逻辑
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        
    Returns:
        str: 停牌结果消息
    """
    # 直接调用player_stand函数
    result = player_stand(group_id, user_id)
    
    # 检查游戏是否已经结束，如果结束则删除新版21点游戏对象
    if (group_id, user_id) in blackjack_game_objects:
        game = blackjack_game_objects[(group_id, user_id)]
        if game.status == GameStatus.FINISHED:
            delete_blackjack_game(group_id, user_id)
    
    return result