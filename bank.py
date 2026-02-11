import sqlite3
import datetime
import random
import time
from typing import Dict, List, Tuple, Optional, Union

# 导入公共数据库连接池
from .db import db_pool

# 导入公共缓存模块
from .cache import cache_manager

# 状态常量
STATUS_FREE = 0      # 自由状态
STATUS_PRISON = 1    # 监狱状态
STATUS_WANTED = 2    # 通缉状态
STATUS_HOSPITAL = 3  # 医院状态

# 银行抢劫队伍字典 {group_id: {"leader": leader_id, "members": [member_ids], "status": "waiting", "create_time": timestamp}}
# 每个群组只能同时存在一个抢银行行动
bank_robbery_teams: Dict[int, Dict] = {}

# 存款CD字典 {(group_id, user_id): timestamp}
deposit_cd: Dict[Tuple[int, int], float] = {}

# 保释CD字典 {(group_id, user_id): timestamp}
bail_cd: Dict[Tuple[int, int], float] = {}

# 通缉状态字典 {(group_id, user_id): {"attempts": int, "start_time": timestamp}}
wanted_status: Dict[Tuple[int, int], Dict] = {}

# 越狱尝试次数字典 {(group_id, user_id): int}
jailbreak_attempts: Dict[Tuple[int, int], int] = {}

# 被抢劫冷却时间字典 {(group_id, user_id): timestamp} - 记录用户被抢劫后的冷却结束时间
rob_cooldown: Dict[Tuple[int, int], float] = {}

# 每日银行可抢金额字典 {group_id: {"amount": float, "last_reset": date_string}}
# 每日随机生成50000-100000之间的金额，当金额归零时，所有用户不可以再抢银行
daily_bank_money: Dict[int, Dict[str, Union[float, str]]] = {}

def init_bank_db():
    """初始化银行数据库"""
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        # 创建银行账户表
        sql = """
        CREATE TABLE IF NOT EXISTS bank_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL,
            belonging_group INTEGER NOT NULL,
            balance REAL NOT NULL DEFAULT 0,
            UNIQUE(uid, belonging_group)
        )
        """
        cursor.execute(sql)
        
        # 创建用户状态表
        sql = """
        CREATE TABLE IF NOT EXISTS user_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL,
            belonging_group INTEGER NOT NULL,
            status INTEGER NOT NULL DEFAULT 0,  -- 0: 自由, 1: 监狱, 2: 通缉, 3: 医院
            release_time TIMESTAMP,             -- 释放时间
            UNIQUE(uid, belonging_group)
        )
        """
        cursor.execute(sql)
        
        conn.commit()
    finally:
        db_pool.return_connection(conn)

# 初始化数据库
init_bank_db()

def get_bank_balance(group_id: int, user_id: int) -> float:
    """获取用户银行余额"""
    # 先检查缓存
    cache_key = f"bank_balance_{group_id}_{user_id}"
    cached_value = cache_manager.get_cached_value(cache_key)
    if cached_value is not None:
        return cached_value
    
    # 从数据库获取
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        # 检查用户是否有银行账户，如果没有则创建
        sql = f"SELECT balance FROM bank_accounts WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            # 创建新账户
            sql = f"INSERT INTO bank_accounts (uid, belonging_group, balance) VALUES ({user_id}, {group_id}, 0)"
            cursor.execute(sql)
            conn.commit()
            balance = 0.0
        else:
            balance = float(result[0])
        
        # 更新缓存
        cache_manager.set_cached_value(cache_key, balance)
        
        return balance
    finally:
        db_pool.return_connection(conn)

def update_bank_balance(group_id: int, user_id: int, balance: float) -> None:
    """更新用户银行余额"""
    # 更新数据库
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        # 检查用户是否有银行账户，如果没有则创建
        sql = f"SELECT balance FROM bank_accounts WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            # 创建新账户
            sql = f"INSERT INTO bank_accounts (uid, belonging_group, balance) VALUES ({user_id}, {group_id}, {balance})"
        else:
            # 更新余额
            sql = f"UPDATE bank_accounts SET balance={balance} WHERE uid={user_id} AND belonging_group={group_id}"
        
        cursor.execute(sql)
        conn.commit()
        
        # 更新缓存
        cache_key = f"bank_balance_{group_id}_{user_id}"
        cache_manager.set_cached_value(cache_key, balance)
    finally:
        db_pool.return_connection(conn)

def get_user_status(group_id: int, user_id: int) -> Tuple[int, Optional[datetime.datetime]]:
    """获取用户状态和释放时间"""
    # 先检查缓存
    cache_key = f"user_status_{group_id}_{user_id}"
    cached_value = cache_manager.get_cached_value(cache_key)
    if cached_value is not None:
        status, release_time = cached_value
        # 检查是否已经过了释放时间
        if release_time and datetime.datetime.now() > release_time:
            # 自动释放
            status = STATUS_FREE
            release_time = None
            # 更新缓存
            cache_manager.set_cached_value(cache_key, (status, release_time))
        return status, release_time
    
    # 从数据库获取
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        # 检查用户状态
        sql = f"SELECT status, release_time FROM user_status WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result is None:
            # 创建新状态记录
            sql = f"INSERT INTO user_status (uid, belonging_group, status) VALUES ({user_id}, {group_id}, {STATUS_FREE})"
            cursor.execute(sql)
            conn.commit()
            status = STATUS_FREE
            release_time = None
        else:
            status = result[0]
            release_time = datetime.datetime.fromisoformat(result[1]) if result[1] else None
            
            # 检查是否已经过了释放时间
            if release_time and datetime.datetime.now() > release_time:
                # 自动释放（监狱、医院和通缉状态）
                sql = f"UPDATE user_status SET status={STATUS_FREE}, release_time=NULL WHERE uid={user_id} AND belonging_group={group_id}"
                cursor.execute(sql)
                conn.commit()
                status = STATUS_FREE
                release_time = None
                
                # 如果是通缉状态，清除通缉记录
                if status == STATUS_WANTED and (group_id, user_id) in wanted_status:
                    del wanted_status[(group_id, user_id)]
        
        # 更新缓存
        cache_manager.set_cached_value(cache_key, (status, release_time))
        
        return status, release_time
    finally:
        db_pool.return_connection(conn)

