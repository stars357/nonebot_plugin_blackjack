import sqlite3
import datetime
from typing import Dict, List, Tuple, Optional, Union
from .sign import get_point, update_point
from .resource import get_user_resource, update_user_resource, RESOURCE_PRICES
from .market import get_resource_price_info

# 联盟类型常量
ALLIANCE_NONE = -1        # 无联盟
ALLIANCE_BUSINESS = 0     # 商业联盟
ALLIANCE_MILITARY = 1     # 军事同盟
ALLIANCE_LABOR = 2        # 工农联合

# 联盟名称
ALLIANCE_NAMES = {
    ALLIANCE_BUSINESS: "商业联盟",
    ALLIANCE_MILITARY: "军事同盟",
    ALLIANCE_LABOR: "工农联合"
}

# 联盟特权
# 商业联盟：交易税-100%，可查看当前资源的市场价格
# 军事同盟：被抢劫概率-20%，被抢劫保护30%资源或金币
# 工农联合：生产产量+10%，体力消耗-10%

# 联盟成员字典 {group_id: {alliance_type: [member_ids]}}
alliance_members: Dict[int, Dict[int, List[int]]] = {}

# 联盟领袖字典 {group_id: {alliance_type: leader_id}}
alliance_leaders: Dict[int, Dict[int, int]] = {}

# 联盟转移请求字典 {group_id: {alliance_type: {"from": current_leader_id, "to": new_leader_id}}}
alliance_transfer_requests: Dict[int, Dict[int, Dict[str, int]]] = {}

def init_alliance_db():
    """初始化联盟数据库"""
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 创建联盟成员表
    sql = """
    CREATE TABLE IF NOT EXISTS alliance_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        belonging_group INTEGER NOT NULL,
        alliance_type INTEGER NOT NULL DEFAULT -1,  -- -1: 无联盟, 0: 商业联盟, 1: 军事同盟, 2: 工农联合
        join_date DATE NOT NULL,
        UNIQUE(uid, belonging_group)
    )
    """
    cursor.execute(sql)
    
    # 创建联盟领袖表
    sql = """
    CREATE TABLE IF NOT EXISTS alliance_leaders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        belonging_group INTEGER NOT NULL,
        alliance_type INTEGER NOT NULL,  -- 0: 商业联盟, 1: 军事同盟, 2: 工农联合
        leader_id INTEGER NOT NULL,
        UNIQUE(belonging_group, alliance_type)
    )
    """
    cursor.execute(sql)
    
    conn.commit()
    cursor.close()
    conn.close()

def get_user_alliance(group_id: int, user_id: int) -> int:
    """获取用户所属联盟"""
    init_alliance_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT alliance_type FROM alliance_members WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 创建新记录，默认无联盟
        sql = f"INSERT INTO alliance_members (uid, belonging_group, alliance_type, join_date) VALUES ({user_id}, {group_id}, {ALLIANCE_NONE}, '{datetime.date.today().isoformat()}')"
        cursor.execute(sql)
        conn.commit()
        alliance_type = ALLIANCE_NONE
    else:
        alliance_type = result[0]
    
    cursor.close()
    conn.close()
    return alliance_type

def join_alliance(group_id: int, user_id: int, alliance_type: int) -> str:
    """加入联盟"""
    # 检查联盟类型是否有效
    if alliance_type not in [ALLIANCE_BUSINESS, ALLIANCE_MILITARY, ALLIANCE_LABOR]:
        return "无效的联盟类型！"
    
    # 获取用户当前联盟
    current_alliance = get_user_alliance(group_id, user_id)
    
    # 如果已经在该联盟中
    if current_alliance == alliance_type:
        return f"你已经是{ALLIANCE_NAMES[alliance_type]}的成员了！"
    
    # 如果在其他联盟中
    if current_alliance != ALLIANCE_NONE:
        return f"你已经是{ALLIANCE_NAMES[current_alliance]}的成员，请先退出当前联盟！"
    
    # 加入新联盟
    init_alliance_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    today = datetime.date.today().isoformat()
    sql = f"UPDATE alliance_members SET alliance_type={alliance_type}, join_date='{today}' WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    conn.commit()
    
    # 检查是否需要设置联盟领袖
    sql = f"SELECT leader_id FROM alliance_leaders WHERE belonging_group={group_id} AND alliance_type={alliance_type}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    if result is None:
        # 该联盟还没有领袖，将当前用户设为领袖
        sql = f"INSERT INTO alliance_leaders (belonging_group, alliance_type, leader_id) VALUES ({group_id}, {alliance_type}, {user_id})"
        cursor.execute(sql)
        conn.commit()
        
        # 更新内存中的领袖记录
        if group_id not in alliance_leaders:
            alliance_leaders[group_id] = {}
        alliance_leaders[group_id][alliance_type] = user_id
        
        cursor.close()
        conn.close()
        return f"你已成功创建并加入{ALLIANCE_NAMES[alliance_type]}，并成为联盟领袖！"
    
    # 更新内存中的成员记录
    if group_id not in alliance_members:
        alliance_members[group_id] = {}
    if alliance_type not in alliance_members[group_id]:
        alliance_members[group_id][alliance_type] = []
    alliance_members[group_id][alliance_type].append(user_id)
    
    cursor.close()
    conn.close()
    return f"你已成功加入{ALLIANCE_NAMES[alliance_type]}！"

