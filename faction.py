import sqlite3
import datetime
import random
import time
from typing import Dict, List, Tuple, Optional, Union
from .sign import get_point, update_point
from .resource import (
    get_user_resource, update_user_resource, 
    RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE,
    RESOURCE_PRICES
)
from .common import SPECIAL_BLUE_GEM, SPECIAL_DEMON_BRANCH
from .db import db_pool

# 阵营类型常量
FACTION_NONE = -1      # 无阵营
FACTION_WATER = 0      # 水水军
FACTION_DEMON = 1      # 魔王军

# 阵营名称
FACTION_NAMES = {
    FACTION_WATER: "水水军",
    FACTION_DEMON: "魔王军"
}

# 阵营特殊资源
FACTION_SPECIAL_RESOURCES = {
    FACTION_WATER: SPECIAL_BLUE_GEM,      # 水水军：海蓝宝石
    FACTION_DEMON: SPECIAL_DEMON_BRANCH   # 魔王军：恶魔树枝干
}

# 阵营资源池字典 {group_id: {faction_type: {resource_type: amount}}}
faction_resource_pools: Dict[int, Dict[int, Dict[int, int]]] = {}

# 阵营战争状态字典 {group_id: {"attacker": faction_type, "defender": faction_type, "start_time": timestamp, "end_time": timestamp}}
faction_wars: Dict[int, Dict[str, Union[int, float]]] = {}

# 阵营贸易禁运字典 {group_id: {faction_type: {target_faction: [resource_types]}}}
trade_embargoes: Dict[int, Dict[int, Dict[int, List[int]]]] = {}

# 阵营投票字典 {group_id: {faction_type: {"vote_type": type, "target": target, "resource": resource_type, "votes": {user_id: vote}}}}
faction_votes: Dict[int, Dict[int, Dict[str, Union[int, Dict[int, bool]]]]] = {}

# 特殊资源产出CD字典 {(group_id, user_id): end_time}
special_resource_cd: Dict[Tuple[int, int], float] = {}

def init_faction_db():
    """初始化阵营数据库"""
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # 创建阵营成员表
        sql = """
        CREATE TABLE IF NOT EXISTS faction_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL,
            belonging_group INTEGER NOT NULL,
            faction_type INTEGER NOT NULL DEFAULT -1,  -- -1: 无阵营, 0: 水水军, 1: 魔王军
            join_date DATE NOT NULL,
            UNIQUE(uid, belonging_group)
        )
        """
        cursor.execute(sql)
        
        # 创建阵营资源池表
        sql = """
        CREATE TABLE IF NOT EXISTS faction_resource_pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            belonging_group INTEGER NOT NULL,
            faction_type INTEGER NOT NULL,  -- 0: 水水军, 1: 魔王军
            resource_type INTEGER NOT NULL,  -- 0: 食物, 1: 木材, 2: 矿石
            amount INTEGER NOT NULL DEFAULT 0,
            UNIQUE(belonging_group, faction_type, resource_type)
        )
        """
        cursor.execute(sql)
        
        # 创建阵营战争记录表
        sql = """
        CREATE TABLE IF NOT EXISTS faction_war_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            belonging_group INTEGER NOT NULL,
            attacker_faction INTEGER NOT NULL,
            defender_faction INTEGER NOT NULL,
            resource_type INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            war_date DATE NOT NULL
        )
        """
        cursor.execute(sql)
        
        # 创建贸易禁运表
        sql = """
        CREATE TABLE IF NOT EXISTS trade_embargoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            belonging_group INTEGER NOT NULL,
            faction_type INTEGER NOT NULL,  -- 发起禁运的阵营
            target_faction INTEGER NOT NULL,  -- 被禁运的阵营
            resource_type INTEGER NOT NULL,  -- 被禁运的资源类型
            start_date DATE NOT NULL,
            UNIQUE(belonging_group, faction_type, target_faction, resource_type)
        )
        """
        cursor.execute(sql)
        
        conn.commit()
    finally:
        if conn:
            db_pool.return_connection(conn)

