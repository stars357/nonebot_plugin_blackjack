import sqlite3
import datetime
import random
import time
from typing import Dict, List, Tuple, Optional, Union

from .resource import get_user_resource, get_user_stamina, produce_resource, update_user_resource, update_user_stamina
from .sign import get_point, update_point
from .common import (
    RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE,
    TOOL_IRON, TOOL_FINE_GOLD, TOOL_ALLOY, TOOL_ALLOY_PERM,
    TOOL_TYPE_PICKAXE, TOOL_TYPE_HOE, TOOL_TYPE_AXE,
    PROF_NONE, PROF_WORKER, PROF_MINER, PROF_FARMER, PROF_LUMBERJACK, PROF_BLACKSMITH,
    SPECIAL_BLUE_GEM, SPECIAL_SUPER_PLANT, SPECIAL_DEMON_BRANCH,
    TOOL_DURABILITY, MAX_STAMINA, RESOURCE_STAMINA_COST, RESOURCE_OUTPUT
)

# 工具制作材料
TOOL_CRAFTING_MATERIALS = {
    TOOL_IRON: {RESOURCE_ORE: 30, RESOURCE_WOOD: 10},
    TOOL_FINE_GOLD: {RESOURCE_ORE: 120, RESOURCE_WOOD: 60},
    TOOL_ALLOY: {RESOURCE_ORE: 600, RESOURCE_WOOD: 240, SPECIAL_DEMON_BRANCH: 1, SPECIAL_BLUE_GEM: 1},
    TOOL_ALLOY_PERM: {SPECIAL_BLUE_GEM: 25, SPECIAL_DEMON_BRANCH: 25}  # 升级材料
}

# 职业切换CD字典 {(group_id, user_id): next_change_time}
profession_change_cd: Dict[Tuple[int, int], datetime.datetime] = {}

# 打工状态字典 {(group_id, user_id): {"start_time": timestamp, "hourly_wage": int}}
working_status: Dict[Tuple[int, int], Dict] = {}

# 动态导入函数，避免循环导入
def get_resource_functions():
    """动态导入resource模块中的函数"""
    from . import resource
    return {
        'get_user_resource': resource.get_user_resource,
        'update_user_resource': resource.update_user_resource,
        'get_user_stamina': resource.get_user_stamina,
        'update_user_stamina': resource.update_user_stamina,
        'check_resource_cd': resource.check_resource_cd,
        'set_resource_cd': resource.set_resource_cd
    }

def init_profession_db():
    """初始化职业系统数据库"""
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 创建用户职业表
    sql = """
    CREATE TABLE IF NOT EXISTS user_profession (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        profession INTEGER NOT NULL DEFAULT -1,  -- -1: 无职业, 0: 牛马, 1: 矿工, 2: 农夫, 3: 伐木工, 4: 铁匠
        last_change_date DATE,                  -- 上次更换职业的日期
        working_hours INTEGER DEFAULT 0,        -- 打工累计小时数（仅牛马职业）
        hourly_wage INTEGER DEFAULT 10,         -- 每小时工资（仅牛马职业）
        UNIQUE(uid, belonging_group)
    )
    """
    cursor.execute(sql)
    
    # 创建用户工具表（扩展现有表，添加耐久度）
    sql = """
    CREATE TABLE IF NOT EXISTS user_tool_durability (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        tool_type INTEGER NOT NULL,  -- 0: 铁质工具, 1: 精金工具, 2: 强化合金工具, 3: 强化合金工具【不毁】
        tool_category INTEGER NOT NULL, -- 0: 镐, 1: 锄, 2: 斧
        durability INTEGER NOT NULL,  -- 剩余耐久度
        UNIQUE(uid, belonging_group, tool_type, tool_category)
    )
    """
    cursor.execute(sql)
    
    # 创建特殊资源表
    sql = """
    CREATE TABLE IF NOT EXISTS special_resources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        resource_type INTEGER NOT NULL,  -- 0: 海蓝宝石, 1: 超级植株, 2: 恶魔树枝干
        amount INTEGER NOT NULL DEFAULT 0,
        UNIQUE(uid, belonging_group, resource_type)
    )
    """
    cursor.execute(sql)
    
    # 创建职业切换CD表
    sql = """
    CREATE TABLE IF NOT EXISTS profession_change_cd (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        next_change_date DATE NOT NULL,
        UNIQUE(uid, belonging_group)
    )
    """
    cursor.execute(sql)
    
    # 创建打工状态表
    sql = """
    CREATE TABLE IF NOT EXISTS working_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        start_time TIMESTAMP NOT NULL,
        hourly_wage INTEGER NOT NULL,
        UNIQUE(uid, belonging_group)
    )
    """
    cursor.execute(sql)
    
    conn.commit()
    cursor.close()
    conn.close()

