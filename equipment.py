import sqlite3
import datetime
from typing import Dict, List, Tuple, Optional, Union
from .common import (
    TOOL_IRON, TOOL_FINE_GOLD, TOOL_ALLOY, TOOL_ALLOY_PERM,
    TOOL_TYPE_PICKAXE, TOOL_TYPE_HOE, TOOL_TYPE_AXE
)
from .profession import get_tool_durability, update_tool_durability

# 用户装备状态字典 {(group_id, user_id): {tool_category: tool_type}}
equipped_tools: Dict[Tuple[int, int], Dict[int, int]] = {}

def init_equipment_db():
    """初始化装备系统数据库"""
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 创建用户装备表
    sql = """
    CREATE TABLE IF NOT EXISTS user_equipment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        tool_category INTEGER NOT NULL, -- 0: 镐, 1: 锄, 2: 斧
        tool_type INTEGER NOT NULL,     -- 0: 铁质工具, 1: 精金工具, 2: 强化合金工具, 3: 强化合金工具【不毁】
        equipped_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(uid, belonging_group, tool_category)
    )
    """
    cursor.execute(sql)
    
    conn.commit()
    cursor.close()
    conn.close()

def get_equipped_tool(group_id: int, user_id: int, tool_category: int) -> int:
    """获取用户当前装备的工具类型
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        tool_category: 工具种类 (0: 镐, 1: 锄, 2: 斧)
        
    Returns:
        工具类型 (-1: 未装备, 0: 铁质工具, 1: 精金工具, 2: 强化合金工具, 3: 强化合金工具【不毁】)
    """
    # 先检查内存中是否有记录
    if (group_id, user_id) in equipped_tools and tool_category in equipped_tools[(group_id, user_id)]:
        return equipped_tools[(group_id, user_id)][tool_category]
    
    # 从数据库查询
    init_equipment_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT tool_type FROM user_equipment WHERE uid={user_id} AND belonging_group={group_id} AND tool_category={tool_category}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 未装备工具
        tool_type = -1
    else:
        tool_type = result[0]
        
        # 更新内存记录
        if (group_id, user_id) not in equipped_tools:
            equipped_tools[(group_id, user_id)] = {}
        equipped_tools[(group_id, user_id)][tool_category] = tool_type
    
    cursor.close()
    conn.close()
    return tool_type

def equip_tool(group_id: int, user_id: int, tool_type: int, tool_category: int) -> str:
    """装备工具
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        tool_type: 工具类型 (0: 铁质工具, 1: 精金工具, 2: 强化合金工具, 3: 强化合金工具【不毁】)
        tool_category: 工具种类 (0: 镐, 1: 锄, 2: 斧)
        
    Returns:
        操作结果消息
    """
    # 检查工具类型是否有效
    if tool_type not in [TOOL_IRON, TOOL_FINE_GOLD, TOOL_ALLOY, TOOL_ALLOY_PERM]:
        return "无效的工具类型"
    
    # 检查工具种类是否有效
    if tool_category not in [TOOL_TYPE_PICKAXE, TOOL_TYPE_HOE, TOOL_TYPE_AXE]:
        return "无效的工具种类"
    
    # 检查用户是否有该工具
    durability = get_tool_durability(group_id, user_id, tool_type, tool_category)
    if durability <= 0 and not (tool_type == TOOL_ALLOY_PERM and durability == -1):
        tool_type_names = ["铁质", "精金", "强化合金", "强化合金【不毁】"]
        tool_category_names = ["镐", "锄", "斧"]
        return f"你没有{tool_type_names[tool_type]}{tool_category_names[tool_category]}，无法装备"
    
    # 获取当前装备的工具
    current_tool_type = get_equipped_tool(group_id, user_id, tool_category)
    
    # 如果已经装备了相同的工具，无需重复装备
    if current_tool_type == tool_type:
        tool_type_names = ["铁质", "精金", "强化合金", "强化合金【不毁】"]
        tool_category_names = ["镐", "锄", "斧"]
        return f"你已经装备了{tool_type_names[tool_type]}{tool_category_names[tool_category]}，无需重复装备"
    
    # 更新装备状态
    init_equipment_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT id FROM user_equipment WHERE uid={user_id} AND belonging_group={group_id} AND tool_category={tool_category}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 创建新记录
        sql = f"INSERT INTO user_equipment (uid, belonging_group, tool_category, tool_type) VALUES ({user_id}, {group_id}, {tool_category}, {tool_type})"
    else:
        # 更新记录
        sql = f"UPDATE user_equipment SET tool_type={tool_type}, equipped_time=CURRENT_TIMESTAMP WHERE uid={user_id} AND belonging_group={group_id} AND tool_category={tool_category}"
    
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()
    
    # 更新内存记录
    if (group_id, user_id) not in equipped_tools:
        equipped_tools[(group_id, user_id)] = {}
    equipped_tools[(group_id, user_id)][tool_category] = tool_type
    
    # 构建回复消息
    tool_type_names = ["铁质", "精金", "强化合金", "强化合金【不毁】"]
    tool_category_names = ["镐", "锄", "斧"]
    
    message = f"装备成功！当前装备：{tool_type_names[tool_type]}{tool_category_names[tool_category]}"
    
    # 显示工具耐久度
    if tool_type != TOOL_ALLOY_PERM:
        message += f"（耐久度：{durability}）"
    else:
        message += "（无限耐久）"
    
    return message