def get_user_faction(group_id: int, user_id: int) -> int:
    """获取用户所属阵营"""
    init_faction_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        sql = f"SELECT faction_type FROM faction_members WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            # 创建新记录，默认无阵营
            sql = f"INSERT INTO faction_members (uid, belonging_group, faction_type, join_date) VALUES ({user_id}, {group_id}, {FACTION_NONE}, '{datetime.date.today().isoformat()}')"
            cursor.execute(sql)
            conn.commit()
            faction_type = FACTION_NONE
        else:
            faction_type = result[0]
        
        return faction_type
    finally:
        if conn:
            db_pool.return_connection(conn)

def join_faction(group_id: int, user_id: int, faction_type: int) -> str:
    """加入阵营"""
    # 检查阵营类型是否有效
    if faction_type not in [FACTION_WATER, FACTION_DEMON]:
        return "无效的阵营类型！"
    
    # 获取用户当前阵营
    current_faction = get_user_faction(group_id, user_id)
    
    # 如果已经在该阵营中
    if current_faction == faction_type:
        return f"你已经是{FACTION_NAMES[faction_type]}的成员了！"
    
    # 如果在其他阵营中
    if current_faction != FACTION_NONE:
        return f"你已经是{FACTION_NAMES[current_faction]}的成员，一旦加入阵营不可切换！"
    
    # 加入新阵营
    init_faction_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        today = datetime.date.today().isoformat()
        sql = f"UPDATE faction_members SET faction_type={faction_type}, join_date='{today}' WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        conn.commit()
        
        # 返回加入成功信息和阵营特权说明
        special_resource = "海蓝宝石" if faction_type == FACTION_WATER else "恶魔树枝干"
        return f"你已成功加入{FACTION_NAMES[faction_type]}！\n\n阵营特权：\n- 可以产出特殊资源：{special_resource}\n- 可以参与阵营资源池共享\n- 可以参与阵营战争和贸易禁运"
    finally:
        if conn:
            db_pool.return_connection(conn)

def get_faction_members(group_id: int, faction_type: int) -> List[int]:
    """获取阵营成员列表"""
    init_faction_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        sql = f"SELECT uid FROM faction_members WHERE belonging_group={group_id} AND faction_type={faction_type}"
        cursor.execute(sql)
        results = cursor.fetchall()
        
        members = [result[0] for result in results]
        
        return members
    finally:
        if conn:
            db_pool.return_connection(conn)

def get_faction_resource_pool(group_id: int, faction_type: int, resource_type: int) -> int:
    """获取阵营资源池中的资源数量"""
    # 先从内存中查找
    if group_id in faction_resource_pools and faction_type in faction_resource_pools[group_id] and resource_type in faction_resource_pools[group_id][faction_type]:
        return faction_resource_pools[group_id][faction_type][resource_type]
    
    # 从数据库中查询
    init_faction_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        sql = f"SELECT amount FROM faction_resource_pools WHERE belonging_group={group_id} AND faction_type={faction_type} AND resource_type={resource_type}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            # 创建新记录
            sql = f"INSERT INTO faction_resource_pools (belonging_group, faction_type, resource_type, amount) VALUES ({group_id}, {faction_type}, {resource_type}, 0)"
            cursor.execute(sql)
            conn.commit()
            amount = 0
        else:
            amount = result[0]
        
        # 更新内存中的记录
        if group_id not in faction_resource_pools:
            faction_resource_pools[group_id] = {}
        if faction_type not in faction_resource_pools[group_id]:
            faction_resource_pools[group_id][faction_type] = {}
        faction_resource_pools[group_id][faction_type][resource_type] = amount
        
        return amount
    finally:
        if conn:
            db_pool.return_connection(conn)