def leave_alliance(group_id: int, user_id: int) -> str:
    """退出联盟"""
    # 获取用户当前联盟
    current_alliance = get_user_alliance(group_id, user_id)
    
    # 如果不在任何联盟中
    if current_alliance == ALLIANCE_NONE:
        return "你目前不属于任何联盟！"
    
    # 检查是否是联盟领袖
    is_leader = False
    if group_id in alliance_leaders and current_alliance in alliance_leaders[group_id]:
        if alliance_leaders[group_id][current_alliance] == user_id:
            is_leader = True
    
    if not is_leader:
        # 从数据库中查询
        init_alliance_db()
        conn = sqlite3.connect("identifier.sqlite")
        cursor = conn.cursor()
        
        sql = f"SELECT leader_id FROM alliance_leaders WHERE belonging_group={group_id} AND alliance_type={current_alliance}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result and result[0] == user_id:
            is_leader = True
        
        cursor.close()
        conn.close()
    
    if is_leader:
        return "作为联盟领袖，你不能直接退出联盟。请先将领袖职位转移给其他成员，或者解散联盟！"
    
    # 退出联盟
    init_alliance_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"UPDATE alliance_members SET alliance_type={ALLIANCE_NONE} WHERE uid={user_id} AND belonging_group={group_id}"
    cursor.execute(sql)
    conn.commit()
    
    # 更新内存中的成员记录
    if group_id in alliance_members and current_alliance in alliance_members[group_id]:
        if user_id in alliance_members[group_id][current_alliance]:
            alliance_members[group_id][current_alliance].remove(user_id)
    
    cursor.close()
    conn.close()
    return f"你已成功退出{ALLIANCE_NAMES[current_alliance]}！"

def transfer_leadership(group_id: int, current_leader_id: int, new_leader_id: int) -> str:
    """发起领袖转移请求"""
    # 获取当前用户的联盟
    current_alliance = get_user_alliance(group_id, current_leader_id)
    
    # 检查是否是联盟领袖
    is_leader = False
    if group_id in alliance_leaders and current_alliance in alliance_leaders[group_id]:
        if alliance_leaders[group_id][current_alliance] == current_leader_id:
            is_leader = True
    
    if not is_leader:
        # 从数据库中查询
        init_alliance_db()
        conn = sqlite3.connect("identifier.sqlite")
        cursor = conn.cursor()
        
        sql = f"SELECT leader_id FROM alliance_leaders WHERE belonging_group={group_id} AND alliance_type={current_alliance}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result and result[0] == current_leader_id:
            is_leader = True
        
        cursor.close()
        conn.close()
    
    if not is_leader:
        return "只有联盟领袖才能转移领导权！"
    
    # 检查新领袖是否在同一联盟
    new_leader_alliance = get_user_alliance(group_id, new_leader_id)
    if new_leader_alliance != current_alliance:
        return "指定的新领袖不是该联盟的成员！"
    
    # 创建转移请求
    if group_id not in alliance_transfer_requests:
        alliance_transfer_requests[group_id] = {}
    alliance_transfer_requests[group_id][current_alliance] = {"from": current_leader_id, "to": new_leader_id}
    
    return f"已向{new_leader_id}发送领袖转移请求，等待其确认！"