def unequip_tool(group_id: int, user_id: int, tool_category: int) -> str:
    """卸下工具
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        tool_category: 工具种类 (0: 镐, 1: 锄, 2: 斧)
        
    Returns:
        操作结果消息
    """
    # 检查工具种类是否有效
    if tool_category not in [TOOL_TYPE_PICKAXE, TOOL_TYPE_HOE, TOOL_TYPE_AXE]:
        return "无效的工具种类"
    
    # 获取当前装备的工具
    current_tool_type = get_equipped_tool(group_id, user_id, tool_category)
    
    # 如果没有装备工具，无需卸下
    if current_tool_type == -1:
        tool_category_names = ["镐", "锄", "斧"]
        return f"你没有装备{tool_category_names[tool_category]}，无需卸下"
    
    # 更新装备状态
    init_equipment_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 删除记录
    sql = f"DELETE FROM user_equipment WHERE uid={user_id} AND belonging_group={group_id} AND tool_category={tool_category}"
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()
    
    # 更新内存记录
    if (group_id, user_id) in equipped_tools and tool_category in equipped_tools[(group_id, user_id)]:
        del equipped_tools[(group_id, user_id)][tool_category]
    
    # 构建回复消息
    tool_type_names = ["铁质", "精金", "强化合金", "强化合金【不毁】"]
    tool_category_names = ["镐", "锄", "斧"]
    
    return f"卸下成功！已卸下{tool_type_names[current_tool_type]}{tool_category_names[tool_category]}"

def get_equipment_info(group_id: int, user_id: int) -> str:
    """获取用户装备信息
    
    Args:
        group_id: 群组ID
        user_id: 用户ID
        
    Returns:
        装备信息消息
    """
    # 获取各种类工具的装备状态
    pickaxe_type = get_equipped_tool(group_id, user_id, TOOL_TYPE_PICKAXE)
    hoe_type = get_equipped_tool(group_id, user_id, TOOL_TYPE_HOE)
    axe_type = get_equipped_tool(group_id, user_id, TOOL_TYPE_AXE)
    
    # 构建回复消息
    tool_type_names = ["铁质", "精金", "强化合金", "强化合金【不毁】"]
    
    message = "===== 装备信息 =====\n"
    
    # 镐
    message += "镐："
    if pickaxe_type == -1:
        message += "未装备\n"
    else:
        durability = get_tool_durability(group_id, user_id, pickaxe_type, TOOL_TYPE_PICKAXE)
        message += f"{tool_type_names[pickaxe_type]}镐"
        if pickaxe_type != TOOL_ALLOY_PERM:
            message += f"（耐久度：{durability}）\n"
        else:
            message += "（无限耐久）\n"
    
    # 锄
    message += "锄："
    if hoe_type == -1:
        message += "未装备\n"
    else:
        durability = get_tool_durability(group_id, user_id, hoe_type, TOOL_TYPE_HOE)
        message += f"{tool_type_names[hoe_type]}锄"
        if hoe_type != TOOL_ALLOY_PERM:
            message += f"（耐久度：{durability}）\n"
        else:
            message += "（无限耐久）\n"
    
    # 斧
    message += "斧："
    if axe_type == -1:
        message += "未装备\n"
    else:
        durability = get_tool_durability(group_id, user_id, axe_type, TOOL_TYPE_AXE)
        message += f"{tool_type_names[axe_type]}斧"
        if axe_type != TOOL_ALLOY_PERM:
            message += f"（耐久度：{durability}）\n"
        else:
            message += "（无限耐久）\n"
    
    message += "\n装备效果：\n"
    message += "- 铁质工具：10%概率收获翻倍，资源产量+10%\n"
    message += "- 精金工具：有几率获得特殊材料\n"
    message += "- 强化合金工具：资源产量+50%\n"
    
    return message