def update_faction_resource_pool(group_id: int, faction_type: int, resource_type: int, amount: int) -> None:
    """更新阵营资源池中的资源数量"""
    # 获取当前资源数量
    current_amount = get_faction_resource_pool(group_id, faction_type, resource_type)
    new_amount = max(0, current_amount + amount)  # 确保资源不会为负
    
    # 更新数据库
    init_faction_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        sql = f"UPDATE faction_resource_pools SET amount={new_amount} WHERE belonging_group={group_id} AND faction_type={faction_type} AND resource_type={resource_type}"
        cursor.execute(sql)
        conn.commit()
        
        # 更新内存中的记录
        if group_id not in faction_resource_pools:
            faction_resource_pools[group_id] = {}
        if faction_type not in faction_resource_pools[group_id]:
            faction_resource_pools[group_id][faction_type] = {}
        faction_resource_pools[group_id][faction_type][resource_type] = new_amount
    finally:
        if conn:
            db_pool.return_connection(conn)

def contribute_to_faction_pool(group_id: int, user_id: int, resource_type: int, amount: int) -> str:
    """向阵营资源池贡献资源"""
    # 获取用户阵营
    faction_type = get_user_faction(group_id, user_id)
    if faction_type == FACTION_NONE:
        return "你不属于任何阵营，无法贡献资源！"
    
    # 检查用户资源是否足够
    user_resource = get_user_resource(group_id, user_id, resource_type)
    if user_resource < amount:
        return "你的资源不足！"
    
    # 扣除用户资源
    update_user_resource(group_id, user_id, resource_type, -amount)
    
    # 增加阵营资源池
    update_faction_resource_pool(group_id, faction_type, resource_type, amount)
    
    # 获取资源名称
    resource_name = "食物" if resource_type == RESOURCE_FOOD else "木材" if resource_type == RESOURCE_WOOD else "矿石"
    
    return f"你成功向{FACTION_NAMES[faction_type]}资源池贡献了{amount}单位{resource_name}！"

def withdraw_from_faction_pool(group_id: int, user_id: int, resource_type: int, amount: int) -> str:
    """从阵营资源池提取资源"""
    # 获取用户阵营
    faction_type = get_user_faction(group_id, user_id)
    if faction_type == FACTION_NONE:
        return "你不属于任何阵营，无法提取资源！"
    
    # 检查阵营资源池是否足够
    pool_resource = get_faction_resource_pool(group_id, faction_type, resource_type)
    if pool_resource < amount:
        return "阵营资源池中的资源不足！"
    
    # 从阵营资源池扣除
    update_faction_resource_pool(group_id, faction_type, resource_type, -amount)
    
    # 增加用户资源
    update_user_resource(group_id, user_id, resource_type, amount)
    
    # 获取资源名称
    resource_name = "食物" if resource_type == RESOURCE_FOOD else "木材" if resource_type == RESOURCE_WOOD else "矿石"
    
    return f"你成功从{FACTION_NAMES[faction_type]}资源池提取了{amount}单位{resource_name}！"

def get_faction_resource_pool_info(group_id: int, faction_type: int) -> str:
    """获取阵营资源池信息"""
    if faction_type == FACTION_NONE:
        return "无效的阵营类型！"
    
    # 获取各类资源数量
    food_amount = get_faction_resource_pool(group_id, faction_type, RESOURCE_FOOD)
    wood_amount = get_faction_resource_pool(group_id, faction_type, RESOURCE_WOOD)
    ore_amount = get_faction_resource_pool(group_id, faction_type, RESOURCE_ORE)
    
    # 生成资源池信息
    info = f"===== {FACTION_NAMES[faction_type]}资源池 =====\n"
    info += f"食物：{food_amount}单位\n"
    info += f"木材：{wood_amount}单位\n"
    info += f"矿石：{ore_amount}单位\n"
    
    return info