def accept_leadership(group_id: int, user_id: int) -> str:
    """接受领袖转移请求"""
    # 检查是否有针对该用户的转移请求
    if group_id not in alliance_transfer_requests:
        return "没有待处理的领袖转移请求！"
    
    # 获取用户的联盟
    user_alliance = get_user_alliance(group_id, user_id)
    if user_alliance == ALLIANCE_NONE:
        return "你不属于任何联盟！"
    
    if user_alliance not in alliance_transfer_requests[group_id]:
        return "没有针对你所在联盟的领袖转移请求！"
    
    transfer_request = alliance_transfer_requests[group_id][user_alliance]
    if transfer_request["to"] != user_id:
        return "该转移请求不是针对你的！"
    
    # 执行领袖转移
    init_alliance_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"UPDATE alliance_leaders SET leader_id={user_id} WHERE belonging_group={group_id} AND alliance_type={user_alliance}"
    cursor.execute(sql)
    conn.commit()
    
    # 更新内存中的领袖记录
    if group_id not in alliance_leaders:
        alliance_leaders[group_id] = {}
    alliance_leaders[group_id][user_alliance] = user_id
    
    # 删除转移请求
    del alliance_transfer_requests[group_id][user_alliance]
    
    cursor.close()
    conn.close()
    return f"你已成功接任{ALLIANCE_NAMES[user_alliance]}的领袖职位！"

def disband_alliance(group_id: int, leader_id: int) -> str:
    """解散联盟（仅领袖可操作）"""
    # 获取用户的联盟
    leader_alliance = get_user_alliance(group_id, leader_id)
    if leader_alliance == ALLIANCE_NONE:
        return "你不属于任何联盟！"
    
    # 检查是否是联盟领袖
    is_leader = False
    if group_id in alliance_leaders and leader_alliance in alliance_leaders[group_id]:
        if alliance_leaders[group_id][leader_alliance] == leader_id:
            is_leader = True
    
    if not is_leader:
        # 从数据库中查询
        init_alliance_db()
        conn = sqlite3.connect("identifier.sqlite")
        cursor = conn.cursor()
        
        sql = f"SELECT leader_id FROM alliance_leaders WHERE belonging_group={group_id} AND alliance_type={leader_alliance}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result and result[0] == leader_id:
            is_leader = True
        
        cursor.close()
        conn.close()
    
    if not is_leader:
        return "只有联盟领袖才能解散联盟！"
    
    # 解散联盟
    init_alliance_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    # 将所有成员的联盟设为无
    sql = f"UPDATE alliance_members SET alliance_type={ALLIANCE_NONE} WHERE belonging_group={group_id} AND alliance_type={leader_alliance}"
    cursor.execute(sql)
    
    # 删除领袖记录
    sql = f"DELETE FROM alliance_leaders WHERE belonging_group={group_id} AND alliance_type={leader_alliance}"
    cursor.execute(sql)
    
    conn.commit()
    
    # 更新内存中的记录
    if group_id in alliance_members and leader_alliance in alliance_members[group_id]:
        alliance_members[group_id][leader_alliance] = []
    
    if group_id in alliance_leaders and leader_alliance in alliance_leaders[group_id]:
        del alliance_leaders[group_id][leader_alliance]
    
    cursor.close()
    conn.close()
    return f"你已成功解散{ALLIANCE_NAMES[leader_alliance]}！"

def get_alliance_members(group_id: int, alliance_type: int) -> List[int]:
    """获取联盟成员列表"""
    init_alliance_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT uid FROM alliance_members WHERE belonging_group={group_id} AND alliance_type={alliance_type}"
    cursor.execute(sql)
    results = cursor.fetchall()
    
    members = [result[0] for result in results]
    
    cursor.close()
    conn.close()
    
    # 更新内存中的成员记录
    if group_id not in alliance_members:
        alliance_members[group_id] = {}
    alliance_members[group_id][alliance_type] = members
    
    return members

