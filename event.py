import sqlite3
import datetime
import random
import time
import asyncio
from typing import Dict, List, Tuple, Optional, Union
from nonebot import require, get_bot
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent

# 导入公共数据库连接池
from .db import db_pool

from .resource import (
    get_user_resource, update_user_resource, RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE,
    update_user_stamina, get_user_stamina, MAX_STAMINA
)
from .bank import get_bank_balance, update_bank_balance
from .sign import get_point, update_point
from .casino import get_casino_leaderboard

# 事件类型常量
EVENT_NATURAL_DISASTER = 0  # 自然灾害
EVENT_MARKET = 1            # 市场事件
EVENT_SPECIAL = 2           # 特殊事件
EVENT_WEALTH = 3            # 贫富事件
EVENT_INFLATION = 4         # 通胀事件

# 自然灾害类型
DISASTER_DROUGHT = 0        # 干旱（食物-50%/1小时）
DISASTER_STORM = 1          # 风暴（木材-40%/30分钟）
DISASTER_EARTHQUAKE = 2     # 地震（矿石-30%/45分钟）

# 市场事件类型
MARKET_PRICE_SURGE = 0      # 价格飙升（+100%/30分钟）
MARKET_CRASH = 1            # 市场崩溃（-30%/1小时）

# 特殊事件类型
SPECIAL_GOLDEN_TIME = 0     # 黄金时间（产量+50%/30分钟）
SPECIAL_ENERGY_BOOST = 1    # 能量提升（体力消耗-40%/1小时）

# 事件状态字典 {group_id: {event_type: {"type": event_subtype, "end_time": datetime, "effect": effect_value}}}
event_status: Dict[int, Dict[int, Dict[str, any]]] = {}

# 富豪榜特权状态 {group_id: {user_id: {"rank": rank, "privileges": [privileges]}}}
wealth_rank_privileges: Dict[int, Dict[int, Dict[str, any]]] = {}

# 事件触发概率（10%）
EVENT_TRIGGER_PROBABILITY = 0.1