def start_faction_war(group_id: int, attacker_id: int, defender_faction: int) -> str:
    """发起阵营战争"""
    # 获取攻击者阵营
    attacker_faction = get_user_faction(group_id, attacker_id)
    if attacker_faction == FACTION_NONE:
        return "你不属于任何阵营，无法发起战争！"
    
    # 检查防御方阵营是否有效
    if defender_faction not in [FACTION_WATER, FACTION_DEMON] or defender_faction == attacker_faction:
        return "无效的目标阵营！"
    
    # 检查是否已有战争进行中
    if group_id in faction_wars:
        war_info = faction_wars[group_id]
        current_time = time.time()
        if "end_time" in war_info and current_time < war_info["end_time"]:
            attacker_name = FACTION_NAMES[war_info["attacker"]]
            defender_name = FACTION_NAMES[war_info["defender"]]
            remaining_time = int(war_info["end_time"] - current_time)
            return f"当前已有战争进行中！{attacker_name}正在攻打{defender_name}，还有{remaining_time}秒结束。"
    
    # 获取攻击方成员数量
    attacker_members = get_faction_members(group_id, attacker_faction)
    if len(attacker_members) < 3:
        return "发起战争需要至少3名阵营成员！"
    
    # 获取防御方成员数量
    defender_members = get_faction_members(group_id, defender_faction)
    if len(defender_members) < 3:
        return "目标阵营成员不足3人，无法发起战争！"
    
    # 设置战争状态
    current_time = time.time()
    war_duration = 3600  # 战争持续1小时
    faction_wars[group_id] = {
        "attacker": attacker_faction,
        "defender": defender_faction,
        "start_time": current_time,
        "end_time": current_time + war_duration
    }
    
    # 返回战争开始信息
    attacker_name = FACTION_NAMES[attacker_faction]
    defender_name = FACTION_NAMES[defender_faction]
    return f"{attacker_name}向{defender_name}发起了战争！战争将持续1小时，结束后将随机抢夺对方1%~15%的某种资源。"

def end_faction_war(group_id: int) -> str:
    """结束阵营战争并结算"""
    if group_id not in faction_wars:
        return "当前没有进行中的战争！"
    
    war_info = faction_wars[group_id]
    current_time = time.time()
    
    # 检查战争是否已结束
    if current_time < war_info["end_time"]:
        remaining_time = int(war_info["end_time"] - current_time)
        return f"战争尚未结束，还有{remaining_time}秒。"
    
    attacker_faction = war_info["attacker"]
    defender_faction = war_info["defender"]
    
    # 随机决定胜负（50%概率）
    attacker_wins = random.random() < 0.5
    
    # 确定胜利方和失败方
    winner_faction = attacker_faction if attacker_wins else defender_faction
    loser_faction = defender_faction if attacker_wins else attacker_faction
    
    # 随机选择一种资源
    resource_type = random.choice([RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE])
    
    # 获取失败方资源池中的资源数量
    loser_resource = get_faction_resource_pool(group_id, loser_faction, resource_type)
    
    # 计算抢夺的资源数量（1%~15%）
    steal_percentage = random.uniform(0.01, 0.15)
    steal_amount = int(loser_resource * steal_percentage)
    
    if steal_amount > 0:
        # 从失败方资源池中扣除
        update_faction_resource_pool(group_id, loser_faction, resource_type, -steal_amount)
        
        # 增加胜利方资源池
        update_faction_resource_pool(group_id, winner_faction, resource_type, steal_amount)
        
        # 记录战争结果
        init_faction_db()
        conn = None
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            
            today = datetime.date.today().isoformat()
            sql = f"INSERT INTO faction_war_records (belonging_group, attacker_faction, defender_faction, resource_type, amount, war_date) VALUES ({group_id}, {attacker_faction}, {defender_faction}, {resource_type}, {steal_amount}, '{today}')"
            cursor.execute(sql)
            conn.commit()
        finally:
            if conn:
                conn.close()
    
    # 清除战争状态
    del faction_wars[group_id]
    
    # 获取资源名称
    resource_name = "食物" if resource_type == RESOURCE_FOOD else "木材" if resource_type == RESOURCE_WOOD else "矿石"
    
    # 返回战争结果
    winner_name = FACTION_NAMES[winner_faction]
    loser_name = FACTION_NAMES[loser_faction]
    
    if steal_amount > 0:
        return f"战争结束！{winner_name}战胜了{loser_name}，抢夺了{steal_amount}单位{resource_name}！"
    else:
        return f"战争结束！{winner_name}战胜了{loser_faction}，但没有抢到任何资源。"