def get_user_profession(group_id: int, user_id: int) -> int:
    """获取用户职业"""
    init_profession_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT profession FROM user_profession WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 创建新记录，默认无职业
        sql = f"INSERT INTO user_profession (uid, belonging_group, profession) VALUES ({user_id}, {group_id}, {PROF_NONE})"
        cursor.execute(sql)
        conn.commit()
        profession = PROF_NONE
    else:
        profession = result[0]
    
    cursor.close()
    conn.close()
    return profession

def check_profession_change_cd(group_id: int, user_id: int) -> Tuple[bool, str]:
    """检查职业切换CD"""
    # 先检查内存中是否有记录
    if (group_id, user_id) in profession_change_cd:
        next_change_time = profession_change_cd[(group_id, user_id)]
        if datetime.datetime.now() < next_change_time:
            days_remaining = (next_change_time.date() - datetime.datetime.now().date()).days
            return False, f"职业切换CD中，还需等待{days_remaining}天"
        else:
            # CD已结束，删除记录
            del profession_change_cd[(group_id, user_id)]
            return True, ""
    
    # 检查数据库
    init_profession_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT next_change_date FROM profession_change_cd WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 没有CD记录
        cursor.close()
        conn.close()
        return True, ""
    else:
        next_change_date = datetime.datetime.strptime(result[0], "%Y-%m-%d").date()
        today = datetime.datetime.now().date()
        
        if today < next_change_date:
            # 仍在CD期内
            days_remaining = (next_change_date - today).days
            
            # 更新内存记录
            next_change_time = datetime.datetime.combine(next_change_date, datetime.time())
            profession_change_cd[(group_id, user_id)] = next_change_time
            
            cursor.close()
            conn.close()
            return False, f"职业切换CD中，还需等待{days_remaining}天"
        else:
            # CD已结束，删除记录
            sql = f"DELETE FROM profession_change_cd WHERE uid={user_id} AND belonging_group={group_id}"
            cursor.execute(sql)
            conn.commit()
            cursor.close()
            conn.close()
            return True, ""

def set_profession_change_cd(group_id: int, user_id: int) -> None:
    """设置职业切换CD（15天）"""
    # 计算下次可切换职业的日期
    next_change_date = datetime.datetime.now().date() + datetime.timedelta(days=15)
    next_change_time = datetime.datetime.combine(next_change_date, datetime.time())
    
    # 更新内存记录
    profession_change_cd[(group_id, user_id)] = next_change_time
    
    # 更新数据库
    init_profession_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT id FROM profession_change_cd WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 创建新记录
        sql = f"INSERT INTO profession_change_cd (uid, belonging_group, next_change_date) VALUES ({user_id}, {group_id}, '{next_change_date.isoformat()}')"
    else:
        # 更新记录
        sql = f"UPDATE profession_change_cd SET next_change_date='{next_change_date.isoformat()}' WHERE uid={user_id} AND belonging_group={group_id}"
    
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()

def change_profession(group_id: int, user_id: int, new_profession: int) -> str:
    """切换职业"""
    # 检查职业类型是否有效
    if new_profession not in [PROF_WORKER, PROF_MINER, PROF_FARMER, PROF_LUMBERJACK, PROF_BLACKSMITH]:
        return "无效的职业类型"
    
    # 获取当前职业
    current_profession = get_user_profession(group_id, user_id)
    
    # 如果已经是该职业，无需切换
    if current_profession == new_profession:
        profession_names = ["牛马", "矿工", "农夫", "伐木工", "铁匠"]
        return f"你已经是{profession_names[new_profession]}了，无需切换"
    
    # 检查CD
    allowed, message = check_profession_change_cd(group_id, user_id)
    if not allowed:
        return message
    
    # 更新职业
    init_profession_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    today = datetime.datetime.now().date().isoformat()
    
    if current_profession == PROF_NONE:
        # 首次选择职业，不设置CD
        sql = f"UPDATE user_profession SET profession={new_profession}, last_change_date='{today}' WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        conn.commit()
    else:
        # 切换职业，设置CD
        sql = f"UPDATE user_profession SET profession={new_profession}, last_change_date='{today}' WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        conn.commit()
        set_profession_change_cd(group_id, user_id)
    
    cursor.close()
    conn.close()
    
    # 如果从牛马职业切换出来，结束打工状态
    if current_profession == PROF_WORKER:
        end_working(group_id, user_id)
    
    # 构建回复消息
    profession_names = ["牛马", "矿工", "农夫", "伐木工", "铁匠"]
    message = f"职业切换成功！你现在的职业是：{profession_names[new_profession]}"
    
    if current_profession != PROF_NONE:
        message += "\n职业切换CD已生效，15天内无法再次切换职业"
    
    return message