def init_event_db():
    """初始化事件数据库"""
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        # 创建事件记录表
        sql = """
        CREATE TABLE IF NOT EXISTS event_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            belonging_group INTEGER NOT NULL,
            event_type INTEGER NOT NULL,  -- 0: 自然灾害, 1: 市场事件, 2: 特殊事件, 3: 贫富事件, 4: 通胀事件
            event_subtype INTEGER NOT NULL,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            effect_value REAL NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
        cursor.execute(sql)
        
        # 创建富豪榜表
        sql = """
        CREATE TABLE IF NOT EXISTS wealth_ranking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            belonging_group INTEGER NOT NULL,
            uid INTEGER NOT NULL,
            rank INTEGER NOT NULL,
            total_wealth REAL NOT NULL,
            update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(belonging_group, uid)
        )
        """
        cursor.execute(sql)
        
        conn.commit()
    finally:
        db_pool.return_connection(conn)

def get_active_events(group_id: int) -> Dict[int, Dict[str, any]]:
    """获取群组当前活跃的事件"""
    # 检查内存中是否有记录
    if group_id in event_status:
        return event_status[group_id]
    
    # 从数据库加载活跃事件
    init_event_db()
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        now = datetime.datetime.now().isoformat()
        sql = f"SELECT event_type, event_subtype, end_time, effect_value FROM event_records WHERE belonging_group={group_id} AND is_active=1 AND end_time > '{now}'"
        cursor.execute(sql)
        results = cursor.fetchall()
        
        # 初始化群组事件状态
        event_status[group_id] = {}
        
        # 加载活跃事件
        for event_type, event_subtype, end_time, effect_value in results:
            event_status[group_id][event_type] = {
                "type": event_subtype,
                "end_time": datetime.datetime.fromisoformat(end_time),
                "effect": effect_value
            }
        
        return event_status[group_id]
    finally:
        db_pool.return_connection(conn)

def add_event(group_id: int, event_type: int, event_subtype: int, duration_minutes: int, effect_value: float) -> bool:
    """添加新事件"""
    # 检查是否已有同类型事件
    active_events = get_active_events(group_id)
    if event_type in active_events:
        # 已有同类型事件，不添加新事件
        return False
    
    # 计算结束时间
    start_time = datetime.datetime.now()
    end_time = start_time + datetime.timedelta(minutes=duration_minutes)
    
    # 添加到内存
    if group_id not in event_status:
        event_status[group_id] = {}
    
    event_status[group_id][event_type] = {
        "type": event_subtype,
        "end_time": end_time,
        "effect": effect_value
    }
    
    # 添加到数据库
    init_event_db()
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        sql = f"INSERT INTO event_records (belonging_group, event_type, event_subtype, start_time, end_time, effect_value, is_active) VALUES ({group_id}, {event_type}, {event_subtype}, '{start_time.isoformat()}', '{end_time.isoformat()}', {effect_value}, 1)"
        cursor.execute(sql)
        
        conn.commit()
    finally:
        db_pool.return_connection(conn)
    
    return True

def end_event(group_id: int, event_type: int) -> bool:
    """结束事件"""
    # 检查是否有该事件
    active_events = get_active_events(group_id)
    if event_type not in active_events:
        return False
    
    # 从内存中移除
    del event_status[group_id][event_type]
    
    # 更新数据库
    init_event_db()
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        now = datetime.datetime.now().isoformat()
        sql = f"UPDATE event_records SET is_active=0, end_time='{now}' WHERE belonging_group={group_id} AND event_type={event_type} AND is_active=1"
        cursor.execute(sql)
        
        conn.commit()
    finally:
        db_pool.return_connection(conn)
    
    return True

def check_event_effect(group_id: int, event_type: int) -> Tuple[bool, int, float]:
    """检查事件效果
    返回：(是否有效, 子类型, 效果值)
    """
    # 检查是否为目标群聊(443234650)，只在该群聊中生效事件效果
    if group_id != 443234650:
        return False, -1, 0.0
    
    active_events = get_active_events(group_id)
    
    if event_type in active_events:
        event = active_events[event_type]
        # 检查事件是否已过期
        if datetime.datetime.now() > event["end_time"]:
            end_event(group_id, event_type)
            return False, -1, 0.0
        
        print(f"[事件系统] 群聊 {group_id} 中事件 {event_type} 生效中，效果值: {event['effect']}")
        return True, event["type"], event["effect"]
    
    return False, -1, 0.0

async def trigger_random_event(group_id: int) -> Optional[str]:
    """触发随机事件
    返回：事件描述消息，如果没有触发事件则返回None
    """
    # 检查是否为目标群聊(443234650)，只在该群聊中触发事件
    if group_id != 443234650:
        print(f"[事件系统] 群聊 {group_id} 不是目标群聊，跳过事件触发")
        return None
    
    print(f"[事件系统] 尝试在群聊 {group_id} 中触发事件")
    
    # 随机决定是否触发事件（10%概率）
    if random.random() > EVENT_TRIGGER_PROBABILITY:
        print(f"[事件系统] 随机概率未达到触发条件，跳过事件触发")
        return None
    
    # 随机选择事件类型
    event_type = random.randint(0, 4)  # 0-4对应五种事件类型
    print(f"[事件系统] 触发事件类型: {event_type}")
    
    # 根据事件类型触发具体事件
    if event_type == EVENT_NATURAL_DISASTER:
        return await trigger_natural_disaster(group_id)
    elif event_type == EVENT_MARKET:
        return await trigger_market_event(group_id)
    elif event_type == EVENT_SPECIAL:
        return await trigger_special_event(group_id)
    elif event_type == EVENT_WEALTH:
        return await trigger_wealth_event(group_id)
    elif event_type == EVENT_INFLATION:
        return await trigger_inflation_event(group_id)
    
    return None

async def trigger_natural_disaster(group_id: int) -> str:
    """触发自然灾害事件"""
    # 随机选择灾害类型
    disaster_type = random.randint(0, 2)  # 0-2对应三种灾害
    
    if disaster_type == DISASTER_DROUGHT:
        # 干旱：食物-50%/1小时
        add_event(group_id, EVENT_NATURAL_DISASTER, DISASTER_DROUGHT, 60, -0.5)
        return "【自然灾害】干旱来袭！未来1小时内，食物产量减少50%！"
    
    elif disaster_type == DISASTER_STORM:
        # 风暴：木材-40%/30分钟
        add_event(group_id, EVENT_NATURAL_DISASTER, DISASTER_STORM, 30, -0.4)
        return "【自然灾害】风暴来袭！未来30分钟内，木材产量减少40%！"
    
    elif disaster_type == DISASTER_EARTHQUAKE:
        # 地震：矿石-30%/45分钟
        add_event(group_id, EVENT_NATURAL_DISASTER, DISASTER_EARTHQUAKE, 45, -0.3)
        return "【自然灾害】地震来袭！未来45分钟内，矿石产量减少30%！"
    
    return "发生了未知的自然灾害！"

async def trigger_market_event(group_id: int) -> str:
    """触发市场事件"""
    # 随机选择市场事件类型
    market_type = random.randint(0, 1)  # 0-1对应两种市场事件
    
    # 随机选择受影响的资源类型
    resource_type = random.randint(0, 2)  # 0-2对应食物、木材、矿石
    resource_name = ["食物", "木材", "矿石"][resource_type]
    
    if market_type == MARKET_PRICE_SURGE:
        # 价格飙升：+100%/30分钟
        add_event(group_id, EVENT_MARKET, MARKET_PRICE_SURGE, 30, 1.0)
        return f"【市场事件】{resource_name}价格飙升！未来30分钟内，{resource_name}价格提高100%！"
    
    elif market_type == MARKET_CRASH:
        # 市场崩溃：-30%/1小时
        add_event(group_id, EVENT_MARKET, MARKET_CRASH, 60, -0.3)
        return f"【市场事件】{resource_name}市场崩溃！未来1小时内，{resource_name}价格降低30%！"
    
    return "发生了未知的市场事件！"

async def trigger_special_event(group_id: int) -> str:
    """触发特殊事件"""
    # 随机选择特殊事件类型
    special_type = random.randint(0, 1)  # 0-1对应两种特殊事件
    
    if special_type == SPECIAL_GOLDEN_TIME:
        # 黄金时间：产量+50%/30分钟
        add_event(group_id, EVENT_SPECIAL, SPECIAL_GOLDEN_TIME, 30, 0.5)
        return "【特殊事件】黄金时间！未来30分钟内，所有资源产量提高50%！"
    
    elif special_type == SPECIAL_ENERGY_BOOST:
        # 能量提升：体力消耗-40%/1小时
        add_event(group_id, EVENT_SPECIAL, SPECIAL_ENERGY_BOOST, 60, -0.4)
        return "【特殊事件】能量提升！未来1小时内，体力消耗减少40%！"
    
    return "发生了未知的特殊事件！"

async def trigger_wealth_event(group_id: int) -> str:
    """触发贫富事件（起义）"""
    # 获取富豪榜前三名
    top_users = await get_wealth_ranking(group_id, limit=3)
    
    if not top_users or len(top_users) < 1:
        return "【贫富事件】穷人们想要发起起义，但找不到足够富有的目标！"
    
    # 随机选择一位富豪
    target_index = random.randint(0, min(2, len(top_users) - 1))
    target_user_id, target_wealth = top_users[target_index]
    
    # 计算损失金额（20%的存款）
    bank_balance = get_bank_balance(group_id, target_user_id)
    loss_amount = bank_balance * 0.2
    
    # 更新银行余额
    if bank_balance > 0:
        update_bank_balance(group_id, target_user_id, bank_balance - loss_amount)
        
        # 记录事件
        add_event(group_id, EVENT_WEALTH, 0, 10, -0.2)  # 短暂事件，10分钟后自动结束
        
        # 获取用户昵称（如果可能）
        try:
            bot = get_bot()
            user_info = await bot.get_group_member_info(group_id=group_id, user_id=target_user_id)
            user_name = user_info.get('card') or user_info.get('nickname', f'用户{target_user_id}')
        except:
            user_name = f'用户{target_user_id}'
        
        return f"【贫富事件】起义爆发！穷人们抢劫了富豪 {user_name}，造成其损失 {loss_amount:.2f} 金币（银行存款的20%）！"
    else:
        return "【贫富事件】穷人们想要发起起义，但富豪们的银行存款都空空如也！"

async def trigger_inflation_event(group_id: int) -> str:
    """触发通胀事件（银行遭劫匪）"""
    # 获取所有有银行存款的用户
    init_event_db()
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        sql = f"SELECT uid FROM bank_accounts WHERE belonging_group={group_id} AND balance > 0"
        cursor.execute(sql)
        users = cursor.fetchall()
        
        return users
    finally:
        db_pool.return_connection(conn)
    
    if not users:
        return "【通胀事件】银行遭到劫匪袭击，但没有人有存款，劫匪空手而归！"
    
    # 对每个用户扣除10%存款
    affected_count = 0
    total_loss = 0.0
    
    for (user_id,) in users:
        bank_balance = get_bank_balance(group_id, user_id)
        if bank_balance > 0:
            loss_amount = bank_balance * 0.1
            update_bank_balance(group_id, user_id, bank_balance - loss_amount)
            affected_count += 1
            total_loss += loss_amount
    
    # 记录事件
    add_event(group_id, EVENT_INFLATION, 0, 10, -0.1)  # 短暂事件，10分钟后自动结束
    
    return f"【通胀事件】银行遭到劫匪袭击！全体玩家存款金币减少10%！共有 {affected_count} 名玩家受影响，总损失 {total_loss:.2f} 金币！"

async def get_wealth_ranking(group_id: int, limit: int = 10) -> List[Tuple[int, float]]:
    """获取财富排行榜
    返回：[(user_id, total_wealth), ...]
    """
    # 计算每个用户的总财富（金币 + 银行存款）
    init_event_db()
    
    # 确保bank_accounts表存在
    from .bank import init_bank_db
    init_bank_db()
    
    conn = db_pool.get_connection()
    try:
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
        
        # 更新富豪榜数据库
        now = datetime.datetime.now().isoformat()
        for rank, (uid, total_wealth) in enumerate(results, 1):
            # 检查是否已有记录
            sql = f"SELECT id FROM wealth_ranking WHERE belonging_group={group_id} AND uid={uid}"
            cursor.execute(sql)
            result = cursor.fetchone()
            
            if result:
                # 更新记录
                sql = f"UPDATE wealth_ranking SET rank={rank}, total_wealth={total_wealth}, update_time='{now}' WHERE belonging_group={group_id} AND uid={uid}"
            else:
                # 创建新记录
                sql = f"INSERT INTO wealth_ranking (belonging_group, uid, rank, total_wealth, update_time) VALUES ({group_id}, {uid}, {rank}, {total_wealth}, '{now}')"
            
            cursor.execute(sql)
        
        conn.commit()
        
        return results
    finally:
        db_pool.return_connection(conn)
    
    # 更新富豪榜特权
    update_wealth_rank_privileges(group_id, results)
    
    return results

def update_wealth_rank_privileges(group_id: int, ranking_data: List[Tuple[int, float]]):
    """更新富豪榜特权"""
    if group_id not in wealth_rank_privileges:
        wealth_rank_privileges[group_id] = {}
    
    # 清除旧特权
    wealth_rank_privileges[group_id].clear()
    
    # 为前三名设置特权
    for rank, (uid, total_wealth) in enumerate(ranking_data[:3], 1):
        wealth_rank_privileges[group_id][uid] = {
            "rank": rank,
            "privileges": ["tax_free"]  # 免税特权
        }

def check_wealth_rank_privilege(group_id: int, user_id: int, privilege: str) -> bool:
    """检查用户是否拥有特定富豪榜特权"""
    if group_id in wealth_rank_privileges and user_id in wealth_rank_privileges[group_id]:
        return privilege in wealth_rank_privileges[group_id][user_id]["privileges"]
    return False

async def get_wealth_ranking_message(group_id: int, limit: int = 10) -> str:
    """获取财富排行榜消息"""
    ranking_data = await get_wealth_ranking(group_id, limit)
    
    if not ranking_data:
        return "暂无财富排行数据"
    
    message = "===== 财富排行榜 =====\n"
    message += "排名  用户ID  总财富  特权\n"
    
    # 获取Bot实例
    try:
        bot = get_bot()
        
        for rank, (uid, total_wealth) in enumerate(ranking_data, 1):
            # 获取用户昵称
            try:
                user_info = await bot.get_group_member_info(group_id=group_id, user_id=uid)
                user_name = user_info.get('card') or user_info.get('nickname', f'用户{uid}')
            except:
                user_name = f'用户{uid}'
            
            # 获取特权信息
            privileges = ""
            if rank <= 3:
                privileges = "免税"
            
            message += f"{rank}. {user_name}({uid}): {total_wealth:.2f} 金币 {privileges}\n"
    except:
        # 如果无法获取Bot实例，使用简化版本
        for rank, (uid, total_wealth) in enumerate(ranking_data, 1):
            privileges = "免税" if rank <= 3 else ""
            message += f"{rank}. 用户{uid}: {total_wealth:.2f} 金币 {privileges}\n"
    
    return message

# 定时任务
scheduler = require("nonebot_plugin_apscheduler").scheduler

@scheduler.scheduled_job("interval", hours=1)
async def hourly_event_check():
    """每小时检查是否触发事件"""
    # 获取所有Bot实例
    try:
        bot = get_bot()
        
        print("[事件系统] 开始执行每小时事件检查")
        
        # 只在目标群聊(443234650)中触发事件
        target_group_id = 443234650
        
        # 检查Bot是否在目标群聊中
        groups = await bot.get_group_list()
        group_ids = [group["group_id"] for group in groups]
        
        if target_group_id in group_ids:
            print(f"[事件系统] 尝试在目标群聊 {target_group_id} 中触发事件")
            
            # 尝试触发随机事件
            event_message = await trigger_random_event(target_group_id)
            
            # 如果触发了事件，发送通知
            if event_message:
                print(f"[事件系统] 成功触发事件: {event_message}")
                await bot.send_group_msg(group_id=target_group_id, message=event_message)
            else:
                print("[事件系统] 未触发任何事件")
        else:
            print(f"[事件系统] Bot不在目标群聊 {target_group_id} 中，跳过事件触发")
    except Exception as e:
        print(f"Error in hourly_event_check: {e}")

# 检查事件状态，清理过期事件
@scheduler.scheduled_job("interval", minutes=5)
def clean_expired_events():
    """清理过期事件"""
    now = datetime.datetime.now()
    print(f"[事件系统] 开始清理过期事件，当前时间: {now.isoformat()}")
    
    # 检查所有群组的事件
    for group_id in list(event_status.keys()):
        # 只处理目标群聊(443234650)的事件
        if group_id != 443234650:
            continue
            
        print(f"[事件系统] 检查群聊 {group_id} 的事件状态")
        for event_type in list(event_status[group_id].keys()):
            event = event_status[group_id][event_type]
            if now > event["end_time"]:
                print(f"[事件系统] 事件 {event_type} 已过期，结束时间: {event['end_time'].isoformat()}")
                end_event(group_id, event_type)
            else:
                print(f"[事件系统] 事件 {event_type} 仍在生效中，结束时间: {event['end_time'].isoformat()}")

# 添加测试函数，用于验证事件系统是否正常工作
async def test_event_system():
    """测试事件系统是否正常工作"""
    target_group_id = 443234650
    print(f"[事件系统测试] 开始测试事件系统在群聊 {target_group_id} 中的工作状态")
    
    # 测试触发随机事件
    event_message = await trigger_random_event(target_group_id)
    if event_message:
        print(f"[事件系统测试] 成功触发事件: {event_message}")
    else:
        print("[事件系统测试] 未触发任何事件")
    
    # 测试非目标群聊
    non_target_group_id = 12345678
    event_message = await trigger_random_event(non_target_group_id)
    if event_message is None:
        print(f"[事件系统测试] 非目标群聊 {non_target_group_id} 成功跳过事件触发")
    else:
        print(f"[事件系统测试] 错误: 非目标群聊 {non_target_group_id} 触发了事件")
    
    print("[事件系统测试] 测试完成")
    return "事件系统测试完成"