import sqlite3
import datetime
import random
import time
import threading
from typing import Dict, List, Tuple, Optional, Union
from nonebot_plugin_apscheduler import scheduler
from .sign import get_point, update_point
from .game import db_pool
# 导入共享常量和函数
from .common import (
    PROF_FARMER, PROF_LUMBERJACK, PROF_MINER, RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE,
    TOOL_IRON, TOOL_FINE_GOLD, TOOL_ALLOY, TOOL_ALLOY_PERM,
    RESOURCE_PRICES, TOOL_PRICES, RESOURCE_STAMINA_COST,
    RESOURCE_CD, RESOURCE_OUTPUT, MAX_STAMINA,
    PROF_WORKER, PROF_NONE
)

# 资源生产CD字典 {(group_id, user_id, resource_type): end_time}
resource_cd: Dict[Tuple[int, int, int], datetime.datetime] = {}

# 缓存字典
user_stamina_cache: Dict[Tuple[int, int], Tuple[int, float]] = {}  # {(group_id, user_id): (stamina, timestamp)}
user_resource_cache: Dict[Tuple[int, int, int], Tuple[int, float]] = {}  # {(group_id, user_id, resource_type): (amount, timestamp)}
user_tool_cache: Dict[Tuple[int, int, int], Tuple[int, float]] = {}  # {(group_id, user_id, tool_type): (amount, timestamp)}

# 缓存锁
cache_lock = threading.Lock()

# 缓存过期时间（秒）
CACHE_EXPIRY = 300

def init_resource_db():
    """初始化资源数据库"""
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        # 创建用户体力表
        sql = """
        CREATE TABLE IF NOT EXISTS user_stamina (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL,
            belonging_group INTEGER NOT NULL,
            stamina INTEGER NOT NULL DEFAULT 100,
            last_refresh DATE,
            UNIQUE(uid, belonging_group)
        )
        """
        cursor.execute(sql)
        
        # 创建用户资源表
        sql = """
        CREATE TABLE IF NOT EXISTS user_resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL,
            belonging_group INTEGER NOT NULL,
            resource_type INTEGER NOT NULL,  -- 0: 食物, 1: 木材, 2: 矿石
            amount INTEGER NOT NULL DEFAULT 0,
            UNIQUE(uid, belonging_group, resource_type)
        )
        """
        cursor.execute(sql)
        
        # 创建用户工具表
        sql = """
        CREATE TABLE IF NOT EXISTS user_tools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL,
            belonging_group INTEGER NOT NULL,
            tool_type INTEGER NOT NULL,  -- 0: 铁质工具, 1: 精金工具, 2: 强化合金工具, 3: 强化合金工具【不毁】
            amount INTEGER NOT NULL DEFAULT 0,
            UNIQUE(uid, belonging_group, tool_type)
        )
        """
        cursor.execute(sql)
        
        # 创建资源生产CD表
        sql = """
        CREATE TABLE IF NOT EXISTS resource_production_cd (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL,
            belonging_group INTEGER NOT NULL,
            resource_type INTEGER NOT NULL,  -- 0: 食物, 1: 木材, 2: 矿石
            end_time TIMESTAMP NOT NULL,
            UNIQUE(uid, belonging_group, resource_type)
        )
        """
        cursor.execute(sql)
        
        conn.commit()
    finally:
        db_pool.return_connection(conn)

