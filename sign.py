import sqlite3
import datetime
import random

# 用户ID映射表 - 将QQ官方机器人的用户ID映射到原QQ号
user_id_mapping = {
    # 格式: {机器人平台用户ID: 原QQ号}
    "590848196": 1810867677
}

# 反向映射表 - 将原QQ号映射到机器人平台用户ID
qq_to_bot_id_mapping = {
    # 格式: {原QQ号: 机器人平台用户ID}
    1810867677: "590848196"
}

# 小倒霉蛋特权用户字典 - 下次签到必定触发小倒霉蛋的馈赠事件
# 格式: {uid: True} - 用户ID到布尔值的映射，表示是否拥有小倒霉蛋特权
# 现在支持机器人平台用户ID和原QQ号两种格式
xiaodaomeidan_privileged_users = {
    # 在这里添加特权用户，可以使用机器人平台的用户ID或原QQ号：
    1810867677: True,  # 用户x拥有小倒霉蛋特权（原QQ号）
    "590848196": True,  # 或者使用机器人平台用户ID
}

# 原QQ号特权用户列表（用于兼容性检查）
original_qq_privileged_users = {1810867677}


def get_bot_user_id(qq_number: int) -> str:
    """根据QQ号获取机器人平台的用户ID"""
    return qq_to_bot_id_mapping.get(qq_number, str(qq_number))


def get_qq_number(bot_user_id) -> int:
    """根据机器人平台用户ID获取原QQ号"""
    # 如果传入的就是数字，直接返回
    if isinstance(bot_user_id, int):
        return bot_user_id
    
    # 如果是字符串形式的数字，尝试转换
    if isinstance(bot_user_id, str) and bot_user_id.isdigit():
        return int(bot_user_id)
    
    # 从映射表中查找
    return user_id_mapping.get(str(bot_user_id), 0)


def add_privileged_user_by_qq(qq_number: int):
    """通过QQ号添加特权用户"""
    bot_user_id = get_bot_user_id(qq_number)
    xiaodaomeidan_privileged_users[bot_user_id] = True


def add_user_mapping(qq_number: int, bot_user_id: str):
    """添加用户ID映射关系"""
    global user_id_mapping, qq_to_bot_id_mapping
    user_id_mapping[bot_user_id] = qq_number
    qq_to_bot_id_mapping[qq_number] = bot_user_id


def sign_today(uid, group_id) -> str:
    init()
    # 检查是否有至尊签到卡
    has_supreme_card = check_supreme_card(uid, group_id)
    
    # 基础金币奖励：30~50
    coins = random.randint(30, 50)
    
    # 特殊事件：祖坟裂开（5%概率）
    zufen_event = random.random() < 0.05
    if zufen_event:
        coins *= 10
    
    # 检查是否是小倒霉蛋特权用户（下次签到必定触发小倒霉蛋的馈赠事件）
    is_xiaodaomeidan_privileged = check_xiaodaomeidan_privileged_user(uid, group_id)
    
    # 特殊事件：小倒霉蛋的馈赠（0.1%概率，或者特权用户且没有至尊签到卡时100%概率）
    xiaodaomeidan_event = (is_xiaodaomeidan_privileged and not has_supreme_card) or random.random() < 0.001
    
    # 如果是小倒霉蛋特权用户，标记为已使用
    if is_xiaodaomeidan_privileged:
        mark_xiaodaomeidan_privileged_used(uid, group_id)
    
    # 如果有至尊签到卡，奖励*100
    if has_supreme_card:
        coins *= 100
    now = datetime.datetime.now()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    sql = f"select * from sign_in where uid={uid} and belonging_group={group_id}"
    data = cursor.execute(sql).fetchall()
    if data:
        date = data[0][1]
        date = datetime.datetime.strptime(date, "%Y-%m-%d")
        timedelta = now - date
        coins_past = data[0][3]
        if timedelta.days < 1:
            return f"你今天已经签到过啦，请明天再来！\n你现在的金币是{coins_past}"
        count = data[0][2] + 1
        coins_now = coins_past + coins
        
        # 构建签到消息
        message = f"签到成功，今日获得金币为{coins}"
        
        # 添加特殊事件消息
        if zufen_event:
            message += "\n【祖坟裂开】签到奖励×10！"
        
        if has_supreme_card:
            message += "\n【至尊签到卡】签到奖励×100！"
        
        # 如果触发小倒霉蛋的馈赠事件
        if xiaodaomeidan_event:
            add_supreme_card(uid, group_id)
            message += "\n恭喜获得【小倒霉蛋的馈赠】！获得至尊签到卡×1"
        
        sql = f"UPDATE sign_in set sign_in_date = date(CURRENT_TIMESTAMP,'localtime'), total_sign_in = {count}," \
              f" points = {coins_now}, today_point = {coins} where uid = {uid} and belonging_group = {group_id}"
        cursor.execute(sql)
        cursor.close()
        conn.commit()
        conn.close()
        
        message += f"\n你现在的金币是{coins_now:.2f}"
        return message
    else:
        # 构建签到消息
        message = f"签到成功，今日获得金币为{coins}"
        
        # 添加特殊事件消息
        if zufen_event:
            message += "\n【祖坟裂开】签到奖励×10！"
        
        # 如果触发小倒霉蛋的馈赠事件
        if xiaodaomeidan_event:
            add_supreme_card(uid, group_id)
            message += "\n恭喜获得【小倒霉蛋的馈赠】！获得至尊签到卡×1"
        
        sql = f"INSERT INTO sign_in VALUES(null, date(CURRENT_TIMESTAMP,'localtime'), 1, {coins}, {group_id}," \
              f" {uid}, {coins})"
        cursor.execute(sql)
        cursor.close()
        conn.commit()
        conn.close()
        
        message += f"\n你现在的金币是{coins:.2f}"
        return message


