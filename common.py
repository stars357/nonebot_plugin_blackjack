import sqlite3
import datetime
import random
import time
from typing import Dict, List, Tuple, Optional, Union
from .sign import get_point, update_point

# 资源类型常量
RESOURCE_FOOD = 0    # 食物
RESOURCE_WOOD = 1    # 木材
RESOURCE_ORE = 2     # 矿石

# 工具类型常量
TOOL_IRON = 0        # 铁质工具
TOOL_FINE_GOLD = 1   # 精金工具
TOOL_ALLOY = 2       # 强化合金工具
TOOL_ALLOY_PERM = 3  # 强化合金工具【不毁】

# 工具种类常量
TOOL_TYPE_PICKAXE = 0  # 镐
TOOL_TYPE_HOE = 1      # 锄
TOOL_TYPE_AXE = 2      # 斧

# 职业类型常量
PROF_NONE = -1      # 无职业
PROF_WORKER = 0     # 牛马
PROF_MINER = 1      # 矿工
PROF_FARMER = 2     # 农夫
PROF_LUMBERJACK = 3 # 伐木工
PROF_BLACKSMITH = 4 # 铁匠

# 特殊资源常量
SPECIAL_BLUE_GEM = 0    # 海蓝宝石
SPECIAL_SUPER_PLANT = 1 # 超级植株
SPECIAL_DEMON_BRANCH = 2 # 恶魔树枝干

# 资源基准价格
RESOURCE_PRICES = {
    RESOURCE_FOOD: 10,  # 食物：10金币/单位
    RESOURCE_WOOD: 15,  # 木材：15金币/单位
    RESOURCE_ORE: 20    # 矿石：20金币/单位
}

# 工具基准价格
TOOL_PRICES = {
    TOOL_IRON: 1000,      # 铁质工具：1000金币/个
    TOOL_FINE_GOLD: 4500, # 精金工具：4500金币/个
    TOOL_ALLOY: 22500,    # 强化合金工具：22500金币/个
    # TOOL_ALLOY_PERM: 无基准价格
}

# 资源生产消耗的体力
RESOURCE_STAMINA_COST = {
    RESOURCE_FOOD: 5,   # 食物：5体力
    RESOURCE_WOOD: 8,   # 木材：8体力
    RESOURCE_ORE: 10    # 矿石：10体力
}

# 资源生产CD（秒）
RESOURCE_CD = {
    RESOURCE_FOOD: 300,  # 食物：300秒
    RESOURCE_WOOD: 400,  # 木材：400秒
    RESOURCE_ORE: 500    # 矿石：500秒
}

# 资源生产产出范围
RESOURCE_OUTPUT = {
    RESOURCE_FOOD: (10, 20),  # 食物：10~20个
    RESOURCE_WOOD: (6, 13),   # 木材：6~13个
    RESOURCE_ORE: (5, 10)     # 矿石：5~10个
}

# 工具耐久度
TOOL_DURABILITY = {
    TOOL_IRON: 10,        # 铁质工具：10次
    TOOL_FINE_GOLD: 30,   # 精金工具：30次
    TOOL_ALLOY: 100,      # 强化合金工具：100次
    TOOL_ALLOY_PERM: -1   # 强化合金工具【不毁】：无限
}

# 体力上限
MAX_STAMINA = 100