def get_special_resource(group_id: int, user_id: int, resource_type: int) -> int:
    """获取特殊资源数量"""
    init_profession_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT amount FROM special_resources WHERE uid={user_id} AND belonging_group={group_id} AND resource_type={resource_type}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 创建新记录
        sql = f"INSERT INTO special_resources (uid, belonging_group, resource_type, amount) VALUES ({user_id}, {group_id}, {resource_type}, 0)"
        cursor.execute(sql)
        conn.commit()
        amount = 0
    else:
        amount = result[0]
    
    cursor.close()
    conn.close()
    return amount

def update_special_resource(group_id: int, user_id: int, resource_type: int, amount: int) -> None:
    """更新特殊资源数量"""
    init_profession_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 确保资源数量不为负
    amount = max(0, amount)
    
    sql = f"SELECT id FROM special_resources WHERE uid={user_id} AND belonging_group={group_id} AND resource_type={resource_type}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 创建新记录
        sql = f"INSERT INTO special_resources (uid, belonging_group, resource_type, amount) VALUES ({user_id}, {group_id}, {resource_type}, {amount})"
    else:
        # 更新记录
        sql = f"UPDATE special_resources SET amount={amount} WHERE uid={user_id} AND belonging_group={group_id} AND resource_type={resource_type}"
    
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()

def get_tool_durability(group_id: int, user_id: int, tool_type: int, tool_category: int) -> int:
    """获取工具耐久度"""
    init_profession_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT durability FROM user_tool_durability WHERE uid={user_id} AND belonging_group={group_id} AND tool_type={tool_type} AND tool_category={tool_category}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 没有该工具
        durability = 0
    else:
        durability = result[0]
    
    cursor.close()
    conn.close()
    return durability

def update_tool_durability(group_id: int, user_id: int, tool_type: int, tool_category: int, durability: int) -> None:
    """更新工具耐久度"""
    init_profession_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 确保耐久度不为负（除非是无限耐久的工具）
    if tool_type != TOOL_ALLOY_PERM:
        durability = max(0, durability)
    
    sql = f"SELECT id FROM user_tool_durability WHERE uid={user_id} AND belonging_group={group_id} AND tool_type={tool_type} AND tool_category={tool_category}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None and durability > 0:
        # 创建新记录
        sql = f"INSERT INTO user_tool_durability (uid, belonging_group, tool_type, tool_category, durability) VALUES ({user_id}, {group_id}, {tool_type}, {tool_category}, {durability})"
        cursor.execute(sql)
    elif result is not None:
        if durability <= 0:
            # 删除记录
            sql = f"DELETE FROM user_tool_durability WHERE uid={user_id} AND belonging_group={group_id} AND tool_type={tool_type} AND tool_category={tool_category}"
        else:
            # 更新记录
            sql = f"UPDATE user_tool_durability SET durability={durability} WHERE uid={user_id} AND belonging_group={group_id} AND tool_type={tool_type} AND tool_category={tool_category}"
        cursor.execute(sql)
    
    conn.commit()
    cursor.close()
    conn.close()

def get_best_tool(group_id: int, user_id: int, tool_category: int) -> Tuple[int, int]:
    """获取用户最好的工具及其耐久度"""
    # 按优先级检查工具（从高级到低级）
    for tool_type in [TOOL_ALLOY_PERM, TOOL_ALLOY, TOOL_FINE_GOLD, TOOL_IRON]:
        durability = get_tool_durability(group_id, user_id, tool_type, tool_category)
        if durability > 0 or tool_type == TOOL_ALLOY_PERM and durability == -1:
            return tool_type, durability
    
    # 没有工具
    return -1, 0

def get_equipped_tool_info(group_id: int, user_id: int, tool_category: int) -> Tuple[int, int]:
    """获取用户装备的工具及其耐久度"""
    # 导入装备模块
    from .equipment import get_equipped_tool
    
    # 获取装备的工具类型
    tool_type = get_equipped_tool(group_id, user_id, tool_category)
    
    # 如果没有装备工具，返回-1
    if tool_type == -1:
        return -1, 0
    
    # 获取工具耐久度
    durability = get_tool_durability(group_id, user_id, tool_type, tool_category)
    
    # 检查耐久度是否有效
    if durability <= 0 and not (tool_type == TOOL_ALLOY_PERM and durability == -1):
        # 工具已损坏或不存在，清除装备状态
        from .equipment import unequip_tool
        unequip_tool(group_id, user_id, tool_category)
        return -1, 0
    
    return tool_type, durability