def get_user_stamina(group_id: int, user_id: int) -> int:
    """获取用户体力值"""
    init_resource_db()
    
    # 检查缓存
    cache_key = (group_id, user_id)
    today = datetime.date.today().isoformat()
    
    with cache_lock:
        if cache_key in user_stamina_cache:
            stamina, timestamp, last_refresh_cache = user_stamina_cache[cache_key]
            # 如果缓存未过期且最后刷新日期是今天，直接返回
            if time.time() - timestamp < CACHE_EXPIRY and last_refresh_cache == today:
                return stamina
    
    # 从数据库获取
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        sql = f"SELECT stamina, last_refresh FROM user_stamina WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            # 创建新记录，默认体力为100
            sql = f"INSERT INTO user_stamina (uid, belonging_group, stamina, last_refresh) VALUES ({user_id}, {group_id}, {MAX_STAMINA}, '{today}')"
            cursor.execute(sql)
            conn.commit()
            stamina = MAX_STAMINA
            last_refresh = today
        else:
            stamina, last_refresh = result
            
            # 检查是否需要刷新体力（每天刷新一次）
            if last_refresh != today:
                stamina = MAX_STAMINA
                sql = f"UPDATE user_stamina SET stamina={stamina}, last_refresh='{today}' WHERE uid={user_id} AND belonging_group={group_id}"
                cursor.execute(sql)
                conn.commit()
                last_refresh = today
        
        # 更新缓存
        with cache_lock:
            user_stamina_cache[cache_key] = (stamina, time.time(), last_refresh)
        
        return stamina
    finally:
        db_pool.return_connection(conn)

def update_user_stamina(group_id: int, user_id: int, stamina: int) -> None:
    """更新用户体力值"""
    init_resource_db()
    
    # 确保体力不超过上限
    stamina = min(MAX_STAMINA, max(0, stamina))
    
    today = datetime.date.today().isoformat()
    
    # 更新数据库
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        sql = f"SELECT id FROM user_stamina WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            # 创建新记录
            sql = f"INSERT INTO user_stamina (uid, belonging_group, stamina, last_refresh) VALUES ({user_id}, {group_id}, {stamina}, '{today}')"
        else:
            # 更新记录
            sql = f"UPDATE user_stamina SET stamina={stamina} WHERE uid={user_id} AND belonging_group={group_id}"
        
        cursor.execute(sql)
        conn.commit()
        
        # 更新缓存
        cache_key = (group_id, user_id)
        with cache_lock:
            user_stamina_cache[cache_key] = (stamina, time.time(), today)
    finally:
        db_pool.return_connection(conn)

def get_user_resource(group_id: int, user_id: int, resource_type: int) -> int:
    """获取用户资源数量"""
    init_resource_db()
    
    # 检查缓存
    cache_key = (group_id, user_id, resource_type)
    with cache_lock:
        if cache_key in user_resource_cache:
            amount, timestamp = user_resource_cache[cache_key]
            if time.time() - timestamp < CACHE_EXPIRY:
                return amount
    
    # 从数据库获取
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        sql = f"SELECT amount FROM user_resources WHERE uid={user_id} AND belonging_group={group_id} AND resource_type={resource_type}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            # 创建新记录
            sql = f"INSERT INTO user_resources (uid, belonging_group, resource_type, amount) VALUES ({user_id}, {group_id}, {resource_type}, 0)"
            cursor.execute(sql)
            conn.commit()
            amount = 0
        else:
            amount = result[0]
        
        # 更新缓存
        with cache_lock:
            user_resource_cache[cache_key] = (amount, time.time())
        
        return amount
    finally:
        db_pool.return_connection(conn)

def update_user_resource(group_id: int, user_id: int, resource_type: int, amount: int) -> None:
    """更新用户资源数量"""
    init_resource_db()
    
    # 确保资源数量不为负
    amount = max(0, amount)
    
    # 更新数据库
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        sql = f"SELECT id FROM user_resources WHERE uid={user_id} AND belonging_group={group_id} AND resource_type={resource_type}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            # 创建新记录
            sql = f"INSERT INTO user_resources (uid, belonging_group, resource_type, amount) VALUES ({user_id}, {group_id}, {resource_type}, {amount})"
        else:
            # 更新记录
            sql = f"UPDATE user_resources SET amount={amount} WHERE uid={user_id} AND belonging_group={group_id} AND resource_type={resource_type}"
        
        cursor.execute(sql)
        conn.commit()
        
        # 更新缓存
        cache_key = (group_id, user_id, resource_type)
        with cache_lock:
            user_resource_cache[cache_key] = (amount, time.time())
    finally:
        db_pool.return_connection(conn)