def update_user_status(group_id: int, user_id: int, status: int, release_time: Optional[datetime.datetime] = None) -> None:
    """更新用户状态"""
    # 更新数据库
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        
        # 检查用户是否有状态记录
        sql = f"SELECT id FROM user_status WHERE uid={user_id} AND belonging_group={group_id}"
        cursor.execute(sql)
        result = cursor.fetchone()
        
        release_time_str = f"'{release_time.isoformat()}'" if release_time else "NULL"
        
        if result is None:
            # 创建新状态记录
            sql = f"INSERT INTO user_status (uid, belonging_group, status, release_time) VALUES ({user_id}, {group_id}, {status}, {release_time_str})"
        else:
            # 更新状态
            sql = f"UPDATE user_status SET status={status}, release_time={release_time_str} WHERE uid={user_id} AND belonging_group={group_id}"
        
        cursor.execute(sql)
        conn.commit()
        
        # 更新缓存
        cache_key = f"user_status_{group_id}_{user_id}"
        cache_manager.set_cached_value(cache_key, (status, release_time))
    finally:
        db_pool.return_connection(conn)

def check_operation_allowed(group_id: int, user_id: int, allow_prison: bool = False, allow_hospital: bool = False, allow_wanted: bool = False) -> Tuple[bool, str]:
    """检查用户是否可以执行操作"""
    status, release_time = get_user_status(group_id, user_id)
    
    if status == STATUS_PRISON and not allow_prison:
        remaining_time = (release_time - datetime.datetime.now()).total_seconds() if release_time else 0
        minutes = int(remaining_time // 60)
        seconds = int(remaining_time % 60)
        return False, f"你正在监狱中，还有{minutes}分{seconds}秒才能出狱"
    
    if status == STATUS_HOSPITAL and not allow_hospital:
        remaining_time = (release_time - datetime.datetime.now()).total_seconds() if release_time else 0
        minutes = int(remaining_time // 60)
        seconds = int(remaining_time % 60)
        return False, f"你正在医院治疗，还有{minutes}分{seconds}秒才能出院"
    
    if status == STATUS_WANTED and not allow_wanted:
        return False, "你正处于通缉状态，无法执行此操作"
    
    return True, ""

# 定期清理缓存的函数
def clear_cache():
    # 清理银行相关缓存
    cache_manager.clear_cache("bank_balance_")
    cache_manager.clear_cache("user_status_")

# 导入定时器
import asyncio

# 定期清理缓存（每5分钟）
async def schedule_cache_clear():
    while True:
        await asyncio.sleep(300)
        clear_cache()

def deposit(group_id: int, user_id: int, amount: float) -> str:
    """存款操作"""
    # 检查用户状态
    allowed, message = check_operation_allowed(group_id, user_id)
    if not allowed:
        return message
    
    # 检查CD
    current_time = time.time()
    if (group_id, user_id) in deposit_cd:
        last_time = deposit_cd[(group_id, user_id)]
        if current_time - last_time < 10:  # 10秒CD
            return f"存款操作冷却中，请{int(10 - (current_time - last_time))}秒后再试"
    
    # 检查金币是否足够
    from .sign import get_point, update_point
    active_coins = get_point(group_id, user_id)
    
    if active_coins < amount:
        return f"你的活动金币不足，当前余额：{active_coins}"
    
    # 更新活动金币和银行余额，保留两位小数
    bank_balance = get_bank_balance(group_id, user_id)
    # 四舍五入到两位小数
    new_active_coins = round(active_coins - amount, 2)
    new_bank_balance = round(bank_balance + amount, 2)
    
    update_point(group_id, user_id, new_active_coins)
    update_bank_balance(group_id, user_id, new_bank_balance)
    
    # 更新CD
    deposit_cd[(group_id, user_id)] = current_time
    
    return f"存款成功！已将{amount}金币存入银行，当前活动金币：{new_active_coins}，银行余额：{new_bank_balance}"

def withdraw(group_id: int, user_id: int, amount: float) -> str:
    """取款操作"""
    # 检查用户状态
    allowed, message = check_operation_allowed(group_id, user_id)
    if not allowed:
        return message
    
    # 检查银行余额是否足够
    bank_balance = get_bank_balance(group_id, user_id)
    
    if bank_balance < amount:
        return f"你的银行余额不足，当前银行余额：{bank_balance}"
    
    # 更新活动金币和银行余额，保留两位小数
    from .sign import get_point, update_point
    active_coins = get_point(group_id, user_id)
    
    # 四舍五入到两位小数
    new_active_coins = round(active_coins + amount, 2)
    new_bank_balance = round(bank_balance - amount, 2)
    
    update_point(group_id, user_id, new_active_coins)
    update_bank_balance(group_id, user_id, new_bank_balance)
    
    return f"取款成功！已从银行取出{amount}金币，当前活动金币：{new_active_coins}，银行余额：{new_bank_balance}"

def transfer(group_id: int, from_user_id: int, to_user_id: int, amount: float) -> str:
    """转账操作"""
    # 检查用户状态
    allowed, message = check_operation_allowed(group_id, from_user_id)
    if not allowed:
        return message
    
    # 检查是否自己转给自己
    if from_user_id == to_user_id:
        return "不能给自己转账"
    
    # 检查银行余额是否足够
    bank_balance = get_bank_balance(group_id, from_user_id)
    
    if bank_balance < amount:
        return f"你的银行余额不足，当前银行余额：{bank_balance}"
    
    # 获取接收方余额
    to_bank_balance = get_bank_balance(group_id, to_user_id)
    
    # 更新双方银行余额，保留两位小数
    new_from_balance = round(bank_balance - amount, 2)
    new_to_balance = round(to_bank_balance + amount, 2)
    
    update_bank_balance(group_id, from_user_id, new_from_balance)
    update_bank_balance(group_id, to_user_id, new_to_balance)
    
    return f"转账成功！已向对方转账{amount}金币，当前银行余额：{new_from_balance}"

def check_balance(group_id: int, user_id: int) -> str:
    """查询余额"""
    from .sign import get_point
    active_coins = get_point(group_id, user_id)
    bank_balance = get_bank_balance(group_id, user_id)
    total_assets = active_coins + bank_balance
    
    return f"当前余额：\n活动金币：{active_coins:.2f}\n银行存款：{bank_balance:.2f}\n总资产：{total_assets:.2f}"

def rob_user(group_id: int, robber_id: int, victim_id: int) -> str:
    """抢劫用户"""
    # 检查抢劫者状态
    allowed, message = check_operation_allowed(group_id, robber_id)
    if not allowed:
        return message
    
    # 检查被抢劫者状态
    victim_status, _ = get_user_status(group_id, victim_id)
    if victim_status != STATUS_FREE:
        return "对方当前无法被抢劫"
    
    # 检查被抢劫者是否在冷却时间内
    current_time = time.time()
    if (group_id, victim_id) in rob_cooldown:
        cooldown_end_time = rob_cooldown[(group_id, victim_id)]
        if current_time < cooldown_end_time:
            remaining_time = int(cooldown_end_time - current_time)
            minutes = remaining_time // 60
            seconds = remaining_time % 60
            return f"该用户在{minutes}分{seconds}秒内不能被抢劫，请选择其他目标"
    
    # 获取双方金币
    from .sign import get_point, update_point
    robber_active = get_point(group_id, robber_id)
    victim_active = get_point(group_id, victim_id)
    
    if victim_active <= 0:
        return "对方没有活动金币可抢"
    
    # 计算抢劫成功率（线性插值：差值1-100000，对应概率100%~0.01%）
    robber_total = robber_active + get_bank_balance(group_id, robber_id)
    victim_total = victim_active + get_bank_balance(group_id, victim_id)
    
    diff = abs(victim_total - robber_total)
    success_rate = max(0.0001, min(1.0, 1.0 - (diff / 100000) * 0.9999))
    
    # 判断抢劫是否成功
    if random.random() < success_rate:
        # 抢劫成功，随机获得被抢劫者1%~15%的活动金币
        rob_percent = random.uniform(0.01, 0.15)
        rob_amount = round(victim_active * rob_percent, 2)
        
        # 更新金币
        update_point(group_id, robber_id, robber_active + rob_amount)
        update_point(group_id, victim_id, victim_active - rob_amount)
        
        # 设置被抢劫者的冷却时间（5分钟）
        rob_cooldown[(group_id, victim_id)] = time.time() + 300  # 5分钟 = 300秒
        
        return f"抢劫成功！你抢到了对方{rob_amount}金币（{rob_percent*100:.1f}%的活动金币）"
    else:
        # 抢劫失败，罚款总金额的5%，并关进监狱5分钟
        robber_bank = get_bank_balance(group_id, robber_id)
        fine = round((robber_active + robber_bank) * 0.05, 2)
        
        # 更新金币和状态
        if fine <= robber_active:
            update_point(group_id, robber_id, robber_active - fine)
        else:
            # 如果活动金币不足以支付罚款，从银行扣除
            remaining_fine = fine - robber_active
            update_point(group_id, robber_id, 0)
            update_bank_balance(group_id, robber_id, max(0, robber_bank - remaining_fine))
        
        # 关进监狱5分钟
        release_time = datetime.datetime.now() + datetime.timedelta(minutes=5)
        update_user_status(group_id, robber_id, STATUS_PRISON, release_time)
        
        # 重置越狱尝试次数
        if (group_id, robber_id) in jailbreak_attempts:
            jailbreak_attempts[(group_id, robber_id)] = 0
        
        return f"抢劫失败！你被罚款{fine}金币，并被关进监狱5分钟"

def check_team_timeout(group_id: int) -> bool:
    """检查抢银行队伍是否超时（5分钟）"""
    if group_id not in bank_robbery_teams:
        return False
    
    team = bank_robbery_teams[group_id]
    if "create_time" not in team:
        return False
    
    # 检查是否超过5分钟（300秒）
    current_time = time.time()
    if current_time - team["create_time"] > 300:
        # 超时，清除队伍
        del bank_robbery_teams[group_id]
        return True
    
    return False

def start_bank_robbery_team(group_id: int, leader_id: int) -> str:
    """发起抢银行组队 - 每个群组只能同时存在一个抢银行行动"""
    # 检查用户状态
    allowed, message = check_operation_allowed(group_id, leader_id)
    if not allowed:
        return message
    
    # 检查是否已经存在抢银行队伍
    if group_id in bank_robbery_teams:
        # 检查现有队伍是否超时
        if check_team_timeout(group_id):
            # 如果超时已被清除，继续创建新队伍
            pass
        else:
            # 如果用户已经在队伍中
            if leader_id in bank_robbery_teams[group_id]["members"]:
                return "你已经在抢银行队伍中了"
            # 如果队伍已存在但用户不在队伍中
            return "已经有一个抢银行队伍在等待中，请使用'加入'命令加入现有队伍"
    
    # 创建新队伍
    bank_robbery_teams[group_id] = {
        "leader": leader_id,
        "members": [leader_id],
        "status": "waiting",
        "create_time": time.time()  # 添加创建时间
    }
    
    return f"抢银行队伍创建成功！\n其他人可以使用'加入'命令加入队伍\n当人数达到要求后，队长可以发送'开始抢'开始行动\n注意：队伍将在5分钟后自动解散"

def join_bank_robbery_team(group_id: int, user_id: int) -> str:
    """加入抢银行队伍 - 加入当前群组中唯一的抢银行行动"""
    # 检查用户状态
    allowed, message = check_operation_allowed(group_id, user_id)
    if not allowed:
        return message
    
    # 检查队伍是否存在
    if group_id not in bank_robbery_teams:
        return "当前没有抢银行队伍，请先使用'抢银行'命令创建队伍"
    
    team = bank_robbery_teams[group_id]
    
    # 检查队伍状态
    if team["status"] != "waiting":
        return "队伍已经开始行动，无法加入"
    
    # 检查是否已经在队伍中
    if user_id in team["members"]:
        return "你已经在队伍中了"
    
    # 检查队伍是否已满
    if len(team["members"]) >= 10:
        return "队伍已满，无法加入"
    
    # 加入队伍
    team["members"].append(user_id)
    
    return f"成功加入抢银行队伍！当前队伍人数：{len(team['members'])}/10"

def get_daily_bank_money(group_id: int) -> float:
    """获取每日银行可抢金额，如果是新的一天则重置金额"""
    today = datetime.date.today().isoformat()
    
    # 检查是否需要初始化或重置
    if group_id not in daily_bank_money or daily_bank_money[group_id]["last_reset"] != today:
        # 随机生成50000-100000之间的金额
        amount = random.randint(50000, 100000)
        daily_bank_money[group_id] = {"amount": amount, "last_reset": today}
        return amount
    
    return daily_bank_money[group_id]["amount"]

def update_daily_bank_money(group_id: int, amount: float) -> None:
    """更新每日银行可抢金额"""
    if group_id in daily_bank_money:
        daily_bank_money[group_id]["amount"] = max(0, amount)

def start_bank_robbery(group_id: int, user_id: int) -> str:
    """开始抢银行行动 - 开始当前群组中唯一的抢银行行动"""
    # 检查队伍是否存在
    if group_id not in bank_robbery_teams:
        return "当前没有抢银行队伍，请先使用'抢银行'命令创建队伍"
    
    team = bank_robbery_teams[group_id]
    
    # 检查是否是队长
    if team["leader"] != user_id:
        return "只有队长才能开始抢银行行动"
    
    # 检查队伍状态
    if team["status"] != "waiting":
        return "该队伍已经开始行动"
    
    # 检查队伍人数
    if len(team["members"]) < 2:
        return "抢银行队伍至少需要2人才能开始行动"
    
    # 检查所有成员状态
    for member_id in team["members"]:
        allowed, message = check_operation_allowed(group_id, member_id)
        if not allowed:
            return f"队伍中有成员无法参与行动：{message}"
    
    # 检查每日银行可抢金额
    remaining_money = get_daily_bank_money(group_id)
    if remaining_money <= 0:
        # 删除队伍
        del bank_robbery_teams[group_id]
        return "今日银行金库已被抢空，请明天再来！"
    
    # 生成本次可抢银行金额（1000~20000，但不超过剩余金额）
    bank_money = min(random.randint(1000, 20000), remaining_money)
    
    # 计算成功率
    # 基础成功率50%，根据银行金额线性降低，最低5%
    base_success_rate = 0.5
    money_factor = (bank_money - 1000) / 19000  # 0~1范围
    success_rate = max(0.05, base_success_rate - money_factor * 0.45)  # 最低5%
    
    # 人数因素：超过5人后，每多一人降低2.5%，最多降低10%
    if len(team["members"]) > 5:
        extra_members = len(team["members"]) - 5
        penalty = min(0.1, extra_members * 0.025)  # 最多降低10%
        success_rate = max(0.05, success_rate - penalty)  # 综合成功率不低于5%
    
    # 导入重置消耗记录的函数
    from .chip_purchase_limit import reset_consumption_records
    
    # 为所有参与者重置筹码消耗记录（无论抢银行成功与否）
    for member_id in team["members"]:
        reset_consumption_records(group_id, member_id)
    
    # 更新每日银行可抢金额
    update_daily_bank_money(group_id, remaining_money - bank_money)
    
    # 判断是否成功
    if random.random() < success_rate:
        # 抢银行成功，判断结果类型
        
        # 计算利益均沾和贫富不均的概率
        equal_share_prob = 0.7
        unequal_share_prob = 0.2
        
        # 当抢银行人数超过3人时，每多一人，贫富不均概率提高5%，最多提高25%
        if len(team["members"]) > 3:
            extra_members = len(team["members"]) - 3
            prob_shift = min(0.25, extra_members * 0.05)  # 最多提高25%
            unequal_share_prob = min(0.9, unequal_share_prob + prob_shift)  # 不超过90%
            equal_share_prob = 0.9 - unequal_share_prob  # 保持和为90%
        
        # 随机决定结果类型
        result_roll = random.random()
        
        if result_roll < equal_share_prob:  # 利益均沾
            # 所有参与人员均分所得金币
            share_per_person = round(bank_money / len(team["members"]), 2)
            
            # 更新所有成员的金币
            from .sign import get_point, update_point
            result_message = "抢银行成功！利益均沾！\n"
            result_message += f"银行金额：{bank_money}金币\n"
            result_message += f"每人分得：{share_per_person}金币\n"
            result_message += f"今日银行剩余金额：{daily_bank_money[group_id]['amount']:.2f}金币\n"
            result_message += "参与成员：\n"
            
            for member_id in team["members"]:
                active_coins = get_point(group_id, member_id)
                update_point(group_id, member_id, active_coins + share_per_person)
                result_message += f"用户{member_id}获得{share_per_person}金币\n"
            
            # 删除队伍
            del bank_robbery_teams[group_id]
            return result_message
            
        elif result_roll < equal_share_prob + unequal_share_prob:  # 贫富不均
            # 随机一人获得全部金币，其他人进医院
            lucky_member = random.choice(team["members"])
            
            # 更新幸运者的金币
            from .sign import get_point, update_point
            active_coins = get_point(group_id, lucky_member)
            update_point(group_id, lucky_member, active_coins + bank_money)
            
            # 其他人进医院并支付医药费
            result_message = "抢银行成功但分赃不均！\n"
            result_message += f"银行金额：{bank_money}金币\n"
            result_message += f"用户{lucky_member}独吞了所有金币！\n"
            result_message += f"今日银行剩余金额：{daily_bank_money[group_id]['amount']:.2f}金币\n"
            result_message += "其他成员因争抢受伤进了医院：\n"
            
            for member_id in team["members"]:
                if member_id != lucky_member:
                    # 计算医药费（银行存款的5%）
                    bank_balance = get_bank_balance(group_id, member_id)
                    medical_fee = round(bank_balance * 0.05, 2)
                    
                    # 扣除医药费
                    update_bank_balance(group_id, member_id, bank_balance - medical_fee)
                    
                    # 进入医院状态
                    release_time = datetime.datetime.now() + datetime.timedelta(minutes=5)
                    update_user_status(group_id, member_id, STATUS_HOSPITAL, release_time)
                    
                    result_message += f"用户{member_id}支付医药费{medical_fee}金币，住院5分钟\n"
            
            # 删除队伍
            del bank_robbery_teams[group_id]
            return result_message
            
        else:  # 法网恢恢
            # 所有参与人员罚款总金额的15%且关进监狱15分钟
            result_message = "抢银行过程中被警察抓获！法网恢恢！\n"
            result_message += f"今日银行剩余金额：{daily_bank_money[group_id]['amount']:.2f}金币\n"
            result_message += "所有参与成员：\n"
            
            from .sign import get_point, update_point
            for member_id in team["members"]:
                # 计算罚款（总金额的15%）
                active_coins = get_point(group_id, member_id)
                bank_balance = get_bank_balance(group_id, member_id)
                fine = round((active_coins + bank_balance) * 0.15, 2)
                
                # 扣除罚款
                if fine <= active_coins:
                    update_point(group_id, member_id, active_coins - fine)
                    result_message += f"用户{member_id}被罚款{fine}金币\n"
                else:
                    # 如果活动金币不足以支付罚款，从银行扣除
                    remaining_fine = fine - active_coins
                    update_point(group_id, member_id, 0)
                    update_bank_balance(group_id, member_id, max(0, bank_balance - remaining_fine))
                    result_message += f"用户{member_id}被罚款{fine}金币（活动金币不足，从银行扣除{remaining_fine}金币）\n"
                
                # 关进监狱15分钟
                release_time = datetime.datetime.now() + datetime.timedelta(minutes=15)
                update_user_status(group_id, member_id, STATUS_PRISON, release_time)
                
                # 重置越狱尝试次数
                if (group_id, member_id) in jailbreak_attempts:
                    jailbreak_attempts[(group_id, member_id)] = 0
            
            # 删除队伍
            del bank_robbery_teams[group_id]
            return result_message
    else:
        # 抢银行失败，所有参与人员罚款总金额的10%且关进监狱10分钟
        result_message = "抢银行失败！被警察抓获！\n"
        result_message += f"今日银行剩余金额：{daily_bank_money[group_id]['amount']:.2f}金币\n"
        result_message += "所有参与成员：\n"
        
        from .sign import get_point, update_point
        for member_id in team["members"]:
            # 计算罚款（总金额的10%）
            active_coins = get_point(group_id, member_id)
            bank_balance = get_bank_balance(group_id, member_id)
            fine = round((active_coins + bank_balance) * 0.1, 2)
            
            # 扣除罚款
            if fine <= active_coins:
                update_point(group_id, member_id, active_coins - fine)
                result_message += f"用户{member_id}被罚款{fine}金币\n"
            else:
                # 如果活动金币不足以支付罚款，从银行扣除
                remaining_fine = fine - active_coins
                update_point(group_id, member_id, 0)
                update_bank_balance(group_id, member_id, max(0, bank_balance - remaining_fine))
                result_message += f"用户{member_id}被罚款{fine}金币（活动金币不足，从银行扣除{remaining_fine}金币）\n"
            
            # 关进监狱10分钟
            release_time = datetime.datetime.now() + datetime.timedelta(minutes=10)
            update_user_status(group_id, member_id, STATUS_PRISON, release_time)
            
            # 重置越狱尝试次数
            if (group_id, member_id) in jailbreak_attempts:
                jailbreak_attempts[(group_id, member_id)] = 0
        
        # 删除队伍
        del bank_robbery_teams[group_id]
        return result_message

def bail_out(group_id: int, bailer_id: int, prisoner_id: int) -> str:
    """保释操作"""
    # 检查保释者状态
    allowed, message = check_operation_allowed(group_id, bailer_id)
    if not allowed:
        return message
    
    # 检查被保释者状态
    prisoner_status, release_time = get_user_status(group_id, prisoner_id)
    if prisoner_status != STATUS_PRISON:
        return "对方不在监狱中，无需保释"
    
    # 检查保释CD
    current_time = time.time()
    if (group_id, prisoner_id) in bail_cd:
        last_time = bail_cd[(group_id, prisoner_id)]
        if current_time - last_time < 1800:  # 30分钟CD
            minutes = int((1800 - (current_time - last_time)) // 60)
            seconds = int((1800 - (current_time - last_time)) % 60)
            return f"该用户在{minutes}分{seconds}秒内不能被保释"
    
    # 计算保释金额
    base_bail = 500
    
    # 如果是通缉状态被抓，保释金额为基础金额的3倍
    if (group_id, prisoner_id) in wanted_status and wanted_status[(group_id, prisoner_id)].get("caught", False):
        bail_amount = base_bail * 3
    else:
        bail_amount = base_bail
    
    # 检查保释者金币是否足够
    from .sign import get_point, update_point
    bailer_active = get_point(group_id, bailer_id)
    
    # 先检查金额是否足够，避免先扣除后发现不足
    if bailer_active < bail_amount:
        return f"你的活动金币不足以支付保释金，需要{bail_amount}金币，当前余额：{bailer_active}"
    
    # 确认金额足够后再扣除
    new_balance = round(bailer_active - bail_amount, 2)  # 保留两位小数
    update_point(group_id, bailer_id, new_balance)
    
    # 释放囚犯
    update_user_status(group_id, prisoner_id, STATUS_FREE)
    
    # 清除通缉状态记录（如果存在）
    if (group_id, prisoner_id) in wanted_status:
        del wanted_status[(group_id, prisoner_id)]
    
    # 更新保释CD
    bail_cd[(group_id, prisoner_id)] = current_time
    
    return f"保释成功！你支付了{bail_amount}金币将用户{prisoner_id}保释出狱"

def bail(group_id: int, bailer_id: int, prisoner_id: int) -> str:
    """保释操作（bail_out的别名）
    允许用户支付一定金额将监狱中的其他用户保释出来
    
    Args:
        group_id: 群组ID
        bailer_id: 保释者ID
        prisoner_id: 被保释者ID
        
    Returns:
        str: 保释结果消息
    """
    return bail_out(group_id, bailer_id, prisoner_id)

def jailbreak(group_id: int, user_id: int) -> str:
    """越狱操作"""
    # 检查用户状态
    status, release_time = get_user_status(group_id, user_id)
    if status != STATUS_PRISON:
        return "你不在监狱中，无需越狱"
    
    # 检查是否是通缉状态被抓
    if (group_id, user_id) in wanted_status and wanted_status[(group_id, user_id)].get("caught", False):
        return "你是因通缉被抓，无法越狱"
    
    # 检查越狱尝试次数
    if (group_id, user_id) not in jailbreak_attempts:
        jailbreak_attempts[(group_id, user_id)] = 0
    
    if jailbreak_attempts[(group_id, user_id)] >= 3:
        return "你已经尝试越狱3次，无法继续尝试"
    
    # 增加越狱尝试次数
    jailbreak_attempts[(group_id, user_id)] += 1
    
    # 50%概率越狱成功
    if random.random() < 0.5:
        # 越狱成功，进入通缉状态，设置2分钟后自动释放
        release_time = datetime.datetime.now() + datetime.timedelta(minutes=2)
        update_user_status(group_id, user_id, STATUS_WANTED, release_time)
        
        # 初始化通缉状态
        # 计算悬赏金额（总资产的50%）
        from .sign import get_point
        active_coins = get_point(group_id, user_id)
        bank_balance = get_bank_balance(group_id, user_id)
        bounty = round((active_coins + bank_balance) * 0.5, 2)
        
        wanted_status[(group_id, user_id)] = {
            "attempts": 0,
            "start_time": time.time(),
            "caught": False,
            "bounty": bounty
        }
        
        # 计算悬赏金额（总资产的50%），但不立即扣除
        from .sign import get_point
        active_coins = get_point(group_id, user_id)
        bank_balance = get_bank_balance(group_id, user_id)
        bounty = round((active_coins + bank_balance) * 0.5, 2)
        
        # 将悬赏金额保存在通缉状态中，但不立即扣除
        wanted_status[(group_id, user_id)]["bounty"] = bounty
        
        return f"越狱成功！但你已进入通缉状态，2分钟内无法进行除签到外的任何操作，且被悬赏{bounty}金币"
    else:
        # 越狱失败，重置关押时间
        release_time = datetime.datetime.now() + datetime.timedelta(minutes=5)
        update_user_status(group_id, user_id, STATUS_PRISON, release_time)
        
        return f"越狱失败！你被重新关押，关押时间重置为5分钟，已尝试{jailbreak_attempts[(group_id, user_id)]}/3次"

def catch_wanted(group_id: int, catcher_id: int, wanted_id: int) -> str:
    """抓捕通缉犯"""
    # 检查抓捕者状态
    allowed, message = check_operation_allowed(group_id, catcher_id)
    if not allowed:
        return message
    
    # 检查被抓捕者状态
    wanted_user_status, _ = get_user_status(group_id, wanted_id)
    if wanted_user_status != STATUS_WANTED:
        return "对方不是通缉犯，无法抓捕"
    
    # 检查通缉状态
    if (group_id, wanted_id) not in wanted_status:
        # 如果没有通缉状态记录，创建一个
        # 计算悬赏金额（总资产的50%）
        from .sign import get_point
        wanted_active = get_point(group_id, wanted_id)
        wanted_bank = get_bank_balance(group_id, wanted_id)
        bounty = round((wanted_active + wanted_bank) * 0.5, 2)
        
        wanted_status[(group_id, wanted_id)] = {
            "attempts": 0,
            "start_time": time.time(),
            "caught": False,
            "bounty": bounty
        }
    
    # 检查抓捕尝试次数
    if wanted_status[(group_id, wanted_id)]["attempts"] >= 3:
        # 自动退出通缉状态
        update_user_status(group_id, wanted_id, STATUS_FREE)
        del wanted_status[(group_id, wanted_id)]
        return "该通缉犯已经被尝试抓捕3次，已自动退出通缉状态"
    
    # 检查通缉时间是否已过2分钟
    current_time = time.time()
    if current_time - wanted_status[(group_id, wanted_id)]["start_time"] > 120:  # 2分钟
        # 自动退出通缉状态
        update_user_status(group_id, wanted_id, STATUS_FREE)
        del wanted_status[(group_id, wanted_id)]
        return "该通缉犯的通缉时间已过，已自动退出通缉状态"
    
    # 增加抓捕尝试次数
    wanted_status[(group_id, wanted_id)]["attempts"] += 1
    
    # 20%概率抓捕成功
    if random.random() < 0.2:
        # 抓捕成功，关进监狱20分钟
        release_time = datetime.datetime.now() + datetime.timedelta(minutes=20)
        update_user_status(group_id, wanted_id, STATUS_PRISON, release_time)
        
        # 标记为通缉状态被抓
        wanted_status[(group_id, wanted_id)]["caught"] = True
        
        # 获取之前计算的悬赏金额
        from .sign import get_point, update_point
        bounty = wanted_status[(group_id, wanted_id)].get("bounty", 0)
        
        if bounty > 0:
            # 从被抓捕者扣除悬赏金额
            wanted_active = get_point(group_id, wanted_id)
            wanted_bank = get_bank_balance(group_id, wanted_id)
            
            # 扣除悬赏金额
            if bounty <= wanted_active:
                update_point(group_id, wanted_id, wanted_active - bounty)
            else:
                # 如果活动金币不足以支付悬赏，从银行扣除
                remaining_bounty = bounty - wanted_active
                update_point(group_id, wanted_id, 0)
                update_bank_balance(group_id, wanted_id, max(0, wanted_bank - remaining_bounty))
            
            # 给予抓捕者奖励
            catcher_active = get_point(group_id, catcher_id)
            update_point(group_id, catcher_id, catcher_active + bounty)
        
        return f"抓捕成功！你获得了{bounty}金币的悬赏奖励，通缉犯被关进监狱20分钟"
    else:
        # 抓捕失败
        if wanted_status[(group_id, wanted_id)]["attempts"] >= 3:
            # 如果已经尝试3次，自动退出通缉状态
            update_user_status(group_id, wanted_id, STATUS_FREE)
            del wanted_status[(group_id, wanted_id)]
            return f"抓捕失败！该通缉犯已经被尝试抓捕3次，已自动退出通缉状态"
        else:
            remaining_attempts = 3 - wanted_status[(group_id, wanted_id)]["attempts"]
            return f"抓捕失败！该通缉犯还可以被尝试抓捕{remaining_attempts}次"

def jail_break_all(group_id: int, user_id: int) -> str:
    """劫狱操作"""
    # 检查用户状态
    allowed, message = check_operation_allowed(group_id, user_id)
    if not allowed:
        return message
    
    # 50%概率劫狱成功
    if random.random() < 0.5:
        # 劫狱成功，释放所有在押人员
        conn = None
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            
            # 查询所有在押人员
            sql = f"SELECT uid FROM user_status WHERE belonging_group={group_id} AND status={STATUS_PRISON}"
            cursor.execute(sql)
            prisoners = cursor.fetchall()
        finally:
            if conn:
                conn.close()
        
        if not prisoners:
            return "当前没有人在监狱中，劫狱失败"
        
        # 释放所有在押人员
        result_message = "劫狱成功！释放了以下人员：\n"
        for prisoner in prisoners:
            prisoner_id = prisoner[0]
            update_user_status(group_id, prisoner_id, STATUS_FREE)
            
            # 清除通缉状态记录（如果存在）
            if (group_id, prisoner_id) in wanted_status:
                del wanted_status[(group_id, prisoner_id)]
                
            result_message += f"用户{prisoner_id}\n"
        
        return result_message
    else:
        # 劫狱失败，自身被关押10分钟，罚款总金额的10%
        from .sign import get_point, update_point
        active_coins = get_point(group_id, user_id)
        bank_balance = get_bank_balance(group_id, user_id)
        fine = round((active_coins + bank_balance) * 0.1, 2)
        
        # 扣除罚款
        if fine <= active_coins:
            update_point(group_id, user_id, active_coins - fine)
        else:
            # 如果活动金币不足以支付罚款，从银行扣除
            remaining_fine = fine - active_coins
            update_point(group_id, user_id, 0)
            update_bank_balance(group_id, user_id, max(0, bank_balance - remaining_fine))
        
        # 关进监狱10分钟
        release_time = datetime.datetime.now() + datetime.timedelta(minutes=10)
        update_user_status(group_id, user_id, STATUS_PRISON, release_time)
        
        # 重置越狱尝试次数
        if (group_id, user_id) in jailbreak_attempts:
            jailbreak_attempts[(group_id, user_id)] = 0
        
        return f"劫狱失败！你被罚款{fine}金币，并被关进监狱10分钟"


def heal(group_id: int, user_id: int) -> str:
    """医院治疗"""
    # 检查用户状态
    status, release_time = get_user_status(group_id, user_id)
    if status != STATUS_HOSPITAL:
        return "你不在医院中，无需治疗"
    
    # 计算治疗费用（总资产的3%）
    from .sign import get_point, update_point
    active_coins = get_point(group_id, user_id)
    bank_balance = get_bank_balance(group_id, user_id)
    fee = round((active_coins + bank_balance) * 0.03, 2)
    
    # 先检查金额是否足够，避免先扣除后发现不足
    if active_coins < fee:
        return f"你的活动金币不足以支付治疗费用，需要{fee}金币，当前余额：{active_coins}"
    
    # 确认金额足够后再扣除
    new_balance = round(active_coins - fee, 2)  # 保留两位小数
    update_point(group_id, user_id, new_balance)
    
    # 释放用户
    update_user_status(group_id, user_id, STATUS_FREE)
    
    return f"治疗成功！你支付了{fee}金币的治疗费用，已出院"


# 抢劫队伍字典 {group_id: {team_id: {"leader": leader_id, "members": [member_ids], "status": "waiting", "target": target_id}}}
robbery_teams: Dict[int, Dict[int, Dict]] = {}

# 抢劫CD字典 {(group_id, user_id): timestamp}
robbery_cd: Dict[Tuple[int, int], float] = {}

# 抢劫队伍ID计数器 {group_id: int}
robbery_team_id_counter: Dict[int, int] = {}


def create_robbery_team(group_id: int, user_id: int) -> str:
    """创建抢劫队伍"""
    # 检查用户状态
    allowed, message = check_operation_allowed(group_id, user_id)
    if not allowed:
        return message
    
    # 检查CD
    current_time = time.time()
    if (group_id, user_id) in robbery_cd:
        last_time = robbery_cd[(group_id, user_id)]
        if current_time - last_time < 300:  # 5分钟CD
            remaining = int(300 - (current_time - last_time))
            return f"抢劫冷却中，请{remaining}秒后再试"
    
    # 初始化抢劫队伍字典
    if group_id not in robbery_teams:
        robbery_teams[group_id] = {}
        robbery_team_id_counter[group_id] = 0
    
    # 检查是否已经在队伍中
    for team_id, team in robbery_teams[group_id].items():
        if user_id in team["members"]:
            return "你已经在一个抢劫队伍中了"
    
    # 创建新队伍
    robbery_team_id_counter[group_id] += 1
    team_id = robbery_team_id_counter[group_id]
    robbery_teams[group_id][team_id] = {
        "leader": user_id,
        "members": [user_id],
        "status": "waiting",
        "target": None
    }
    
    return f"抢劫队伍创建成功！队伍ID：{team_id}\n其他人可以使用'加入抢劫 {team_id}'加入队伍\n当人数达到要求后，队长可以发送'开始抢劫 目标ID'开始行动"


def join_robbery_team(group_id: int, user_id: int, team_id: int) -> str:
    """加入抢劫队伍"""
    # 检查用户状态
    allowed, message = check_operation_allowed(group_id, user_id)
    if not allowed:
        return message
    
    # 检查队伍是否存在
    if group_id not in robbery_teams or team_id not in robbery_teams[group_id]:
        return "指定的抢劫队伍不存在"
    
    team = robbery_teams[group_id][team_id]
    
    # 检查队伍状态
    if team["status"] != "waiting":
        return "该队伍已经开始行动，无法加入"
    
    # 检查是否已经在队伍中
    if user_id in team["members"]:
        return "你已经在这个队伍中了"
    
    # 检查队伍是否已满
    if len(team["members"]) >= 5:  # 最多5人
        return "队伍已满，无法加入"
    
    # 检查是否已经在其他队伍中
    for other_team_id, other_team in robbery_teams[group_id].items():
        if user_id in other_team["members"] and other_team_id != team_id:
            return "你已经在另一个抢劫队伍中了"
    
    # 加入队伍
    team["members"].append(user_id)
    
    return f"成功加入抢劫队伍！当前队伍人数：{len(team['members'])}/5"


def start_robbery(group_id: int, user_id: int, team_id: int, target_id: int) -> str:
    """开始抢劫行动"""
    # 检查队伍是否存在
    if group_id not in robbery_teams or team_id not in robbery_teams[group_id]:
        return "指定的抢劫队伍不存在"
    
    team = robbery_teams[group_id][team_id]
    
    # 检查是否是队长
    if team["leader"] != user_id:
        return "只有队长才能开始抢劫行动"
    
    # 检查队伍状态
    if team["status"] != "waiting":
        return "该队伍已经开始行动"
    
    # 检查队伍人数
    if len(team["members"]) < 1:  # 至少1人
        return "抢劫队伍至少需要1人才能开始行动"
    
    # 检查目标是否是自己
    if target_id in team["members"]:
        return "不能抢劫队伍成员"
    
    # 检查目标状态
    target_status, _ = get_user_status(group_id, target_id)
    if target_status != STATUS_FREE:
        return "目标当前无法被抢劫"
    
    # 检查所有成员状态
    for member_id in team["members"]:
        allowed, message = check_operation_allowed(group_id, member_id)
        if not allowed:
            return f"队伍中有成员无法参与行动：{message}"
    
    # 获取目标金币
    from .sign import get_point, update_point
    target_active = get_point(group_id, target_id)
    target_bank = get_bank_balance(group_id, target_id)
    
    if target_active <= 0:
        return "目标没有活动金币可抢"
    
    # 计算抢劫成功率
    # 基础成功率60%，每多一人增加5%，最高80%
    base_success_rate = 0.6
    member_bonus = min(0.2, (len(team["members"]) - 1) * 0.05)  # 最多增加20%
    success_rate = base_success_rate + member_bonus
    
    # 计算队伍总资产和目标总资产
    team_total_assets = 0
    for member_id in team["members"]:
        member_active = get_point(group_id, member_id)
        member_bank = get_bank_balance(group_id, member_id)
        team_total_assets += member_active + member_bank
    
    target_total_assets = target_active + target_bank
    
    # 如果目标资产是队伍资产的10倍以上，成功率降低20%
    if target_total_assets > team_total_assets * 10:
        success_rate = max(0.1, success_rate - 0.2)  # 最低10%
    
    # 更新队伍状态
    team["status"] = "robbing"
    team["target"] = target_id
    
    # 判断是否成功
    if random.random() < success_rate:
        # 抢劫成功，随机获得目标10%~30%的活动金币
        rob_percent = random.uniform(0.1, 0.3)
        rob_amount = round(target_active * rob_percent, 2)
        
        # 更新目标金币
        update_point(group_id, target_id, target_active - rob_amount)
        
        # 分配抢劫所得
        share_per_person = round(rob_amount / len(team["members"]), 2)
        
        result_message = "抢劫成功！\n"
        result_message += f"从目标获得了{rob_amount}金币（{rob_percent*100:.1f}%的活动金币）\n"
        result_message += f"每人分得：{share_per_person}金币\n"
        result_message += "参与成员：\n"
        
        for member_id in team["members"]:
            member_active = get_point(group_id, member_id)
            update_point(group_id, member_id, member_active + share_per_person)
            result_message += f"用户{member_id}获得{share_per_person}金币\n"
            
            # 更新抢劫CD
            robbery_cd[(group_id, member_id)] = time.time()
        
        # 删除队伍
        del robbery_teams[group_id][team_id]
        
        return result_message
    else:
        # 抢劫失败，所有参与人员罚款总金额的5%且关进监狱5分钟
        result_message = "抢劫失败！被警察抓获！\n"
        result_message += "所有参与成员：\n"
        
        for member_id in team["members"]:
            # 计算罚款（总金额的5%）
            member_active = get_point(group_id, member_id)
            member_bank = get_bank_balance(group_id, member_id)
            fine = round((member_active + member_bank) * 0.05, 2)
            
            # 扣除罚款
            if fine <= member_active:
                update_point(group_id, member_id, member_active - fine)
                result_message += f"用户{member_id}被罚款{fine}金币\n"
            else:
                # 如果活动金币不足以支付罚款，从银行扣除
                remaining_fine = fine - member_active
                update_point(group_id, member_id, 0)
                update_bank_balance(group_id, member_id, max(0, member_bank - remaining_fine))
                result_message += f"用户{member_id}被罚款{fine}金币（活动金币不足，从银行扣除{remaining_fine}金币）\n"
            
            # 关进监狱5分钟
            release_time = datetime.datetime.now() + datetime.timedelta(minutes=5)
            update_user_status(group_id, member_id, STATUS_PRISON, release_time)
            
            # 重置越狱尝试次数
            if (group_id, member_id) in jailbreak_attempts:
                jailbreak_attempts[(group_id, member_id)] = 0
            
            # 更新抢劫CD
            robbery_cd[(group_id, member_id)] = time.time()
        
        # 删除队伍
        del robbery_teams[group_id][team_id]
        
        return result_message


def get_robbery_team_info(group_id: int, team_id: int) -> str:
    """获取抢劫队伍信息"""
    # 检查队伍是否存在
    if group_id not in robbery_teams or team_id not in robbery_teams[group_id]:
        return "指定的抢劫队伍不存在"
    
    team = robbery_teams[group_id][team_id]
    
    # 构建队伍信息
    message = f"===== 抢劫队伍信息 =====\n"
    message += f"队伍ID：{team_id}\n"
    message += f"队长：用户{team['leader']}\n"
    message += f"状态：{'等待中' if team['status'] == 'waiting' else '抢劫中'}\n"
    message += f"成员数量：{len(team['members'])}/5\n"
    message += f"成员列表：\n"
    
    for i, member_id in enumerate(team["members"], 1):
        message += f"{i}. 用户{member_id}\n"
    
    return message