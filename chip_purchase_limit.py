import sqlite3
import datetime
from typing import Tuple, List, Optional
from .db import db_pool

# 筹码购买记录表结构
# - id: 主键
# - uid: 用户ID
# - belonging_group: 群组ID
# - amount: 购买/消耗筹码数量
# - operation_type: 操作类型（'buy'购买, 'consume'消耗）
# - operation_time: 操作时间

def init_chip_purchase_db():
    """初始化筹码购买记录数据库"""
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # 创建筹码购买记录表
        sql = """
        CREATE TABLE IF NOT EXISTS chip_purchase_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL,
            belonging_group INTEGER NOT NULL,
            amount REAL NOT NULL,
            operation_type TEXT NOT NULL,
            operation_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        cursor.execute(sql)
        conn.commit()
    finally:
        if conn:
            conn.close()

def add_chip_purchase_record(group_id: int, user_id: int, amount: float):
    """添加筹码购买记录
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        amount: 购买筹码数量
    """
    init_chip_purchase_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # 添加购买记录
        sql = f"INSERT INTO chip_purchase_records (uid, belonging_group, amount, operation_type) VALUES ({user_id}, {group_id}, {amount}, 'buy')"
        cursor.execute(sql)
        conn.commit()
    finally:
        if conn:
            conn.close()

def add_chip_consumption_record(group_id: int, user_id: int, amount: float):
    """添加筹码消耗记录
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        amount: 消耗筹码数量
    """
    init_chip_purchase_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # 添加消耗记录
        sql = f"INSERT INTO chip_purchase_records (uid, belonging_group, amount, operation_type) VALUES ({user_id}, {group_id}, {amount}, 'consume')"
        cursor.execute(sql)
        conn.commit()
    finally:
        if conn:
            conn.close()

def get_consecutive_purchases(group_id: int, user_id: int) -> int:
    """获取用户连续购买筹码次数（未消耗）
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        
    Returns:
        int: 连续购买次数
    """
    init_chip_purchase_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # 获取最近的操作记录
        sql = f"""
        SELECT operation_type FROM chip_purchase_records 
        WHERE uid={user_id} AND belonging_group={group_id} 
        ORDER BY operation_time DESC
        """
        cursor.execute(sql)
        results = cursor.fetchall()
        
        # 计算连续购买次数
        consecutive_count = 0
        for result in results:
            operation_type = result[0]
            if operation_type == 'buy':
                consecutive_count += 1
            else:  # 遇到消耗记录，中断计数
                break
        
        return consecutive_count
    finally:
        if conn:
            conn.close()

def get_consumed_chips_since_limit(group_id: int, user_id: int) -> float:
    """获取用户自受到限制以来消耗的筹码总量
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        
    Returns:
        float: 消耗的筹码总量
    """
    init_chip_purchase_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # 获取最近的购买记录（连续购买超过3次的最早一次）
        consecutive_purchases = get_consecutive_purchases(group_id, user_id)
        if consecutive_purchases < 3:
            # 未受到限制，返回0
            return 0.0
        
        # 获取连续购买记录的时间点
        sql = f"""
        SELECT operation_time FROM chip_purchase_records 
        WHERE uid={user_id} AND belonging_group={group_id} AND operation_type='buy'
        ORDER BY operation_time DESC
        LIMIT {consecutive_purchases}
        """
        cursor.execute(sql)
        results = cursor.fetchall()
        
        if len(results) < consecutive_purchases:
            return 0.0
        
        # 获取限制开始的时间点（第三次连续购买的时间）
        limit_start_time = results[-1][0]
        
        # 获取从限制开始时间点之后的消耗记录总和
        sql = f"""
        SELECT SUM(amount) FROM chip_purchase_records 
        WHERE uid={user_id} AND belonging_group={group_id} AND operation_type='consume'
        AND operation_time > '{limit_start_time}'
        """
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result[0] is None:
            return 0.0
        else:
            return float(result[0])
    finally:
        if conn:
            conn.close()

def reset_consumption_records(group_id: int, user_id: int) -> None:
    """重置用户的筹码消耗记录（抢银行后调用）
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
    """
    # 不删除实际记录，而是添加一条特殊的消耗记录，标记重置点
    init_chip_purchase_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # 添加重置记录（使用特殊的amount值-1作为标记）
        sql = f"INSERT INTO chip_purchase_records (uid, belonging_group, amount, operation_type) VALUES ({user_id}, {group_id}, -1, 'reset')"
        cursor.execute(sql)
        conn.commit()
    finally:
        if conn:
            conn.close()

def calculate_price_increase(group_id: int, user_id: int, chips_amount: float) -> float:
    """计算用户购买筹码的价格增加比例
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        chips_amount: 当前持有筹码数量
        
    Returns:
        float: 价格增加比例（1.0表示原价，1.1表示增加10%）
    """
    # 导入获取当天兑换比例的函数
    from .casino import get_chip_rate
    
    # 如果用户持有筹码为0，直接返回原价比例1.0
    if chips_amount <= 0:
        return 1.0
    
    # 检查是否持有超过10000筹码
    chips_limit_reached = chips_amount >= 10000
    
    # 如果持有筹码超过10000，检查是否已经消耗足够的筹码
    if chips_limit_reached:
        # 获取自受到限制以来消耗的筹码总量
        consumed_chips = get_consumed_chips_since_limit(group_id, user_id)
        
        # 计算需要消耗的筹码量（当前持有筹码的25%）
        required_consumption = chips_amount * 0.25
        
        # 如果已消耗足够的筹码，解除限制
        if consumed_chips >= required_consumption:
            return 1.0
        
        # 否则，计算价格增加
        # 每持有1单位筹码，价格增加0.5%
        increase_percentage = (chips_amount / 100) * 0.005
        return 1.0 + increase_percentage
    
    # 不满足条件，返回原价比例
    return 1.0