def get_user_tool(group_id: int, user_id: int, tool_type: int) -> int:
    """获取用户工具数量"""
    init_resource_db()
    
    # 检查缓存
    cache_key = (group_id, user_id, tool_type)
    with cache_lock:
        if cache_key in user_tool_cache:
            amount, timestamp = user_tool_cache[cache_key]
            if time.time() - timestamp < CACHE_EXPIRY:
                return amount
    
    # 从数据库获取
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        sql = f"SELECT amount FROM user_tools WHERE uid={user_id} AND belonging_group={group_id} AND tool_type={tool_type}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            # 创建新记录
            sql = f"INSERT INTO user_tools (uid, belonging_group, tool_type, amount) VALUES ({user_id}, {group_id}, {tool_type}, 0)"
            cursor.execute(sql)
            conn.commit()
            amount = 0
        else:
            amount = result[0]
        
        # 更新缓存
        with cache_lock:
            user_tool_cache[cache_key] = (amount, time.time())
        
        return amount
    finally:
        db_pool.return_connection(conn)

def update_user_tool(group_id: int, user_id: int, tool_type: int, amount: int) -> None:
    """更新用户工具数量"""
    init_resource_db()
    
    # 确保工具数量不为负
    amount = max(0, amount)
    
    # 更新数据库
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        sql = f"SELECT id FROM user_tools WHERE uid={user_id} AND belonging_group={group_id} AND tool_type={tool_type}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            # 创建新记录
            sql = f"INSERT INTO user_tools (uid, belonging_group, tool_type, amount) VALUES ({user_id}, {group_id}, {tool_type}, {amount})"
        else:
            # 更新记录
            sql = f"UPDATE user_tools SET amount={amount} WHERE uid={user_id} AND belonging_group={group_id} AND tool_type={tool_type}"
        
        cursor.execute(sql)
        conn.commit()
        
        # 更新缓存
        cache_key = (group_id, user_id, tool_type)
        with cache_lock:
            user_tool_cache[cache_key] = (amount, time.time())
    finally:
        db_pool.return_connection(conn)

def check_resource_cd(group_id: int, user_id: int, resource_type: int) -> Tuple[bool, str]:
    """检查资源生产CD"""
    # 先检查内存中是否有记录
    if (group_id, user_id, resource_type) in resource_cd:
        end_time = resource_cd[(group_id, user_id, resource_type)]
        if datetime.datetime.now() < end_time:
            remaining = end_time - datetime.datetime.now()
            minutes = remaining.seconds // 60
            seconds = remaining.seconds % 60
            return False, f"生产CD中，还需等待{minutes}分{seconds}秒"
        else:
            # CD已结束，删除记录
            del resource_cd[(group_id, user_id, resource_type)]
            return True, ""
    
    # 检查数据库
    init_resource_db()
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        sql = f"SELECT end_time FROM resource_production_cd WHERE uid={user_id} AND belonging_group={group_id} AND resource_type={resource_type}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            # 没有CD记录
            return True, ""
        else:
            end_time = datetime.datetime.fromisoformat(result[0])
            if datetime.datetime.now() < end_time:
                # 仍在CD期内
                remaining = end_time - datetime.datetime.now()
                minutes = remaining.seconds // 60
                seconds = remaining.seconds % 60
                
                # 更新内存记录
                resource_cd[(group_id, user_id, resource_type)] = end_time
                
                return False, f"生产CD中，还需等待{minutes}分{seconds}秒"
            else:
                # CD已结束，删除记录
                sql = f"DELETE FROM resource_production_cd WHERE uid={user_id} AND belonging_group={group_id} AND resource_type={resource_type}"
                cursor.execute(sql)
                conn.commit()
                return True, ""
    finally:
        db_pool.return_connection(conn)