def check_war_status(group_id: int) -> str:
    """检查战争状态"""
    if group_id not in faction_wars:
        return "当前没有进行中的战争。"
    
    war_info = faction_wars[group_id]
    current_time = time.time()
    
    if current_time >= war_info["end_time"]:
        # 战争已结束，进行结算
        return end_faction_war(group_id)
    
    # 战争仍在进行中
    attacker_name = FACTION_NAMES[war_info["attacker"]]
    defender_name = FACTION_NAMES[war_info["defender"]]
    remaining_time = int(war_info["end_time"] - current_time)
    return f"当前战争：{attacker_name}正在攻打{defender_name}，还有{remaining_time}秒结束。"

def start_embargo_vote(group_id: int, user_id: int, target_faction: int, resource_type: int) -> str:
    """发起贸易禁运投票"""
    # 获取用户阵营
    faction_type = get_user_faction(group_id, user_id)
    if faction_type == FACTION_NONE:
        return "你不属于任何阵营，无法发起禁运投票！"
    
    # 检查目标阵营是否有效
    if target_faction not in [FACTION_WATER, FACTION_DEMON] or target_faction == faction_type:
        return "无效的目标阵营！"
    
    # 检查资源类型是否有效
    if resource_type not in [RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE]:
        return "无效的资源类型！"
    
    # 检查是否已有该禁运投票进行中
    if group_id in faction_votes and faction_type in faction_votes[group_id]:
        vote_info = faction_votes[group_id][faction_type]
        if vote_info["vote_type"] == "embargo" and vote_info["target"] == target_faction and vote_info["resource"] == resource_type:
            return "该禁运投票已在进行中！"
    
    # 初始化投票
    if group_id not in faction_votes:
        faction_votes[group_id] = {}
    faction_votes[group_id][faction_type] = {
        "vote_type": "embargo",
        "target": target_faction,
        "resource": resource_type,
        "votes": {user_id: True}  # 发起人默认投赞成票
    }
    
    # 获取资源名称
    resource_name = "食物" if resource_type == RESOURCE_FOOD else "木材" if resource_type == RESOURCE_WOOD else "矿石"
    
    # 返回投票开始信息
    target_name = FACTION_NAMES[target_faction]
    return f"你发起了对{target_name}的{resource_name}贸易禁运投票！需要至少半数阵营成员同意才能通过。"