def use_tool(group_id: int, user_id: int, tool_category: int) -> Tuple[int, bool]:
    """使用工具，返回工具类型和是否成功"""
    # 获取装备的工具
    tool_type, durability = get_equipped_tool_info(group_id, user_id, tool_category)
    
    if tool_type == -1:
        # 没有装备工具
        return -1, False
    
    # 使用工具（减少耐久度）
    if tool_type != TOOL_ALLOY_PERM:  # 不毁版不减耐久
        durability -= 1
        update_tool_durability(group_id, user_id, tool_type, tool_category, durability)
    
    return tool_type, True

def start_working(group_id: int, user_id: int) -> str:
    """开始打工（牛马职业）"""
    # 检查职业
    profession = get_user_profession(group_id, user_id)
    if profession != PROF_WORKER:
        return "只有牛马职业才能打工"
    
    # 检查是否已经在打工
    if (group_id, user_id) in working_status:
        return "你已经在打工了，使用 结束打工 命令来结束打工并领取工资"
    
    # 获取每小时工资
    init_profession_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT working_hours, hourly_wage FROM user_profession WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    working_hours = result[0] if result else 0
    hourly_wage = result[1] if result else 10
    
    # 记录打工开始时间
    start_time = time.time()
    working_status[(group_id, user_id)] = {"start_time": start_time, "hourly_wage": hourly_wage}
    
    # 更新数据库
    sql = f"INSERT OR REPLACE INTO working_status (uid, belonging_group, start_time, hourly_wage) VALUES ({user_id}, {group_id}, '{datetime.datetime.now().isoformat()}', {hourly_wage})"
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()
    
    return f"开始打工！当前时薪：{hourly_wage}金币/小时\n累计打工时长：{working_hours}小时"

def end_working(group_id: int, user_id: int) -> str:
    """结束打工并领取工资"""
    # 检查是否在打工
    if (group_id, user_id) not in working_status:
        # 检查数据库
        init_profession_db()
        conn = sqlite3.connect("identifier.sqlite")
        cursor = conn.cursor()
        
        sql = f"SELECT start_time, hourly_wage FROM working_status WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            cursor.close()
            conn.close()
            return "你没有在打工"
        
        # 恢复打工状态
        start_time = datetime.datetime.fromisoformat(result[0]).timestamp()
        hourly_wage = result[1]
        working_status[(group_id, user_id)] = {"start_time": start_time, "hourly_wage": hourly_wage}
        
        cursor.close()
        conn.close()
    
    # 计算打工时长和工资
    start_time = working_status[(group_id, user_id)]["start_time"]
    hourly_wage = working_status[(group_id, user_id)]["hourly_wage"]
    
    current_time = time.time()
    hours_worked = (current_time - start_time) / 3600  # 转换为小时
    
    # 向下取整小时数
    hours_worked_int = int(hours_worked)
    
    # 计算工资
    wage = hours_worked_int * hourly_wage
    
    # 更新用户金币
    user_coins = get_point(group_id, user_id)
    update_point(group_id, user_id, user_coins + wage)
    
    # 更新累计打工时长
    init_profession_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT working_hours FROM user_profession WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    total_working_hours = (result[0] if result else 0) + hours_worked_int
    
    # 计算新的时薪（每满48小时上涨25%，最多上涨20次）
    old_wage_level = (result[0] if result else 0) // 48
    new_wage_level = total_working_hours // 48
    
    new_hourly_wage = hourly_wage
    if new_wage_level > old_wage_level and new_wage_level <= 20:
        # 时薪上涨（基于当前工资水平的25%）
        new_hourly_wage = int(hourly_wage * 1.25)
    
    # 更新数据库
    sql = f"UPDATE user_profession SET working_hours={total_working_hours}, hourly_wage={new_hourly_wage} WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    
    # 删除打工状态
    sql = f"DELETE FROM working_status WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    
    conn.commit()
    cursor.close()
    conn.close()
    
    # 删除内存中的打工状态
    del working_status[(group_id, user_id)]
    
    # 构建回复消息
    message = f"打工结束！\n本次打工时长：{hours_worked_int}小时\n获得工资：{wage:.2f}金币\n当前金币：{(user_coins + wage):.2f}"
    
    if new_hourly_wage > hourly_wage:
        message += f"\n恭喜！你的时薪提升至{new_hourly_wage}金币/小时"
    
    return message