def set_resource_cd(group_id: int, user_id: int, resource_type: int) -> None:
    """设置资源生产CD"""
    # 计算CD结束时间
    cd_seconds = RESOURCE_CD[resource_type]
    end_time = datetime.datetime.now() + datetime.timedelta(seconds=cd_seconds)
    
    # 更新内存记录
    resource_cd[(group_id, user_id, resource_type)] = end_time
    
    # 更新数据库
    init_resource_db()
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        sql = f"SELECT id FROM resource_production_cd WHERE uid={user_id} AND belonging_group={group_id} AND resource_type={resource_type}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            # 创建新记录
            sql = f"INSERT INTO resource_production_cd (uid, belonging_group, resource_type, end_time) VALUES ({user_id}, {group_id}, {resource_type}, '{end_time.isoformat()}')"
        else:
            # 更新记录
            sql = f"UPDATE resource_production_cd SET end_time='{end_time.isoformat()}' WHERE uid={user_id} AND belonging_group={group_id} AND resource_type={resource_type}"
        
        cursor.execute(sql)
        conn.commit()
    finally:
        db_pool.return_connection(conn)

def check_event_effect(group_id: int, resource_type: int) -> Tuple[bool, float]:
    """检查资源生产事件效果
    返回：(是否有效, 效果值)
    """
    # 检查是否为目标群聊(443234650)，只在该群聊中检查事件效果
    if group_id != 443234650:
        return False, 0.0
        
    # 导入事件模块
    from . import event
    
    # 检查自然灾害事件
    if resource_type == RESOURCE_FOOD:
        # 干旱事件
        has_effect, disaster_type, effect_value = event.check_event_effect(group_id, event.EVENT_NATURAL_DISASTER)
        if has_effect and disaster_type == event.DISASTER_DROUGHT:
            print(f"[资源系统] 群聊 {group_id} 中干旱事件生效，食物产量修正: {effect_value}")
            return True, effect_value
    elif resource_type == RESOURCE_WOOD:
        # 风暴事件
        has_effect, disaster_type, effect_value = event.check_event_effect(group_id, event.EVENT_NATURAL_DISASTER)
        if has_effect and disaster_type == event.DISASTER_STORM:
            print(f"[资源系统] 群聊 {group_id} 中风暴事件生效，木材产量修正: {effect_value}")
            return True, effect_value
    elif resource_type == RESOURCE_ORE:
        # 地震事件
        has_effect, disaster_type, effect_value = event.check_event_effect(group_id, event.EVENT_NATURAL_DISASTER)
        if has_effect and disaster_type == event.DISASTER_EARTHQUAKE:
            print(f"[资源系统] 群聊 {group_id} 中地震事件生效，矿石产量修正: {effect_value}")
            return True, effect_value
    
    # 检查特殊事件（黄金时间）
    has_effect, special_type, effect_value = event.check_event_effect(group_id, event.EVENT_SPECIAL)
    if has_effect and special_type == event.SPECIAL_GOLDEN_TIME:
        print(f"[资源系统] 群聊 {group_id} 中黄金时间事件生效，产量修正: {effect_value}")
        return True, effect_value
    
    return False, 0.0

