import sqlite3
import datetime
from typing import Dict, Tuple

# 每日购买限制常量
DAILY_PURCHASE_LIMIT = 50  # 每天最多购买50单位资源

# 用户每日购买记录字典 {(group_id, user_id, resource_type, date): amount}
user_daily_purchases: Dict[Tuple[int, int, int, str], int] = {}

def init_purchase_limit_db():
    """初始化购买限制数据库"""
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 创建用户每日购买记录表
    sql = """
    CREATE TABLE IF NOT EXISTS resource_daily_purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        resource_type INTEGER NOT NULL,  -- 0: 食物, 1: 木材, 2: 矿石
        purchase_date DATE NOT NULL,
        amount INTEGER NOT NULL DEFAULT 0,
        UNIQUE(uid, belonging_group, resource_type, purchase_date)
    )
    """
    cursor.execute(sql)
    
    conn.commit()
    cursor.close()
    conn.close()

def get_daily_purchases(group_id: int, user_id: int, resource_type: int) -> int:
    """获取用户今日购买资源数量"""
    today = datetime.date.today().isoformat()
    
    # 先检查内存中是否有记录
    if (group_id, user_id, resource_type, today) in user_daily_purchases:
        return user_daily_purchases[(group_id, user_id, resource_type, today)]
    
    init_purchase_limit_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT amount FROM resource_daily_purchases WHERE uid={user_id} AND belonging_group={group_id} AND resource_type={resource_type} AND purchase_date='{today}'"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 创建新记录
        sql = f"INSERT INTO resource_daily_purchases (uid, belonging_group, resource_type, purchase_date, amount) VALUES ({user_id}, {group_id}, {resource_type}, '{today}', 0)"
        cursor.execute(sql)
        conn.commit()
        amount = 0
    else:
        amount = int(result[0])
    
    # 更新内存记录
    user_daily_purchases[(group_id, user_id, resource_type, today)] = amount
    
    cursor.close()
    conn.close()
    return amount

def update_daily_purchases(group_id: int, user_id: int, resource_type: int, amount: int) -> None:
    """更新用户今日购买资源数量"""
    today = datetime.date.today().isoformat()
    
    init_purchase_limit_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 确保数量不为负
    amount = max(0, amount)
    
    sql = f"SELECT id FROM resource_daily_purchases WHERE uid={user_id} AND belonging_group={group_id} AND resource_type={resource_type} AND purchase_date='{today}'"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 创建新记录
        sql = f"INSERT INTO resource_daily_purchases (uid, belonging_group, resource_type, purchase_date, amount) VALUES ({user_id}, {group_id}, {resource_type}, '{today}', {amount})"
    else:
        # 更新记录
        sql = f"UPDATE resource_daily_purchases SET amount={amount} WHERE uid={user_id} AND belonging_group={group_id} AND resource_type={resource_type} AND purchase_date='{today}'"
    
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()
    
    # 更新内存记录
    user_daily_purchases[(group_id, user_id, resource_type, today)] = amount

def check_purchase_limit(group_id: int, user_id: int, resource_type: int, amount: int) -> Tuple[bool, int]:
    """检查购买是否超过每日限制
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        resource_type: 资源类型
        amount: 要购买的数量
        
    Returns:
        Tuple[bool, int]: (是否允许购买, 今日剩余可购买数量)
    """
    # 获取今日已购买数量
    purchased = get_daily_purchases(group_id, user_id, resource_type)
    
    # 计算剩余可购买数量
    remaining = DAILY_PURCHASE_LIMIT - purchased
    
    # 检查是否超过限制
    if amount > remaining:
        return False, remaining
    
    return True, remaining