def get_alliance_leader(group_id: int, alliance_type: int) -> int:
    """获取联盟领袖ID"""
    # 先从内存中查找
    if group_id in alliance_leaders and alliance_type in alliance_leaders[group_id]:
        return alliance_leaders[group_id][alliance_type]
    
    # 从数据库中查询
    init_alliance_db()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    
    sql = f"SELECT leader_id FROM alliance_leaders WHERE belonging_group={group_id} AND alliance_type={alliance_type}"
    cursor.execute(sql)
    result = cursor.fetchone()
    
    leader_id = result[0] if result else 0
    
    cursor.close()
    conn.close()
    
    # 更新内存中的领袖记录
    if leader_id > 0:
        if group_id not in alliance_leaders:
            alliance_leaders[group_id] = {}
        alliance_leaders[group_id][alliance_type] = leader_id
    
    return leader_id

def get_alliance_info(group_id: int, alliance_type: int) -> str:
    """获取联盟信息"""
    if alliance_type not in [ALLIANCE_BUSINESS, ALLIANCE_MILITARY, ALLIANCE_LABOR]:
        return "无效的联盟类型！"
    
    # 获取联盟成员
    members = get_alliance_members(group_id, alliance_type)
    
    # 获取联盟领袖
    leader_id = get_alliance_leader(group_id, alliance_type)
    
    # 生成联盟信息
    alliance_name = ALLIANCE_NAMES[alliance_type]
    info = f"===== {alliance_name} =====\n"
    info += f"成员数量：{len(members)}\n"
    info += f"联盟领袖：{leader_id}\n\n"
    
    # 添加联盟特权信息
    info += "联盟特权：\n"
    if alliance_type == ALLIANCE_BUSINESS:
        info += "- 交易税减免100%\n"
        info += "- 可查看当前资源的市场价格\n"
    elif alliance_type == ALLIANCE_MILITARY:
        info += "- 被抢劫概率降低20%\n"
        info += "- 被抢劫时保护30%资源或金币\n"
    elif alliance_type == ALLIANCE_LABOR:
        info += "- 生产产量提高10%\n"
        info += "- 体力消耗降低10%\n"
    
    return info

def get_user_alliance_info(group_id: int, user_id: int) -> str:
    """获取用户的联盟信息"""
    # 获取用户的联盟
    alliance_type = get_user_alliance(group_id, user_id)
    
    if alliance_type == ALLIANCE_NONE:
        return "你目前不属于任何联盟！\n可用的联盟有：\n- 商业联盟：交易税-100%，可查看当前资源的市场价格\n- 军事同盟：被抢劫概率-20%，被抢劫保护30%资源或金币\n- 工农联合：生产产量+10%，体力消耗-10%"
    
    # 获取联盟信息
    alliance_info = get_alliance_info(group_id, alliance_type)
    
    # 检查是否是联盟领袖
    leader_id = get_alliance_leader(group_id, alliance_type)
    is_leader = (leader_id == user_id)
    
    if is_leader:
        alliance_info += "\n你是当前联盟的领袖！"
    
    return alliance_info

def check_business_alliance_bonus(group_id: int, user_id: int) -> bool:
    """检查用户是否有商业联盟加成（交易税减免）"""
    alliance_type = get_user_alliance(group_id, user_id)
    return alliance_type == ALLIANCE_BUSINESS

def check_military_alliance_bonus(group_id: int, user_id: int) -> Tuple[bool, bool]:
    """检查用户是否有军事同盟加成（抢劫概率降低和资源保护）"""
    alliance_type = get_user_alliance(group_id, user_id)
    if alliance_type == ALLIANCE_MILITARY:
        return True, True  # 返回(抢劫概率降低, 资源保护)
    return False, False

def check_labor_alliance_bonus(group_id: int, user_id: int) -> Tuple[bool, bool]:
    """检查用户是否有工农联合加成（产量提高和体力消耗降低）"""
    alliance_type = get_user_alliance(group_id, user_id)
    if alliance_type == ALLIANCE_LABOR:
        return True, True  # 返回(产量提高, 体力消耗降低)
    return False, False

def get_resource_market_price(group_id: int, user_id: int, resource_type: int) -> str:
    """获取资源市场价格（仅商业联盟成员可用）"""
    alliance_type = get_user_alliance(group_id, user_id)
    
    if alliance_type != ALLIANCE_BUSINESS:
        return "只有商业联盟的成员才能查看资源市场价格！"
    
    # 调用market.py中的函数获取资源价格信息
    return get_resource_price_info(resource_type)