def _base_produce_resource(group_id: int, user_id: int, resource_type: int) -> str:
    """基础资源生产函数，不包含职业加成"""
    # 检查CD
    allowed, message = check_resource_cd(group_id, user_id, resource_type)
    if not allowed:
        return message
    
    # 获取用户体力
    stamina = get_user_stamina(group_id, user_id)
    
    # 检查体力是否足够
    stamina_cost = RESOURCE_STAMINA_COST[resource_type]
    if stamina < stamina_cost:
        return f"体力不足，需要{stamina_cost}点体力，当前体力：{stamina}点"
    
    # 扣除体力
    update_user_stamina(group_id, user_id, stamina - stamina_cost)
    
    # 设置CD
    set_resource_cd(group_id, user_id, resource_type)
    
    # 计算产出
    min_output, max_output = RESOURCE_OUTPUT[resource_type]
    output = random.randint(min_output, max_output)
    
    # 检查事件效果
    has_effect, effect_value = check_event_effect(group_id, resource_type)
    if has_effect:
        # 应用事件效果修正产出
        output = int(output * effect_value)
        # 确保至少有1个产出
        output = max(1, output)
    
    # 更新资源数量
    current_amount = get_user_resource(group_id, user_id, resource_type)
    update_user_resource(group_id, user_id, resource_type, current_amount + output)
    
    # 构建回复消息
    resource_names = ["食物", "木材", "矿石"]
    resource_name = resource_names[resource_type]
    
    message = f"生产成功！消耗{stamina_cost}点体力，获得{output}个{resource_name}\n"
    message += f"当前{resource_name}：{current_amount + output}个\n"
    message += f"当前体力：{stamina - stamina_cost}点"
    
    return message

def produce_resource(group_id: int, user_id: int, resource_type: int) -> str:
    """生产资源"""
    # 检查资源类型是否有效
    if resource_type not in [RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE]:
        return "无效的资源类型"
    
    # 动态导入profession模块，避免循环导入
    from . import profession
    
    # 检查用户职业
    profession_type = profession.get_user_profession(group_id, user_id)
    
    # 如果是牛马职业，不能生产资源
    if profession_type == PROF_WORKER:
        return "牛马职业只能打工，无法生产资源"
    
    # 职业限制检查：只有对应职业才能执行特定资源收集操作
    if resource_type == RESOURCE_FOOD and profession_type != PROF_FARMER:
        return "只有农夫职业才能种地收集食物"
    elif resource_type == RESOURCE_WOOD and profession_type != PROF_LUMBERJACK:
        return "只有伐木工职业才能砍树收集木材"
    elif resource_type == RESOURCE_ORE and profession_type != PROF_MINER:
        return "只有矿工职业才能挖矿收集矿石"
    
    # 检查是否有职业
    if profession_type == PROF_NONE:
        return "请先选择一个职业才能进行资源收集"
    
    # 调用职业资源生产函数（包含工具和职业加成效果）
    return profession.produce_resource_with_profession(group_id, user_id, resource_type)

def eat_food(group_id: int, user_id: int, amount: int) -> str:
    """食用食物恢复体力"""
    # 检查数量是否有效
    if amount <= 0:
        return "请输入正确的数量"
    
    # 获取用户食物数量
    food_amount = get_user_resource(group_id, user_id, RESOURCE_FOOD)
    
    # 检查食物是否足够
    if food_amount < amount:
        return f"食物不足，当前食物：{food_amount}个"
    
    # 获取用户体力
    stamina = get_user_stamina(group_id, user_id)
    
    # 如果体力已满，无需食用
    if stamina >= MAX_STAMINA:
        return f"体力已满（{MAX_STAMINA}点），无需食用食物"
    
    # 计算实际需要的食物数量（不超过能恢复到满体力的量）
    needed_food = MAX_STAMINA - stamina
    actual_amount = min(amount, needed_food)
    
    # 扣除食物
    update_user_resource(group_id, user_id, RESOURCE_FOOD, food_amount - actual_amount)
    
    # 增加体力
    update_user_stamina(group_id, user_id, stamina + actual_amount)
    
    # 构建回复消息
    message = f"食用成功！消耗{actual_amount}个食物，恢复{actual_amount}点体力\n"
    message += f"当前食物：{food_amount - actual_amount}个\n"
    message += f"当前体力：{stamina + actual_amount}点"
    
    return message