def vote_for_embargo(group_id: int, user_id: int, vote: bool) -> str:
    """对贸易禁运投票"""
    # 获取用户阵营
    faction_type = get_user_faction(group_id, user_id)
    if faction_type == FACTION_NONE:
        return "你不属于任何阵营，无法参与投票！"
    
    # 检查是否有投票进行中
    if group_id not in faction_votes or faction_type not in faction_votes[group_id]:
        return "当前没有进行中的投票！"
    
    vote_info = faction_votes[group_id][faction_type]
    if vote_info["vote_type"] != "embargo":
        return "当前没有进行中的禁运投票！"
    
    # 记录投票
    vote_info["votes"][user_id] = vote
    
    # 检查投票是否已达到半数
    faction_members = get_faction_members(group_id, faction_type)
    votes_needed = len(faction_members) // 2 + 1
    
    yes_votes = sum(1 for v in vote_info["votes"].values() if v)
    
    if yes_votes >= votes_needed:
        # 投票通过，实施禁运
        target_faction = vote_info["target"]
        resource_type = vote_info["resource"]
        
        # 记录禁运
        if group_id not in trade_embargoes:
            trade_embargoes[group_id] = {}
        if faction_type not in trade_embargoes[group_id]:
            trade_embargoes[group_id][faction_type] = {}
        if target_faction not in trade_embargoes[group_id][faction_type]:
            trade_embargoes[group_id][faction_type][target_faction] = []
        
        if resource_type not in trade_embargoes[group_id][faction_type][target_faction]:
            trade_embargoes[group_id][faction_type][target_faction].append(resource_type)
        
        # 记录到数据库
        init_faction_db()
        conn = None
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            
            today = datetime.date.today().isoformat()
            sql = f"INSERT OR REPLACE INTO trade_embargoes (belonging_group, faction_type, target_faction, resource_type, start_date) VALUES ({group_id}, {faction_type}, {target_faction}, {resource_type}, '{today}')"
            cursor.execute(sql)
            conn.commit()
        finally:
            if conn:
                conn.close()
        
        # 清除投票
        del faction_votes[group_id][faction_type]
        
        # 获取资源名称
        resource_name = "食物" if resource_type == RESOURCE_FOOD else "木材" if resource_type == RESOURCE_WOOD else "矿石"
        
        # 返回禁运实施信息
        target_name = FACTION_NAMES[target_faction]
        return f"投票通过！你们阵营已对{target_name}实施{resource_name}贸易禁运。"
    
    return f"投票已记录！当前赞成票数：{yes_votes}/{votes_needed}"

def check_embargo(group_id: int, seller_faction: int, buyer_faction: int, resource_type: int) -> bool:
    """检查是否存在贸易禁运"""
    # 检查内存中是否有记录
    if group_id in trade_embargoes and seller_faction in trade_embargoes[group_id] and buyer_faction in trade_embargoes[group_id][seller_faction]:
        if resource_type in trade_embargoes[group_id][seller_faction][buyer_faction]:
            return True
    
    # 从数据库中查询
    init_faction_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        sql = f"SELECT id FROM trade_embargoes WHERE belonging_group={group_id} AND faction_type={seller_faction} AND target_faction={buyer_faction} AND resource_type={resource_type}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        embargo_exists = result is not None
    finally:
        if conn:
            db_pool.return_connection(conn)
    
    # 更新内存中的记录
    if embargo_exists:
        if group_id not in trade_embargoes:
            trade_embargoes[group_id] = {}
        if seller_faction not in trade_embargoes[group_id]:
            trade_embargoes[group_id][seller_faction] = {}
        if buyer_faction not in trade_embargoes[group_id][seller_faction]:
            trade_embargoes[group_id][seller_faction][buyer_faction] = []
        if resource_type not in trade_embargoes[group_id][seller_faction][buyer_faction]:
            trade_embargoes[group_id][seller_faction][buyer_faction].append(resource_type)
    
    return embargo_exists