def get_point(group: int, uid: int) -> float:
    init()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    sql = f"select * from sign_in where belonging_group={group} and uid={uid}"
    cursor.execute(sql)
    result = cursor.fetchone()
    if result:
        point = float(result[3])
    else:
        point = 0.0
    cursor.close()
    conn.commit()
    conn.close()
    return point


def update_point(group: int, uid: int, point: float):
    init()
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    sql = f"""update sign_in set points={point} where belonging_group={group} and uid={uid}"""
    cursor.execute(sql)
    cursor.close()
    conn.commit()
    conn.close()


def init():
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    # 修改points字段类型为REAL，支持小数
    sql = """create table if not exists sign_in(
        id integer primary key autoincrement,
        sign_in_date datetime not null,
        total_sign_in int not null,
        points REAL not null,
        belonging_group int not null,
        uid int not null,
        today_point REAL
    )
    """
    cursor.execute(sql)
    
    # 创建至尊签到卡表
    sql = """create table if not exists supreme_cards(
        id integer primary key autoincrement,
        uid int not null,
        belonging_group int not null,
        acquire_date datetime not null
    )
    """
    cursor.execute(sql)
    
    # 创建特权用户表 - 下次签到必定获得至尊签到卡
    # 保留此表以避免兼容性问题，但不再使用
    sql = """create table if not exists privileged_users(
        id integer primary key autoincrement,
        uid int not null,
        belonging_group int not null,
        add_date datetime not null,
        used int not null default 0,
        UNIQUE(uid, belonging_group)
    )
    """
    cursor.execute(sql)
    
    # 注意：不再创建小倒霉蛋特权用户表，现在使用硬编码字典
    
    conn.commit()
    cursor.close()
    conn.close()


def check_supreme_card(uid: int, group_id: int) -> bool:
    """检查用户是否拥有至尊签到卡"""
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    sql = f"select * from supreme_cards where uid={uid} and belonging_group={group_id}"
    cursor.execute(sql)
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result is not None


def add_supreme_card(uid: int, group_id: int):
    """为用户添加至尊签到卡"""
    conn = sqlite3.connect("identifier.sqlite")
    cursor = conn.cursor()
    sql = f"INSERT INTO supreme_cards VALUES(null, {uid}, {group_id}, date(CURRENT_TIMESTAMP,'localtime'))"
    cursor.execute(sql)
    cursor.close()
    conn.commit()
    conn.close()


# 以下函数已被移除，保留数据库表结构以避免兼容性问题
# def add_privileged_user(uid: int, group_id: int): ...
# def check_privileged_user(uid: int, group_id: int) -> bool: ...
# def mark_privileged_used(uid: int, group_id: int): ...


# 不再需要添加特权用户的函数，因为现在使用硬编码字典
# 如需添加特权用户，请直接修改文件顶部的xiaodaomeidan_privileged_users字典


def check_xiaodaomeidan_privileged_user(uid, group_id: int) -> bool:
    """检查用户是否在小倒霉蛋特权用户列表中（下次签到必定触发小倒霉蛋的馈赠事件）"""
    global xiaodaomeidan_privileged_users, original_qq_privileged_users
    
    # 方法1：直接匹配用户ID（支持机器人平台用户ID和原QQ号）
    if uid in xiaodaomeidan_privileged_users:
        return xiaodaomeidan_privileged_users[uid]
    
    # 方法2：如果是字符串类型的机器人用户ID，尝试通过映射表查找对应的QQ号
    if isinstance(uid, str):
        qq_number = get_qq_number(uid)
        if qq_number in original_qq_privileged_users:
            return True
    
    # 方法3：如果是数字类型，检查是否在原QQ号特权用户列表中
    if isinstance(uid, int) and uid in original_qq_privileged_users:
        return True
    
    return False


def mark_xiaodaomeidan_privileged_used(uid, group_id: int):
    """标记小倒霉蛋特权用户已使用特权（已触发小倒霉蛋的馈赠事件）"""
    global xiaodaomeidan_privileged_users
    
    # 方法1：直接在字典中查找并标记
    if uid in xiaodaomeidan_privileged_users:
        xiaodaomeidan_privileged_users[uid] = False
        return
    
    # 方法2：如果是字符串类型的机器人用户ID，尝试通过映射查找原QQ号并标记
    if isinstance(uid, str):
        qq_number = get_qq_number(uid)
        if qq_number in xiaodaomeidan_privileged_users:
            xiaodaomeidan_privileged_users[qq_number] = False
            return
    
    # 方法3：如果是数字类型，直接标记
    if isinstance(uid, int) and uid in xiaodaomeidan_privileged_users:
        xiaodaomeidan_privileged_users[uid] = False