def sell_resource(group_id: int, user_id: int, resource_type: int, amount: int) -> str:
    """出售资源"""
    # 检查资源类型是否有效
    if resource_type not in [RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE]:
        return "无效的资源类型"
    
    # 检查数量是否有效
    if amount <= 0:
        return "请输入正确的数量"
    
    # 获取用户资源数量
    resource_amount = get_user_resource(group_id, user_id, resource_type)
    
    # 检查资源是否足够
    if resource_amount < amount:
        resource_names = ["食物", "木材", "矿石"]
        resource_name = resource_names[resource_type]
        return f"{resource_name}不足，当前{resource_name}：{resource_amount}个"
    
    # 检查用户是否是商业联盟成员或富豪榜前三
    from .alliance import check_business_alliance_bonus
    from .casino import get_casino_leaderboard
    
    # 检查是否是商业联盟成员
    is_business_member = check_business_alliance_bonus(group_id, user_id)
    
    # 检查是否在富豪榜前三
    is_top_three = False
    
    # 直接查询数据库获取富豪榜前三名
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        # 联合查询金币和银行存款，获取前三名用户
        sql = f"""
        SELECT s.uid, s.points + COALESCE(b.balance, 0) as total_wealth 
        FROM sign_in s 
        LEFT JOIN bank_accounts b ON s.uid = b.uid AND s.belonging_group = b.belonging_group 
        WHERE s.belonging_group = {group_id} 
        ORDER BY total_wealth DESC 
        LIMIT 3
        """
        cursor.execute(sql)
        top_three_users = cursor.fetchall()
        
        # 检查用户是否在前三名
        for top_user_id, _ in top_three_users:
            if top_user_id == user_id:
                is_top_three = True
                break
    finally:
        db_pool.return_connection(conn)
    
    # 计算获得的金币（根据特权决定是否扣除交易税）
    price = RESOURCE_PRICES[resource_type]
    gross_amount = price * amount
    
    # 商业联盟成员或富豪榜前三免交易税
    tax_free = is_business_member or is_top_three
    coins = gross_amount if tax_free else gross_amount * 0.8
    tax_info = "（免交易税）" if tax_free else "（收取20%交易税）"
    
    # 扣除资源
    update_user_resource(group_id, user_id, resource_type, resource_amount - amount)
    
    # 增加金币
    user_coins = get_point(group_id, user_id)
    update_point(group_id, user_id, user_coins + coins)
    
    # 构建回复消息
    resource_names = ["食物", "木材", "矿石"]
    resource_name = resource_names[resource_type]
    
    message = f"出售成功！出售{amount}个{resource_name}，获得{coins:.2f}金币{tax_info}\n"
    message += f"当前{resource_name}：{resource_amount - amount}个\n"
    message += f"当前金币：{(user_coins + coins):.2f}"
    
    return message

def buy_resource(group_id: int, user_id: int, resource_type: int, amount: int) -> str:
    """购买资源"""
    # 检查资源类型是否有效
    if resource_type not in [RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE]:
        return "无效的资源类型"
    
    # 检查数量是否有效
    if amount <= 0:
        return "请输入正确的数量"
    
    # 检查每日购买限制
    from .resource_purchase_limit import check_purchase_limit, update_daily_purchases, DAILY_PURCHASE_LIMIT
    allowed, remaining = check_purchase_limit(group_id, user_id, resource_type, amount)
    if not allowed:
        resource_names = ["食物", "木材", "矿石"]
        resource_name = resource_names[resource_type]
        return f"超过每日购买限制！每天最多购买{DAILY_PURCHASE_LIMIT}单位{resource_name}，今日剩余可购买：{remaining}单位"
    
    # 计算需要的金币
    price = RESOURCE_PRICES[resource_type]
    coins_needed = price * amount
    
    # 检查金币是否足够
    user_coins = get_point(group_id, user_id)
    if user_coins < coins_needed:
        return f"金币不足，需要{coins_needed}金币，当前金币：{user_coins}"
    
    # 扣除金币
    update_point(group_id, user_id, user_coins - coins_needed)
    
    # 增加资源
    resource_amount = get_user_resource(group_id, user_id, resource_type)
    update_user_resource(group_id, user_id, resource_type, resource_amount + amount)
    
    # 更新今日购买记录
    current_purchases = check_purchase_limit(group_id, user_id, resource_type, 0)[1]
    update_daily_purchases(group_id, user_id, resource_type, DAILY_PURCHASE_LIMIT - current_purchases + amount)
    
    # 构建回复消息
    resource_names = ["食物", "木材", "矿石"]
    resource_name = resource_names[resource_type]
    
    message = f"购买成功！花费{coins_needed}金币，购买{amount}个{resource_name}\n"
    message += f"当前{resource_name}：{resource_amount + amount}个\n"
    message += f"当前金币：{user_coins - coins_needed}\n"
    message += f"今日剩余可购买{resource_name}：{DAILY_PURCHASE_LIMIT - (DAILY_PURCHASE_LIMIT - current_purchases + amount)}单位"
    
    return message