def refresh_hourly_wage(group_id: int, user_id: int) -> str:
    """根据累计打工时间重新计算正确的工资水平"""
    # 检查职业
    profession = get_user_profession(group_id, user_id)
    if profession != PROF_WORKER:
        return "只有牛马职业才能刷新工资"
    
    # 获取累计打工时间
    init_profession_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT working_hours FROM user_profession WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        cursor.close()
        conn.close()
        return "未找到用户职业信息"
    
    total_working_hours = result[0] if result[0] is not None else 0
    
    # 根据累计打工时间计算正确的工资水平
    # 每48小时上涨一次，最多上涨20次
    wage_level = min(total_working_hours // 48, 20)
    
    # 计算正确的时薪：基础工资10，每次上涨25%
    correct_hourly_wage = 10
    for i in range(wage_level):
        correct_hourly_wage = int(correct_hourly_wage * 1.25)
    
    # 更新数据库中的时薪
    sql = f"UPDATE user_profession SET hourly_wage={correct_hourly_wage} WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()
    
    # 如果用户正在打工，也需要更新打工状态中的时薪
    if (group_id, user_id) in working_status:
        working_status[(group_id, user_id)]["hourly_wage"] = correct_hourly_wage
        
        # 更新数据库中的打工状态
        conn = sqlite3.connect("identifier.sqlite")
        cursor = conn.cursor()
        sql = f"UPDATE working_status SET hourly_wage={correct_hourly_wage} WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        conn.close()
    
    return f"工资刷新成功！\n累计打工时长：{total_working_hours}小时\n工资等级：{wage_level}级\n当前时薪：{correct_hourly_wage}金币/小时"

def produce_resource_with_profession(group_id: int, user_id: int, resource_type: int) -> str:
    """根据职业生产资源"""
    # 获取用户职业
    profession = get_user_profession(group_id, user_id)
    
    # 检查职业是否允许生产该资源
    if profession == PROF_WORKER:
        return "牛马职业只能打工，无法生产资源"
    
    # 严格检查职业是否匹配资源类型
    if resource_type == RESOURCE_ORE and profession != PROF_MINER and profession != PROF_NONE:
        return "只有矿工职业才能挖矿收集矿石"
    
    if resource_type == RESOURCE_FOOD and profession != PROF_FARMER and profession != PROF_NONE:
        return "只有农夫职业才能种地收集食物"
    
    if resource_type == RESOURCE_WOOD and profession != PROF_LUMBERJACK and profession != PROF_NONE:
        return "只有伐木工职业才能砍树收集木材"
    
    if profession == PROF_BLACKSMITH:
        return "铁匠职业无法直接生产资源，请使用打造功能"
    
    # 确定对应的工具类别
    tool_category = -1
    if resource_type == RESOURCE_ORE:
        tool_category = TOOL_TYPE_PICKAXE
    elif resource_type == RESOURCE_FOOD:
        tool_category = TOOL_TYPE_HOE
    elif resource_type == RESOURCE_WOOD:
        tool_category = TOOL_TYPE_AXE
    
    # 使用工具（如果有）
    tool_type, tool_used = use_tool(group_id, user_id, tool_category)
    
    # 调用基础资源生产函数
    from . import resource
    result = resource._base_produce_resource(group_id, user_id, resource_type)
    
    # 如果生产失败，直接返回结果
    if "生产成功" not in result:
        return result
    
    # 解析基础产出
    import re
    output_match = re.search(r"获得(\d+)个", result)
    base_output = int(output_match.group(1)) if output_match else 0
    
    # 获取当前资源数量（基础产出已经添加）
    current_resource = get_user_resource(group_id, user_id, resource_type)
    
    # 应用工具和职业加成
    bonus_output = 0
    special_resource_gained = False
    special_resource_type = -1
    special_resource_amount = 0
    
    # 工具加成
    if tool_used:
        # 铁质工具：提高资源产量10%，有10%的概率产出翻倍
        if tool_type >= TOOL_IRON:
            # 基础提升10%产量，确保至少增加1个
            iron_bonus = int(base_output * 0.1)
            iron_bonus = max(1, iron_bonus)
            bonus_output += iron_bonus
            
            # 10%概率产出翻倍
            if random.random() < 0.1:
                bonus_output += base_output
                result = result.replace(f"获得{base_output}个", f"获得{base_output + bonus_output}个")
                result += "\n【铁质工具】触发效果：收获翻倍！"
            else:
                result = result.replace(f"获得{base_output}个", f"获得{base_output + bonus_output}个")
                result += "\n【铁质工具】触发效果：产量+10%！"
            
            # 更新资源数量，添加工具带来的额外产出
            update_user_resource(group_id, user_id, resource_type, current_resource + bonus_output)
        
        # 精金工具特殊效果
        if tool_type >= TOOL_FINE_GOLD:
            if resource_type == RESOURCE_ORE and random.random() < 0.1:
                # 矿工：10%概率获得海蓝宝石
                special_resource_gained = True
                special_resource_type = SPECIAL_BLUE_GEM
                special_resource_amount = 1
            elif resource_type == RESOURCE_FOOD and random.random() < 0.15:
                # 农夫：15%概率获得超级植株
                special_resource_gained = True
                special_resource_type = SPECIAL_SUPER_PLANT
                special_resource_amount = 1
            elif resource_type == RESOURCE_WOOD and random.random() < 0.1:
                # 伐木工：10%概率获得恶魔树枝干
                special_resource_gained = True
                special_resource_type = SPECIAL_DEMON_BRANCH
                special_resource_amount = 1
        
        # 强化合金工具：资源产量+50%
        if tool_type >= TOOL_ALLOY:
            # 确保至少增加1个产量
            additional_output = base_output // 2
            additional_output = max(1, additional_output)
            bonus_output += additional_output
            
            # 更新结果显示
            current_total = base_output + bonus_output
            result = result.replace(f"获得{base_output}个", f"获得{current_total}个")
            result += "\n【强化合金工具】触发效果：产量+50%！"
            
            # 更新资源数量
            update_user_resource(group_id, user_id, resource_type, current_resource + additional_output)
    
    # 处理特殊资源获得
    if special_resource_gained:
        current_special = get_special_resource(group_id, user_id, special_resource_type)
        update_special_resource(group_id, user_id, special_resource_type, current_special + special_resource_amount)
        
        special_names = ["海蓝宝石", "超级植株", "恶魔树枝干"]
        result += f"\n【精金工具】触发效果：额外获得{special_names[special_resource_type]}×{special_resource_amount}！"
    
    return result

def produce_resource_with_stamina_recovery(group_id: int, user_id: int, resource_type: int) -> str:
    """生产资源并恢复体力"""
    # 获取当前体力
    stamina = get_user_stamina(group_id, user_id)
    
    # 检查体力是否足够
    if stamina < RESOURCE_STAMINA_COST[resource_type]:
        return "体力不足，无法生产资源"
    
    # 生产资源
    result = produce_resource_with_profession(group_id, user_id, resource_type)
    
    # 如果生产失败，直接返回结果
    if "生产成功" not in result:
        return result
    
    # 消耗体力
    new_stamina = stamina - RESOURCE_STAMINA_COST[resource_type]
    update_user_stamina(group_id, user_id, new_stamina)
    
    # 计算体力恢复
    # 获取当前时间
    current_time = time.time()
    
    # 获取上次体力更新时间
    from . import resource
    last_stamina_update = resource.get_last_stamina_update(group_id, user_id)
    
    # 计算体力恢复量（每小时恢复10点）
    time_diff = current_time - last_stamina_update
    hours_passed = time_diff / 3600
    stamina_recovery = int(hours_passed * 10)
    
    # 应用体力恢复
    actual_recovery = min(stamina_recovery, MAX_STAMINA - new_stamina)
    if actual_recovery > 0:
        new_stamina += actual_recovery
        update_user_stamina(group_id, user_id, new_stamina)
        resource.update_last_stamina_update(group_id, user_id, current_time)
    
    # 添加体力信息到结果
    message = result + f"\n消耗体力：{RESOURCE_STAMINA_COST[resource_type]}点"
    if actual_recovery > 0:
        message += f"\n体力恢复：{actual_recovery}点"
    message += f"\n当前体力：{stamina + actual_recovery}点"
    
    return message

def craft_tool(group_id: int, user_id: int, tool_type: int, tool_category: int) -> str:
    """打造工具（铁匠职业）"""
    # 检查职业
    profession = get_user_profession(group_id, user_id)
    if profession != PROF_BLACKSMITH:
        return "只有铁匠职业才能打造工具"
    
    # 检查工具类型是否有效
    if tool_type not in [TOOL_IRON, TOOL_FINE_GOLD, TOOL_ALLOY]:
        return "无效的工具类型"
    
    # 检查工具类别是否有效
    if tool_category not in [TOOL_TYPE_PICKAXE, TOOL_TYPE_HOE, TOOL_TYPE_AXE]:
        return "无效的工具类别"
    
    # 检查是否已有该工具
    current_durability = get_tool_durability(group_id, user_id, tool_type, tool_category)
    if current_durability > 0:
        tool_names = ["铁质", "精金", "强化合金"]
        category_names = ["镐", "锄", "斧"]
        return f"你已经拥有{tool_names[tool_type]}{category_names[tool_category]}了"
    
    # 检查材料是否足够
    materials = TOOL_CRAFTING_MATERIALS[tool_type]
    for resource_type, required_amount in materials.items():
        if resource_type in [RESOURCE_ORE, RESOURCE_WOOD, RESOURCE_FOOD]:
            current_amount = get_user_resource(group_id, user_id, resource_type)
        else:
            current_amount = get_special_resource(group_id, user_id, resource_type)
        
        if current_amount < required_amount:
            resource_names = {RESOURCE_ORE: "矿石", RESOURCE_WOOD: "木材", RESOURCE_FOOD: "食物", 
                            SPECIAL_BLUE_GEM: "海蓝宝石", SPECIAL_SUPER_PLANT: "超级植株", SPECIAL_DEMON_BRANCH: "恶魔树枝干"}
            return f"材料不足：需要{resource_names[resource_type]}×{required_amount}，当前拥有{current_amount}"
    
    # 消耗材料
    for resource_type, required_amount in materials.items():
        if resource_type in [RESOURCE_ORE, RESOURCE_WOOD, RESOURCE_FOOD]:
            current_amount = get_user_resource(group_id, user_id, resource_type)
            update_user_resource(group_id, user_id, resource_type, current_amount - required_amount)
        else:
            current_amount = get_special_resource(group_id, user_id, resource_type)
            update_special_resource(group_id, user_id, resource_type, current_amount - required_amount)
    
    # 创建工具
    durability = TOOL_DURABILITY[tool_type]
    update_tool_durability(group_id, user_id, tool_type, tool_category, durability)
    
    # 构建回复消息
    tool_names = ["铁质", "精金", "强化合金"]
    category_names = ["镐", "锄", "斧"]
    message = f"打造成功！获得{tool_names[tool_type]}{category_names[tool_category]}（耐久：{durability}）\n\n消耗材料：\n"
    
    resource_names = {RESOURCE_ORE: "矿石", RESOURCE_WOOD: "木材", RESOURCE_FOOD: "食物", 
                    SPECIAL_BLUE_GEM: "海蓝宝石", SPECIAL_SUPER_PLANT: "超级植株", SPECIAL_DEMON_BRANCH: "恶魔树枝干"}
    
    for resource_type, amount in materials.items():
        resource_name = resource_names[resource_type]
        message += f"- {resource_name}×{amount}\n"
    
    return message

def upgrade_tool(group_id: int, user_id: int, tool_category: int) -> str:
    """升级工具为不毁版（铁匠职业）"""
    # 检查职业
    profession = get_user_profession(group_id, user_id)
    if profession != PROF_BLACKSMITH:
        return "只有铁匠职业才能升级工具"
    
    # 检查工具类别是否有效
    if tool_category not in [TOOL_TYPE_PICKAXE, TOOL_TYPE_HOE, TOOL_TYPE_AXE]:
        return "无效的工具类别"
    
    # 检查是否有强化合金工具
    current_durability = get_tool_durability(group_id, user_id, TOOL_ALLOY, tool_category)
    if current_durability <= 0:
        category_names = ["镐", "锄", "斧"]
        return f"你没有强化合金{category_names[tool_category]}，无法升级"
    
    # 检查是否已有不毁版
    perm_durability = get_tool_durability(group_id, user_id, TOOL_ALLOY_PERM, tool_category)
    if perm_durability == -1:
        category_names = ["镐", "锄", "斧"]
        return f"你已经拥有强化合金{category_names[tool_category]}【不毁】了"
    
    # 检查升级材料是否足够
    materials = TOOL_CRAFTING_MATERIALS[TOOL_ALLOY_PERM]
    for resource_type, required_amount in materials.items():
        current_amount = get_special_resource(group_id, user_id, resource_type)
        if current_amount < required_amount:
            resource_names = {SPECIAL_BLUE_GEM: "海蓝宝石", SPECIAL_DEMON_BRANCH: "恶魔树枝干"}
            return f"升级材料不足：需要{resource_names[resource_type]}×{required_amount}，当前拥有{current_amount}"
    
    # 消耗升级材料
    for resource_type, required_amount in materials.items():
        current_amount = get_special_resource(group_id, user_id, resource_type)
        update_special_resource(group_id, user_id, resource_type, current_amount - required_amount)
    
    # 删除原工具，创建不毁版
    update_tool_durability(group_id, user_id, TOOL_ALLOY, tool_category, 0)
    update_tool_durability(group_id, user_id, TOOL_ALLOY_PERM, tool_category, -1)  # -1表示无限耐久
    
    # 构建回复消息
    category_names = ["镐", "锄", "斧"]
    message = f"升级成功！强化合金{category_names[tool_category]}已升级为【不毁】版本\n\n消耗材料：\n"
    
    resource_names = {SPECIAL_BLUE_GEM: "海蓝宝石", SPECIAL_DEMON_BRANCH: "恶魔树枝干"}
    
    for resource_type, amount in materials.items():
        resource_name = resource_names[resource_type]
        message += f"- {resource_name}×{amount}\n"
    
    return message

def get_profession_info(group_id: int, user_id: int) -> str:
    """获取职业信息"""
    profession = get_user_profession(group_id, user_id)
    
    if profession == PROF_NONE:
        return "你还没有选择职业，请使用 切换职业 命令选择职业"
    
    profession_names = ["牛马", "矿工", "农夫", "伐木工", "铁匠"]
    message = f"===== 职业信息 =====\n当前职业：{profession_names[profession]}\n"
    
    # 检查职业切换CD
    allowed, cd_message = check_profession_change_cd(group_id, user_id)
    if not allowed:
        message += f"职业切换状态：{cd_message}\n"
    else:
        message += "职业切换状态：可切换\n"
    
    if profession == PROF_WORKER:
        # 牛马职业：显示打工信息
        init_profession_db()
        conn = sqlite3.connect("identifier.sqlite")
        cursor = conn.cursor()
        
        sql = f"SELECT working_hours, hourly_wage FROM user_profession WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        working_hours = result[0] if result else 0
        hourly_wage = result[1] if result else 10
        
        cursor.close()
        conn.close()
        
        message += f"\n===== 牛马职业信息 =====\n"
        message += f"累计打工时长：{working_hours}小时\n"
        message += f"当前时薪：{hourly_wage}金币/小时\n"
        
        # 检查是否在打工中
        if (group_id, user_id) in working_status:
            start_time = working_status[(group_id, user_id)]["start_time"]
            current_time = time.time()
            hours_worked = (current_time - start_time) / 3600  # 转换为小时
            hours_worked_int = int(hours_worked)
            minutes_worked = int((hours_worked - hours_worked_int) * 60)
            
            message += f"当前打工状态：进行中\n"
            message += f"已打工时长：{hours_worked_int}小时{minutes_worked}分钟\n"
            message += f"预计工资：{hours_worked_int * hourly_wage}金币\n"
        else:
            message += f"当前打工状态：未开始\n"
    
    elif profession in [PROF_MINER, PROF_FARMER, PROF_LUMBERJACK]:
        # 资源生产职业：显示工具信息
        tool_category = -1
        if profession == PROF_MINER:
            tool_category = TOOL_TYPE_PICKAXE
            message += f"\n===== 矿工职业信息 =====\n"
            message += f"特殊能力：使用镐类工具会获得增益\n"
        elif profession == PROF_FARMER:
            tool_category = TOOL_TYPE_HOE
            message += f"\n===== 农夫职业信息 =====\n"
            message += f"特殊能力：使用锄类工具会获得增益\n"
        elif profession == PROF_LUMBERJACK:
            tool_category = TOOL_TYPE_AXE
            message += f"\n===== 伐木工职业信息 =====\n"
            message += f"特殊能力：使用斧类工具会获得增益\n"
        
        # 获取工具信息
        tool_type_names = ["铁质", "精金", "强化合金", "强化合金【不毁】"]
        tool_category_names = ["镐", "锄", "斧"]
        
        message += f"当前装备："
        has_tool = False
        
        for tool_type in [TOOL_ALLOY_PERM, TOOL_ALLOY, TOOL_FINE_GOLD, TOOL_IRON]:
            durability = get_tool_durability(group_id, user_id, tool_type, tool_category)
            if durability > 0 or (tool_type == TOOL_ALLOY_PERM and durability == -1):
                durability_text = "无限" if durability == -1 else str(durability)
                message += f"{tool_type_names[tool_type]}{tool_category_names[tool_category]}（耐久：{durability_text}）\n"
                has_tool = True
                break
        
        if not has_tool:
            message += "无\n"
    
    elif profession == PROF_BLACKSMITH:
        # 铁匠职业：显示打造信息
        message += f"\n===== 铁匠职业信息 =====\n"
        message += f"特殊能力：可以打造和升级工具\n"
        message += f"\n打造列表：\n"
        message += f"- 铁质工具：可使用10次，需要矿石×30、木材×10\n"
        message += f"- 精金工具：可使用30次，需要矿石×120、木材×60\n"
        message += f"- 强化合金工具：可使用100次，需要矿石×600、木材×240、恶魔树枝干×1、海蓝宝石×1\n"
        message += f"- 强化合金工具【不毁】：无限次使用，需要海蓝宝石×25、恶魔树枝干×25（升级）\n"
    
    # 显示特殊资源信息
    blue_gem = get_special_resource(group_id, user_id, SPECIAL_BLUE_GEM)
    super_plant = get_special_resource(group_id, user_id, SPECIAL_SUPER_PLANT)
    demon_branch = get_special_resource(group_id, user_id, SPECIAL_DEMON_BRANCH)
    
    message += f"\n===== 特殊资源 =====\n"
    message += f"海蓝宝石：{blue_gem}个\n"
    message += f"超级植株：{super_plant}个\n"
    message += f"恶魔树枝干：{demon_branch}个\n"
    
    return message