def lift_embargo(group_id: int, user_id: int, target_faction: int, resource_type: int) -> str:
    """解除贸易禁运"""
    # 获取用户阵营
    faction_type = get_user_faction(group_id, user_id)
    if faction_type == FACTION_NONE:
        return "你不属于任何阵营，无法解除禁运！"
    
    # 检查目标阵营是否有效
    if target_faction not in [FACTION_WATER, FACTION_DEMON] or target_faction == faction_type:
        return "无效的目标阵营！"
    
    # 检查资源类型是否有效
    if resource_type not in [RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE]:
        return "无效的资源类型！"
    
    # 检查是否存在禁运
    if not check_embargo(group_id, faction_type, target_faction, resource_type):
        return "不存在该贸易禁运！"
    
    # 从数据库中删除禁运记录
    init_faction_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        sql = f"DELETE FROM trade_embargoes WHERE belonging_group={group_id} AND faction_type={faction_type} AND target_faction={target_faction} AND resource_type={resource_type}"
        cursor.execute(sql)
        conn.commit()
    finally:
        if conn:
            db_pool.return_connection(conn)
    
    # 更新内存中的记录
    if group_id in trade_embargoes and faction_type in trade_embargoes[group_id] and target_faction in trade_embargoes[group_id][faction_type]:
        if resource_type in trade_embargoes[group_id][faction_type][target_faction]:
            trade_embargoes[group_id][faction_type][target_faction].remove(resource_type)
    
    # 获取资源名称
    resource_name = "食物" if resource_type == RESOURCE_FOOD else "木材" if resource_type == RESOURCE_WOOD else "矿石"
    
    # 返回解除禁运信息
    target_name = FACTION_NAMES[target_faction]
    return f"你已解除对{target_name}的{resource_name}贸易禁运！"

def get_embargoes_info(group_id: int, faction_type: int) -> str:
    """获取阵营实施的贸易禁运信息"""
    if faction_type == FACTION_NONE:
        return "无效的阵营类型！"
    
    # 从数据库中查询禁运记录
    init_faction_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        sql = f"SELECT target_faction, resource_type FROM trade_embargoes WHERE belonging_group={group_id} AND faction_type={faction_type}"
        cursor.execute(sql)
        results = cursor.fetchall()
    finally:
        if conn:
            db_pool.return_connection(conn)
    
    if not results:
        return f"{FACTION_NAMES[faction_type]}当前没有实施任何贸易禁运。"
    
    # 整理禁运信息
    embargoes = {}
    for target_faction, resource_type in results:
        if target_faction not in embargoes:
            embargoes[target_faction] = []
        embargoes[target_faction].append(resource_type)
    
    # 生成禁运信息
    info = f"===== {FACTION_NAMES[faction_type]}实施的贸易禁运 =====\n"
    for target_faction, resource_types in embargoes.items():
        target_name = FACTION_NAMES[target_faction]
        info += f"对{target_name}的禁运：\n"
        
        for resource_type in resource_types:
            resource_name = "食物" if resource_type == RESOURCE_FOOD else "木材" if resource_type == RESOURCE_WOOD else "矿石"
            info += f"- {resource_name}\n"
    
    return info

def produce_special_resource(group_id: int, user_id: int) -> str:
    """产出阵营特殊资源"""
    # 获取用户阵营
    faction_type = get_user_faction(group_id, user_id)
    if faction_type == FACTION_NONE:
        return "你不属于任何阵营，无法产出特殊资源！"
    
    # 检查CD
    current_time = time.time()
    if (group_id, user_id) in special_resource_cd:
        end_time = special_resource_cd[(group_id, user_id)]
        if current_time < end_time:
            remaining_time = int(end_time - current_time)
            minutes = remaining_time // 60
            seconds = remaining_time % 60
            return f"特殊资源产出CD中，还需等待{minutes}分{seconds}秒。"
    
    # 从数据库中查询CD
    init_faction_db()
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        sql = f"SELECT end_time FROM special_resource_cd WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result:
            end_time = datetime.datetime.fromisoformat(result[0]).timestamp()
            if current_time < end_time:
                remaining_time = int(end_time - current_time)
                minutes = remaining_time // 60
                seconds = remaining_time % 60
                
                # 更新内存中的CD记录
                special_resource_cd[(group_id, user_id)] = end_time
                
                return f"特殊资源产出CD中，还需等待{minutes}分{seconds}秒。"
        
        # 确定特殊资源类型
        special_resource_type = FACTION_SPECIAL_RESOURCES[faction_type]
        
        # 随机产出数量（1~3）
        amount = random.randint(1, 3)
        
        # 更新用户特殊资源
        from .profession import update_special_resource, get_special_resource
        current_amount = get_special_resource(group_id, user_id, special_resource_type)
        update_special_resource(group_id, user_id, special_resource_type, amount)
        
        # 设置CD（12小时）
        cd_duration = 12 * 3600
        end_time = current_time + cd_duration
        end_time_dt = datetime.datetime.fromtimestamp(end_time)
        
        # 更新数据库中的CD记录
        sql = f"INSERT OR REPLACE INTO special_resource_cd (uid, belonging_group, end_time) VALUES ({user_id}, {group_id}, '{end_time_dt.isoformat()}')"
        cursor.execute(sql)
        conn.commit()
        
        # 更新内存中的CD记录
        special_resource_cd[(group_id, user_id)] = end_time
    finally:
        if conn:
            db_pool.return_connection(conn)
    
    # 获取特殊资源名称
    resource_name = "海蓝宝石" if special_resource_type == SPECIAL_BLUE_GEM else "恶魔树枝干"
    
    return f"你成功产出了{amount}个{resource_name}！当前拥有：{current_amount + amount}个。\n特殊资源产出进入CD，12小时后可再次产出。"