def get_resource_info(group_id: int, user_id: int) -> str:
    """获取资源信息"""
    # 获取用户体力
    stamina = get_user_stamina(group_id, user_id)
    
    # 获取用户资源
    food = get_user_resource(group_id, user_id, RESOURCE_FOOD)
    wood = get_user_resource(group_id, user_id, RESOURCE_WOOD)
    ore = get_user_resource(group_id, user_id, RESOURCE_ORE)
    
    # 获取用户金币
    coins = get_point(group_id, user_id)
    
    # 构建回复消息
    message = f"===== 资源信息 =====\n"
    message += f"体力：{stamina}/{MAX_STAMINA}\n\n"
    message += f"食物：{food}个（基准价格：{RESOURCE_PRICES[RESOURCE_FOOD]}金币/个）\n"
    message += f"木材：{wood}个（基准价格：{RESOURCE_PRICES[RESOURCE_WOOD]}金币/个）\n"
    message += f"矿石：{ore}个（基准价格：{RESOURCE_PRICES[RESOURCE_ORE]}金币/个）\n\n"
    message += f"金币：{coins}\n\n"
    message += f"===== 工具基准价格 =====\n"
    message += f"铁质工具：{TOOL_PRICES[TOOL_IRON]}金币/个\n"
    message += f"精金工具：{TOOL_PRICES[TOOL_FINE_GOLD]}金币/个\n"
    message += f"强化合金工具：{TOOL_PRICES[TOOL_ALLOY]}金币/个\n"
    message += f"强化合金工具【不毁】：无基准价格"
    
    return message

# 缓存清理函数
def clear_resource_cache():
    """清理过期缓存"""
    current_time = time.time()
    with cache_lock:
        # 清理体力缓存
        expired_keys = [key for key, (_, timestamp, _) in user_stamina_cache.items() if current_time - timestamp > CACHE_EXPIRY]
        for key in expired_keys:
            del user_stamina_cache[key]
        
        # 清理资源缓存
        expired_keys = [key for key, (_, timestamp) in user_resource_cache.items() if current_time - timestamp > CACHE_EXPIRY]
        for key in expired_keys:
            del user_resource_cache[key]
        
        # 清理工具缓存
        expired_keys = [key for key, (_, timestamp) in user_tool_cache.items() if current_time - timestamp > CACHE_EXPIRY]
        for key in expired_keys:
            del user_tool_cache[key]
        
        # 清理过期的CD记录
        expired_keys = []
        for key, end_time in resource_cd.items():
            if datetime.datetime.now() > end_time:
                expired_keys.append(key)
        for key in expired_keys:
            del resource_cd[key]

# 定期清理缓存
@scheduler.scheduled_job('cron', minute='*/10', id='clear_resource_cache')
async def schedule_clear_resource_cache():
    """每10分钟清理一次资源缓存"""
    clear_resource_cache()

# 初始化数据库
init_resource_db()