def get_user_faction_info(group_id: int, user_id: int) -> str:
    """获取用户的阵营信息"""
    # 获取用户阵营
    faction_type = get_user_faction(group_id, user_id)
    
    if faction_type == FACTION_NONE:
        return "你目前不属于任何阵营！\n可用的阵营有：\n- 水水军：可以产出海蓝宝石\n- 魔王军：可以产出恶魔树枝干\n\n注意：一旦加入阵营不可切换，请慎重选择！"
    
    # 获取阵营名称和特殊资源
    faction_name = FACTION_NAMES[faction_type]
    special_resource_type = FACTION_SPECIAL_RESOURCES[faction_type]
    special_resource_name = "海蓝宝石" if special_resource_type == SPECIAL_BLUE_GEM else "恶魔树枝干"
    
    # 获取阵营成员数量
    members = get_faction_members(group_id, faction_type)
    
    # 生成阵营信息
    info = f"===== {faction_name} =====\n"
    info += f"成员数量：{len(members)}\n"
    info += f"特殊资源：{special_resource_name}\n\n"
    
    # 添加阵营特权信息
    info += "阵营特权：\n"
    info += f"- 可以产出特殊资源：{special_resource_name}\n"
    info += "- 可以参与阵营资源池共享\n"
    info += "- 可以参与阵营战争和贸易禁运\n"
    
    # 检查特殊资源CD
    current_time = time.time()
    cd_info = "\n特殊资源产出状态："
    
    if (group_id, user_id) in special_resource_cd:
        end_time = special_resource_cd[(group_id, user_id)]
        if current_time < end_time:
            remaining_time = int(end_time - current_time)
            hours = remaining_time // 3600
            minutes = (remaining_time % 3600) // 60
            cd_info += f"CD中，还需等待{hours}小时{minutes}分钟"
        else:
            cd_info += "可以产出"
    else:
        # 从数据库中查询CD
        init_faction_db()
        conn = None
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            
            sql = f"SELECT end_time FROM special_resource_cd WHERE uid={user_id} AND belonging_group={group_id}"
            cursor.execute(sql)
            result = cursor.fetchone()
            
            if result:
                end_time = datetime.datetime.fromisoformat(result[0]).timestamp()
                if current_time < end_time:
                    remaining_time = int(end_time - current_time)
                    hours = remaining_time // 3600
                    minutes = (remaining_time % 3600) // 60
                    cd_info += f"CD中，还需等待{hours}小时{minutes}分钟"
                    
                    # 更新内存中的CD记录
                    special_resource_cd[(group_id, user_id)] = end_time
                else:
                    cd_info += "可以产出"
            else:
                cd_info += "可以产出"
        finally:
            if conn:
                conn.close()
    
    info += cd_info
    
    return info