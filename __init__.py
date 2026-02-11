import datetime
from nonebot import on_command, on_regex
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from typing import Dict, List, Tuple, Optional, Union

# 导入自动回复模块

# 导入游戏相关函数和类
from .game import (
    BlackJackGame, GameStatus, duel, get_rank, add_game, start_game, 
    call_card, stop_card, get_game_ls, add_dual, get_battle_info, battle_dic
)

# 导入签到相关函数
from .sign import sign_today, get_point, update_point

# 导入赌场相关函数
from .casino import (
    get_user_chips, update_user_chips, get_chip_rate, get_casino_pool,
    update_casino_pool, create_blackjack_game, get_blackjack_game,
    update_blackjack_game, delete_blackjack_game, check_casino_punishment,
    set_casino_punishment, get_user_casino_records, get_casino_leaderboard
)

# 导入银行相关函数和常量
from .bank import (
    check_balance, get_bank_balance, rob_user, start_bank_robbery_team, 
    transfer, update_bank_balance, deposit, withdraw, check_operation_allowed,
    create_robbery_team, join_robbery_team, start_robbery, get_robbery_team_info,
    get_user_status, update_user_status, STATUS_PRISON, STATUS_WANTED, STATUS_HOSPITAL,
    jailbreak, bail, heal, join_bank_robbery_team, start_bank_robbery, catch_wanted,
    jail_break_all
)

# 导入通用常量
from .common import (
    RESOURCE_FOOD, RESOURCE_WOOD, RESOURCE_ORE,
    TOOL_IRON, TOOL_FINE_GOLD, TOOL_ALLOY, TOOL_ALLOY_PERM,
    PROF_NONE, PROF_WORKER, PROF_MINER, PROF_FARMER, PROF_LUMBERJACK, PROF_BLACKSMITH,
    MAX_STAMINA, SPECIAL_BLUE_GEM, SPECIAL_DEMON_BRANCH, SPECIAL_SUPER_PLANT
)

# 导入资源相关函数
from .resource import (
    get_user_stamina, update_user_stamina, get_user_resource, update_user_resource,
    get_user_tool, update_user_tool, produce_resource, eat_food, sell_resource,
    buy_resource, get_resource_info
)

# 导入联盟相关函数和常量
from .alliance import (
    get_user_alliance, join_alliance, leave_alliance, transfer_leadership,
    accept_leadership, disband_alliance, get_alliance_info, get_user_alliance_info,
    check_business_alliance_bonus, check_military_alliance_bonus, check_labor_alliance_bonus,
    get_resource_market_price, ALLIANCE_BUSINESS, ALLIANCE_MILITARY, ALLIANCE_LABOR
)

# 导入阵营相关函数和常量
from .faction import (
    get_user_faction, join_faction, get_faction_resource_pool_info, contribute_to_faction_pool,
    withdraw_from_faction_pool, start_faction_war, check_war_status, end_faction_war,
    start_embargo_vote, vote_for_embargo, lift_embargo, get_embargoes_info,
    produce_special_resource, get_user_faction_info, FACTION_WATER, FACTION_DEMON
)

# 导入市场相关函数和常量
from .market import (
    buy_item, use_production_card, use_stamina_card, buy_lottery, sell_to_system,
    create_market_listing, buy_from_market, cancel_market_listing, get_market_listings,
    get_item_info, get_shop_info, get_resource_price_info,
    ITEM_SUPREME_CARD, ITEM_LUXURY_HOUSE, ITEM_PRODUCTION_CARD, ITEM_STAMINA_CARD
)

# 导入职业相关函数和常量
from .profession import (
    get_user_profession, change_profession, get_profession_info, start_working, end_working,
    craft_tool, upgrade_tool, refresh_hourly_wage, TOOL_TYPE_PICKAXE, TOOL_TYPE_HOE, TOOL_TYPE_AXE
)

# 导入装备相关函数
from .equipment import (
    equip_tool, unequip_tool, get_equipment_info, get_equipped_tool
)

# 导入事件相关函数和常量
from .event import (
    get_active_events, trigger_random_event, get_wealth_ranking_message,
    EVENT_NATURAL_DISASTER, EVENT_MARKET, EVENT_SPECIAL, EVENT_WEALTH, EVENT_INFLATION
)


# 游戏命令
blackjack = on_command("21点", aliases={"发起21点"}, priority=10, block=True)
accept_blackjack = on_command("接受游戏", aliases={'接受'}, priority=10, block=True)
blackjack_list = on_command("游戏列表", aliases={'列表'}, priority=10, block=True)
call = on_command("叫牌", aliases={'call'}, priority=10, block=True)
stop = on_command("停牌", aliases={'stop'}, priority=10, block=True)
sign = on_command("签到", priority=10, block=True)
sign_plain = on_regex(r"^\s*签到\s*$", priority=10, block=True)
test_cmd = on_command("test", aliases={"ping"}, priority=1, block=True)
point_battle = on_command("金币对战", aliases={"对战", "发起对战"}, priority=5, block=True)
accept_battle = on_command("接受对战", aliases={"dual"}, priority=5, block=True)
battle_list = on_command("对战列表", priority=5, block=True)
rank = on_command("rank", aliases={'排名'}, priority=5, block=True)

# 赌场系统命令
casino_info_cmd = on_command("赌场信息", aliases={"查看赌场"}, priority=5, block=True)
buy_chips_cmd = on_command("购买筹码", aliases={"买筹码"}, priority=5, block=True)
sell_chips_cmd = on_command("出售筹码", aliases={"卖筹码"}, priority=5, block=True)
play_blackjack_cmd = on_command("玩21点", aliases={"赌场21点"}, priority=5, block=True)
casino_record_cmd = on_command("赌场记录", aliases={"赌场明细"}, priority=5, block=True)
casino_hit_cmd = on_command("赌场叫牌", aliases={"赌场要牌"}, priority=5, block=True)
casino_stand_cmd = on_command("赌场停牌", aliases={"赌场停止"}, priority=5, block=True)
battle_dic: Dict[int, List[List[int]]] = {}

@blackjack.handle()
async def start_blackjack(event: GroupMessageEvent, msg: Message = CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    point = msg.extract_plain_text().strip()
    player1_name = event.sender.card or event.sender.nickname
    if not point.isdigit():
        await blackjack.finish("请输入正确的金币数！")
    point = float(point)  # 使用float类型保持一致性
    user_point = get_point(group_id, user_id)
    if user_point < point:
        await blackjack.finish("你的金币不够！")
    deck_id = await add_game(group_id, user_id, int(point), player1_name)
    if deck_id >= 0:
        await blackjack.finish(f"游戏添加成功 游戏id为{deck_id}")
    else:
        await blackjack.finish("出错了QwQ 对战添加失败")


@accept_blackjack.handle()
async def accept_blackjack_game(event: GroupMessageEvent, msg: Message = CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    battle_id = msg.extract_plain_text().strip()
    player2_name = event.sender.card or event.sender.nickname
    user_point = get_point(group_id, user_id)
    if not battle_id.isdigit():
        await accept_blackjack.finish("请输入正确的游戏id！", at_sender=True)
    words = await start_game(int(battle_id), user_id, player2_name, group_id, int(user_point))  # 直接使用float类型的user_point
    await accept_blackjack.finish(words, at_sender=True)


@call.handle()
async def _call(event: GroupMessageEvent, msg: Message = CommandArg()):
    user_id = event.user_id
    deck_id = msg.extract_plain_text().strip()
    if not deck_id.isdigit():
        await call.finish("请输入正确的游戏id！", at_sender=True)
    words = await call_card(int(deck_id), user_id)
    await call.finish(words, at_sender=True)


@stop.handle()
async def _stop(event: GroupMessageEvent, msg: Message = CommandArg()):
    user_id = event.user_id
    deck_id = msg.extract_plain_text().strip()
    if not deck_id.isdigit():
        await call.finish("请输入正确的游戏id！", at_sender=True)
    words = await stop_card(int(deck_id), user_id)
    await stop.finish(words, at_sender=True)


@blackjack_list.handle()
async def show_game_list(event: GroupMessageEvent):
    group_id = event.group_id
    words = await get_game_ls(group_id)
    await blackjack.finish(words)


@sign.handle()
async def sign_in(event: MessageEvent):
    group_id = event.group_id if isinstance(event, GroupMessageEvent) else 0
    user_id = event.user_id
    await sign.finish(sign_today(user_id, group_id))


@sign_plain.handle()
async def _(event: MessageEvent):
    group_id = event.group_id if isinstance(event, GroupMessageEvent) else 0
    user_id = event.user_id
    await sign_plain.finish(sign_today(user_id, group_id))


@test_cmd.handle()
async def _(event: MessageEvent):
    await test_cmd.finish("ok")


@point_battle.handle()
async def battle(event: GroupMessageEvent, msg: Message = CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    point = msg.extract_plain_text().strip()
    if not point.isdigit():
        await point_battle.finish("请输入数字！")
    point = float(point)  # 使用float类型保持一致性
    user_point = get_point(group_id, user_id)
    if user_point < point:
        await point_battle.finish("你的金币不够！")
    battle_id = add_dual(group_id, user_id, int(point))
    if battle_id >= 0:
        await point_battle.finish(f"对战添加成功 对战id为{battle_id}")
    else:
        await point_battle.finish("出错了QwQ 对战添加失败")


@accept_battle.handle()
async def accept_battle_game(bot: Bot, event: GroupMessageEvent, msg: Message = CommandArg()):
    group_id = event.group_id
    acceptor = event.user_id
    acceptor_name = event.sender.card or event.sender.nickname
    battle_id = msg.extract_plain_text().strip()
    if not battle_id.isdigit():
        await point_battle.finish("请输入对战的数字id！")
    battle_id = int(battle_id)
    battle_info = get_battle_info(group_id, battle_id)
    if not battle_info:
        await point_battle.finish("对战id不存在！")
        return
    (battle_id, challenger, point) = battle_info
    acceptor_point = get_point(group_id, acceptor)
    challenger_point = get_point(group_id, challenger)
    sender = await bot.get_group_member_info(group_id=group_id, user_id=challenger)
    challenger_name = sender['card'] or sender.get('nickname', '')
    if acceptor_point < point:
        await point_battle.finish("你的金币不够！")
    if acceptor == challenger:
        await point_battle.finish("不能和自己对战！")
    words = duel(group_id, point, challenger, challenger_point, challenger_name,
                 acceptor, acceptor_point, acceptor_name)  # 直接使用float类型的point
    for index, battle_ls in enumerate(battle_dic[group_id]):
        if battle_ls[0] == battle_id:
            del battle_dic[group_id][index]
            break
    await accept_battle.finish(words)


@battle_list.handle()
async def accept(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if group_id not in battle_dic:
        await battle_list.finish("没有进行中的对战\n使用 /发起对战 金币数 发起一个吧")
    s = ""
    for battle_id, uid, point in battle_dic[group_id]:
        sender = await bot.get_group_member_info(group_id=group_id, user_id=uid)
        name = sender['card'] or sender.get('nickname', '')
        s += f"{battle_id} 发起人:{name} 对战金币:{point}\n"
    s = s[:-1]
    await battle_list.finish(s)


# 函数已移动到game.py


@rank.handle()
async def main(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    msg = await get_rank(group_id, bot)
    await rank.finish(msg)


# 资源系统命令
get_stamina = on_command("体力", aliases={"查看体力"}, priority=5, block=True)
produce_food = on_command("种地", aliases={"种菜", "种植"}, priority=5, block=True)
produce_wood = on_command("砍树", aliases={"伐木"}, priority=5, block=True)
produce_ore = on_command("挖矿", aliases={"采矿"}, priority=5, block=True)
eat_food_cmd = on_command("吃饭", aliases={"食用", "吃"}, priority=5, block=True)
sell_resource_cmd = on_command("出售资源", aliases={"卖资源"}, priority=5, block=True)
buy_resource_cmd = on_command("购买资源", aliases={"买资源"}, priority=5, block=True)
resource_info = on_command("资源信息", aliases={"查看资源"}, priority=5, block=True)

# 职业系统命令
refresh_wage_cmd = on_command("刷新工资", aliases={"工资刷新"}, priority=5, block=True)
select_profession = on_command("选择职业", aliases={"切换职业"}, priority=5, block=True)
profession_info = on_command("职业信息", aliases={"查看职业"}, priority=5, block=True)
start_work = on_command("开始打工", aliases={"打工"}, priority=5, block=True)
end_work = on_command("结束打工", aliases={"停止打工"}, priority=5, block=True)
eat_super_plant_cmd = on_command("食用超级植株", aliases={"吃超级植株"}, priority=5, block=True)
craft_tool_cmd = on_command("打造工具", aliases={"制作工具"}, priority=5, block=True)
upgrade_tool_cmd = on_command("升级工具", aliases={"工具升级"}, priority=5, block=True)

# 联盟系统命令
join_alliance_cmd = on_command("加入联盟", aliases={"创建联盟"}, priority=5, block=True)
leave_alliance_cmd = on_command("退出联盟", priority=5, block=True)
alliance_info_cmd = on_command("联盟信息", aliases={"查看联盟"}, priority=5, block=True)
transfer_leadership_cmd = on_command("转移领袖", aliases={"转移联盟领袖"}, priority=5, block=True)
accept_leadership_cmd = on_command("接受领袖", aliases={"接受联盟领袖"}, priority=5, block=True)
disband_alliance_cmd = on_command("解散联盟", priority=5, block=True)
check_market_price_cmd = on_command("查看市场价格", aliases={"市场价格"}, priority=5, block=True)

# 阵营系统命令
join_faction_cmd = on_command("加入阵营", priority=5, block=True)
faction_info_cmd = on_command("阵营信息", aliases={"查看阵营"}, priority=5, block=True)
faction_pool_cmd = on_command("阵营资源池", aliases={"查看资源池"}, priority=5, block=True)
contribute_resource_cmd = on_command("贡献资源", aliases={"向阵营贡献"}, priority=5, block=True)
withdraw_resource_cmd = on_command("提取资源", aliases={"从阵营提取"}, priority=5, block=True)
start_war_cmd = on_command("发起战争", aliases={"阵营战争"}, priority=5, block=True)
check_war_cmd = on_command("战争状态", aliases={"查看战争"}, priority=5, block=True)
embargo_vote_cmd = on_command("禁运投票", aliases={"发起禁运"}, priority=5, block=True)
vote_embargo_cmd = on_command("投票禁运", aliases={"禁运投票"}, priority=5, block=True)
lift_embargo_cmd = on_command("解除禁运", priority=5, block=True)
embargoes_info_cmd = on_command("禁运信息", aliases={"查看禁运"}, priority=5, block=True)
produce_special_cmd = on_command("产出特殊资源", aliases={"特殊资源"}, priority=5, block=True)

# 银行系统命令
check_balance_cmd = on_command("余额", aliases={"查询余额", "查看余额"}, priority=5, block=True)
deposit_cmd = on_command("存款", aliases={"存钱"}, priority=5, block=True)
withdraw_cmd = on_command("取款", aliases={"取钱"}, priority=5, block=True)
transfer_cmd = on_command("转账", priority=5, block=True)
rob_cmd = on_command("抢劫", priority=5, block=True)
start_robbery_cmd = on_command("抢银行", aliases={"抢银行队伍"}, priority=5, block=True)
join_robbery_cmd = on_command("加入", priority=5, block=True)
start_rob_cmd = on_command("开始抢", aliases={"开始抢银行"}, priority=5, block=True)
jailbreak_cmd = on_command("越狱", priority=5, block=True)
bail_cmd = on_command("保释", priority=5, block=True)
heal_cmd = on_command("治疗", aliases={"医疗"}, priority=5, block=True)
catch_wanted_cmd = on_command("抓", aliases={"抓捕", "抓人"}, priority=5, block=True)
jail_break_all_cmd = on_command("劫狱", aliases={"劫牢"}, priority=5, block=True)

# 市场系统命令
buy_item_cmd = on_command("购买物品", aliases={"买物品", "购买"}, priority=5, block=True)
use_production_card_cmd = on_command("使用生产卡", aliases={"用生产卡", "使用"}, priority=5, block=True)
use_stamina_card_cmd = on_command("使用体力卡", aliases={"用体力卡"}, priority=5, block=True)
buy_lottery_cmd = on_command("购买彩票", aliases={"买彩票"}, priority=5, block=True)
sell_to_system_cmd = on_command("卖给系统", aliases={"系统出售"}, priority=5, block=True)
create_market_listing_cmd = on_command("创建市场挂单", aliases={"市场挂单", "上架"}, priority=5, block=True)
buy_from_market_cmd = on_command("从市场购买", aliases={"市场购买", "购买挂单"}, priority=5, block=True)
cancel_market_listing_cmd = on_command("取消市场挂单", aliases={"取消挂单", "取消上架"}, priority=5, block=True)
get_market_listings_cmd = on_command("查看市场挂单", aliases={"市场挂单列表", "市场列表", "查看市场"}, priority=5, block=True)
get_item_info_cmd = on_command("物品信息", aliases={"查看物品"}, priority=5, block=True)
get_shop_info_cmd = on_command("商店", aliases={"查看商店"}, priority=5, block=True)
get_resource_price_info_cmd = on_command("资源价格信息", aliases={"查看资源价格"}, priority=5, block=True)

# 装备系统命令
equip_tool_cmd = on_command("装备工具", aliases={"装备", "穿戴工具"}, priority=5, block=True)
unequip_tool_cmd = on_command("卸下工具", aliases={"卸下", "取下工具"}, priority=5, block=True)
equipment_info_cmd = on_command("装备信息", aliases={"查看装备"}, priority=5, block=True)

# 事件系统命令
event_info_cmd = on_command("事件信息", aliases={"查看事件", "当前事件"}, priority=5, block=True)
wealth_rank_cmd = on_command("富豪榜", aliases={"财富排行", "财富榜"}, priority=5, block=True)
trigger_event_cmd = on_command("触发事件", priority=1, permission=SUPERUSER, block=True)
test_event_system_cmd = on_command("测试事件系统", priority=1, permission=SUPERUSER, block=True)


@get_stamina.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    stamina = get_user_stamina(group_id, user_id)
    await get_stamina.finish(f"当前体力：{stamina}/{MAX_STAMINA}")


@produce_food.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    # 检查用户职业
    profession_type = get_user_profession(group_id, user_id)
    if profession_type == PROF_NONE:
        await produce_food.finish("请先选择一个职业才能进行资源收集")
    if profession_type != PROF_FARMER:
        await produce_food.finish("只有农夫职业才能种地收集食物")
    result = produce_resource(group_id, user_id, RESOURCE_FOOD)
    await produce_food.finish(result)


@produce_wood.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    # 检查用户职业
    profession_type = get_user_profession(group_id, user_id)
    if profession_type == PROF_NONE:
        await produce_wood.finish("请先选择一个职业才能进行资源收集")
    if profession_type != PROF_LUMBERJACK:
        await produce_wood.finish("只有伐木工职业才能砍树收集木材")
    result = produce_resource(group_id, user_id, RESOURCE_WOOD)
    await produce_wood.finish(result)


@produce_ore.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    # 检查用户职业
    profession_type = get_user_profession(group_id, user_id)
    if profession_type == PROF_NONE:
        await produce_ore.finish("请先选择一个职业才能进行资源收集")
    if profession_type != PROF_MINER:
        await produce_ore.finish("只有矿工职业才能挖矿收集矿石")
    result = produce_resource(group_id, user_id, RESOURCE_ORE)
    await produce_ore.finish(result)


@eat_food_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str or not arg_str.isdigit():
        await eat_food_cmd.finish("请输入正确的食物数量，例如：吃饭 10")
    
    amount = int(arg_str)
    result = eat_food(group_id, user_id, amount)
    await eat_food_cmd.finish(result)


@sell_resource_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    args_list = arg_str.split()
    if len(args_list) != 2 or not args_list[1].isdigit():
        await sell_resource_cmd.finish("格式错误，正确格式：出售资源 [食物/木材/矿石] [数量]")
    
    resource_type_str = args_list[0]
    amount = int(args_list[1])
    
    resource_type = -1
    if resource_type_str in ["食物", "食品"]:
        resource_type = RESOURCE_FOOD
    elif resource_type_str in ["木材", "木头"]:
        resource_type = RESOURCE_WOOD
    elif resource_type_str in ["矿石", "矿物"]:
        resource_type = RESOURCE_ORE
    else:
        await sell_resource_cmd.finish("资源类型错误，可选：食物、木材、矿石")
    
    result = sell_resource(group_id, user_id, resource_type, amount)
    await sell_resource_cmd.finish(result)


@buy_resource_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    args_list = arg_str.split()
    if len(args_list) != 2 or not args_list[1].isdigit():
        await buy_resource_cmd.finish("格式错误，正确格式：购买资源 [食物/木材/矿石] [数量]")
    
    resource_type_str = args_list[0]
    amount = int(args_list[1])
    
    resource_type = -1
    if resource_type_str in ["食物", "食品"]:
        resource_type = RESOURCE_FOOD
    elif resource_type_str in ["木材", "木头"]:
        resource_type = RESOURCE_WOOD
    elif resource_type_str in ["矿石", "矿物"]:
        resource_type = RESOURCE_ORE
    else:
        await buy_resource_cmd.finish("资源类型错误，可选：食物、木材、矿石")
    
    result = buy_resource(group_id, user_id, resource_type, amount)
    await buy_resource_cmd.finish(result)


@resource_info.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    result = get_resource_info(group_id, user_id)
    await resource_info.finish(result)


@select_profession.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    profession_type = -1
    if arg_str in ["牛马", "打工人"]:
        profession_type = PROF_WORKER
    elif arg_str in ["矿工", "挖矿"]:
        profession_type = PROF_MINER
    elif arg_str in ["农夫", "农民", "种地"]:
        profession_type = PROF_FARMER
    elif arg_str in ["伐木工", "樵夫", "砍树"]:
        profession_type = PROF_LUMBERJACK
    elif arg_str in ["铁匠", "锻造师"]:
        profession_type = PROF_BLACKSMITH
    else:
        await select_profession.finish(
            "职业类型错误，可选：牛马、矿工、农夫、伐木工、铁匠\n" +
            "各职业特点：\n" +
            "- 牛马：不受体力限制，只能打工，每小时获得金币\n" +
            "- 矿工：可以挖矿，使用镐类工具获得增益\n" +
            "- 农夫：可以种地，使用锄类工具获得增益\n" +
            "- 伐木工：可以砍树，使用斧类工具获得增益\n" +
            "- 铁匠：可以打造工具，使用资源制作各种工具"
        )
    
    result = change_profession(group_id, user_id, profession_type)
    await select_profession.finish(result)


@profession_info.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    result = get_profession_info(group_id, user_id)
    await profession_info.finish(result)


@start_work.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    result = start_working(group_id, user_id)
    await start_work.finish(result)


@end_work.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    result = end_working(group_id, user_id)
    await end_work.finish(result)


@refresh_wage_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    result = refresh_hourly_wage(group_id, user_id)
    await refresh_wage_cmd.finish(result)


@eat_super_plant_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str or not arg_str.isdigit():
        await eat_super_plant_cmd.finish("请输入正确的超级植株数量，例如：食用超级植株 1")
    
    amount = int(arg_str)
    result = eat_super_plant(group_id, user_id, amount)
    await eat_super_plant_cmd.finish(result)


@craft_tool_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    args_list = arg_str.split()
    if len(args_list) != 2:
        await craft_tool_cmd.finish(
            "格式错误，正确格式：打造工具 [工具类型] [工具种类]\n" +
            "工具类型：铁质、精金、强化合金\n" +
            "工具种类：镐、锄、斧"
        )
    
    tool_type_str = args_list[0]
    tool_category_str = args_list[1]
    
    tool_type = -1
    if tool_type_str in ["铁质", "铁"]:
        tool_type = TOOL_IRON
    elif tool_type_str in ["精金"]:
        tool_type = TOOL_FINE_GOLD
    elif tool_type_str in ["强化合金", "合金"]:
        tool_type = TOOL_ALLOY
    else:
        await craft_tool_cmd.finish("工具类型错误，可选：铁质、精金、强化合金")
    
    tool_category = -1
    if tool_category_str in ["镐", "镐子", "稿"]:
        tool_category = TOOL_TYPE_PICKAXE
    elif tool_category_str in ["锄", "锄头"]:
        tool_category = TOOL_TYPE_HOE
    elif tool_category_str in ["斧", "斧头"]:
        tool_category = TOOL_TYPE_AXE
    else:
        await craft_tool_cmd.finish("工具种类错误，可选：镐、锄、斧")
    
    result = craft_tool(group_id, user_id, tool_type, tool_category)
    await craft_tool_cmd.finish(result)


@upgrade_tool_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    tool_category = -1
    if arg_str in ["镐", "镐子", "稿"]:
        tool_category = TOOL_TYPE_PICKAXE
    elif arg_str in ["锄", "锄头"]:
        tool_category = TOOL_TYPE_HOE
    elif arg_str in ["斧", "斧头"]:
        tool_category = TOOL_TYPE_AXE
    else:
        await upgrade_tool_cmd.finish("工具种类错误，可选：镐、锄、斧")
    
    result = upgrade_tool(group_id, user_id, tool_category)
    await upgrade_tool_cmd.finish(result)


# 联盟系统命令处理函数
@join_alliance_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    alliance_type = -1
    if arg_str in ["商业联盟", "商业"]:
        alliance_type = ALLIANCE_BUSINESS
    elif arg_str in ["军事同盟", "军事"]:
        alliance_type = ALLIANCE_MILITARY
    elif arg_str in ["工农联合", "工农"]:
        alliance_type = ALLIANCE_LABOR
    else:
        await join_alliance_cmd.finish(
            "联盟类型错误，可选：商业联盟、军事同盟、工农联合\n" +
            "各联盟特点：\n" +
            "- 商业联盟：交易税-100%，可查看当前资源的市场价格\n" +
            "- 军事同盟：被抢劫概率-20%，被抢劫保护30%资源或金币\n" +
            "- 工农联合：生产产量+10%，体力消耗-10%"
        )
    
    result = join_alliance(group_id, user_id, alliance_type)
    await join_alliance_cmd.finish(result)


@leave_alliance_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    result = leave_alliance(group_id, user_id)
    await leave_alliance_cmd.finish(result)


@alliance_info_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str:
        # 查看自己的联盟信息
        result = get_user_alliance_info(group_id, user_id)
    else:
        # 查看指定联盟的信息
        alliance_type = -1
        if arg_str in ["商业联盟", "商业"]:
            alliance_type = ALLIANCE_BUSINESS
        elif arg_str in ["军事同盟", "军事"]:
            alliance_type = ALLIANCE_MILITARY
        elif arg_str in ["工农联合", "工农"]:
            alliance_type = ALLIANCE_LABOR
        else:
            await alliance_info_cmd.finish("联盟类型错误，可选：商业联盟、军事同盟、工农联合")
        
        result = get_alliance_info(group_id, alliance_type)
    
    await alliance_info_cmd.finish(result)


@transfer_leadership_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str.isdigit():
        await transfer_leadership_cmd.finish("请输入正确的用户ID！")
    
    new_leader_id = int(arg_str)
    result = transfer_leadership(group_id, user_id, new_leader_id)
    await transfer_leadership_cmd.finish(result)


@accept_leadership_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    result = accept_leadership(group_id, user_id)
    await accept_leadership_cmd.finish(result)


@disband_alliance_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    result = disband_alliance(group_id, user_id)
    await disband_alliance_cmd.finish(result)


@check_market_price_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    resource_type = -1
    if arg_str in ["食物", "食品"]:
        resource_type = RESOURCE_FOOD
    elif arg_str in ["木材", "木头"]:
        resource_type = RESOURCE_WOOD
    elif arg_str in ["矿石", "矿物"]:
        resource_type = RESOURCE_ORE
    else:
        await check_market_price_cmd.finish("资源类型错误，可选：食物、木材、矿石")
    
    result = get_resource_market_price(group_id, user_id, resource_type)
    await check_market_price_cmd.finish(result)


# 阵营系统命令处理函数
@join_faction_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    faction_type = -1
    if arg_str in ["水水军", "水水"]:
        faction_type = FACTION_WATER
    elif arg_str in ["魔王军", "魔王"]:
        faction_type = FACTION_DEMON
    else:
        await join_faction_cmd.finish(
            "阵营类型错误，可选：水水军、魔王军\n" +
            "各阵营特点：\n" +
            "- 水水军：可以产出海蓝宝石\n" +
            "- 魔王军：可以产出恶魔树枝干\n\n" +
            "注意：一旦加入阵营不可切换，请慎重选择！"
        )
    
    result = join_faction(group_id, user_id, faction_type)
    await join_faction_cmd.finish(result)


@faction_info_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    result = get_user_faction_info(group_id, user_id)
    await faction_info_cmd.finish(result)


@faction_pool_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    # 获取用户阵营
    faction_type = get_user_faction(group_id, user_id)
    if faction_type == -1:
        await faction_pool_cmd.finish("你不属于任何阵营，无法查看资源池！")
    
    result = get_faction_resource_pool_info(group_id, faction_type)
    await faction_pool_cmd.finish(result)


@contribute_resource_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    args_list = arg_str.split()
    if len(args_list) != 2 or not args_list[1].isdigit():
        await contribute_resource_cmd.finish("格式错误，正确格式：贡献资源 [食物/木材/矿石] [数量]")
    
    resource_type_str = args_list[0]
    amount = int(args_list[1])
    
    resource_type = -1
    if resource_type_str in ["食物", "食品"]:
        resource_type = RESOURCE_FOOD
    elif resource_type_str in ["木材", "木头"]:
        resource_type = RESOURCE_WOOD
    elif resource_type_str in ["矿石", "矿物"]:
        resource_type = RESOURCE_ORE
    else:
        await contribute_resource_cmd.finish("资源类型错误，可选：食物、木材、矿石")
    
    result = contribute_to_faction_pool(group_id, user_id, resource_type, amount)
    await contribute_resource_cmd.finish(result)


@withdraw_resource_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    args_list = arg_str.split()
    if len(args_list) != 2 or not args_list[1].isdigit():
        await withdraw_resource_cmd.finish("格式错误，正确格式：提取资源 [食物/木材/矿石] [数量]")
    
    resource_type_str = args_list[0]
    amount = int(args_list[1])
    
    resource_type = -1
    if resource_type_str in ["食物", "食品"]:
        resource_type = RESOURCE_FOOD
    elif resource_type_str in ["木材", "木头"]:
        resource_type = RESOURCE_WOOD
    elif resource_type_str in ["矿石", "矿物"]:
        resource_type = RESOURCE_ORE
    else:
        await withdraw_resource_cmd.finish("资源类型错误，可选：食物、木材、矿石")
    
    result = withdraw_from_faction_pool(group_id, user_id, resource_type, amount)
    await withdraw_resource_cmd.finish(result)


@start_war_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    target_faction = -1
    if arg_str in ["水水军", "水水"]:
        target_faction = FACTION_WATER
    elif arg_str in ["魔王军", "魔王"]:
        target_faction = FACTION_DEMON
    else:
        await start_war_cmd.finish("目标阵营错误，可选：水水军、魔王军")
    
    result = start_faction_war(group_id, user_id, target_faction)
    await start_war_cmd.finish(result)


@check_war_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    
    result = check_war_status(group_id)
    await check_war_cmd.finish(result)


@embargo_vote_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    args_list = arg_str.split()
    if len(args_list) != 2:
        await embargo_vote_cmd.finish("格式错误，正确格式：禁运投票 [水水军/魔王军] [食物/木材/矿石]")
    
    target_faction_str = args_list[0]
    resource_type_str = args_list[1]
    
    target_faction = -1
    if target_faction_str in ["水水军", "水水"]:
        target_faction = FACTION_WATER
    elif target_faction_str in ["魔王军", "魔王"]:
        target_faction = FACTION_DEMON
    else:
        await embargo_vote_cmd.finish("目标阵营错误，可选：水水军、魔王军")
    
    resource_type = -1
    if resource_type_str in ["食物", "食品"]:
        resource_type = RESOURCE_FOOD
    elif resource_type_str in ["木材", "木头"]:
        resource_type = RESOURCE_WOOD
    elif resource_type_str in ["矿石", "矿物"]:
        resource_type = RESOURCE_ORE
    else:
        await embargo_vote_cmd.finish("资源类型错误，可选：食物、木材、矿石")
    
    result = start_embargo_vote(group_id, user_id, target_faction, resource_type)
    await embargo_vote_cmd.finish(result)


@vote_embargo_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    vote = True  # 默认赞成
    if arg_str in ["否", "反对", "不同意", "no", "n"]:
        vote = False
    
    result = vote_for_embargo(group_id, user_id, vote)
    await vote_embargo_cmd.finish(result)


@lift_embargo_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    args_list = arg_str.split()
    if len(args_list) != 2:
        await lift_embargo_cmd.finish("格式错误，正确格式：解除禁运 [水水军/魔王军] [食物/木材/矿石]")
    
    target_faction_str = args_list[0]
    resource_type_str = args_list[1]
    
    target_faction = -1
    if target_faction_str in ["水水军", "水水"]:
        target_faction = FACTION_WATER
    elif target_faction_str in ["魔王军", "魔王"]:
        target_faction = FACTION_DEMON
    else:
        await lift_embargo_cmd.finish("目标阵营错误，可选：水水军、魔王军")
    
    resource_type = -1
    if resource_type_str in ["食物", "食品"]:
        resource_type = RESOURCE_FOOD
    elif resource_type_str in ["木材", "木头"]:
        resource_type = RESOURCE_WOOD
    elif resource_type_str in ["矿石", "矿物"]:
        resource_type = RESOURCE_ORE
    else:
        await lift_embargo_cmd.finish("资源类型错误，可选：食物、木材、矿石")
    
    result = lift_embargo(group_id, user_id, target_faction, resource_type)
    await lift_embargo_cmd.finish(result)


@embargoes_info_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    # 获取用户阵营
    faction_type = get_user_faction(group_id, user_id)
    if faction_type == -1:
        await embargoes_info_cmd.finish("你不属于任何阵营，无法查看禁运信息！")
    
    result = get_embargoes_info(group_id, faction_type)
    await embargoes_info_cmd.finish(result)


@produce_special_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    result = produce_special_resource(group_id, user_id)
    await produce_special_cmd.finish(result)


# 银行系统命令处理函数
@check_balance_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    result = check_balance(group_id, user_id)
    await check_balance_cmd.finish(result)


@deposit_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str or not arg_str.replace('.', '', 1).isdigit():
        await deposit_cmd.finish("请输入正确的存款金额，例如：存款 1000")
    
    amount = float(arg_str)
    result = deposit(group_id, user_id, amount)
    await deposit_cmd.finish(result)


@withdraw_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str or not arg_str.replace('.', '', 1).isdigit():
        await withdraw_cmd.finish("请输入正确的取款金额，例如：取款 1000")
    
    amount = float(arg_str)
    result = withdraw(group_id, user_id, amount)
    await withdraw_cmd.finish(result)


@transfer_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    # 获取完整消息对象，用于提取@信息
    message = event.message
    
    # 检查消息中是否有@用户
    at_segment = None
    for segment in message:
        if segment.type == "at":
            at_segment = segment
            break
    
    # 处理@用户的情况
    if at_segment:
        target_id = int(at_segment.data["qq"])
        # 当使用@时，金额应该是剩余的参数文本
        amount_str = arg_str.strip()
        if not amount_str or not amount_str.replace('.', '', 1).isdigit():
            await transfer_cmd.finish("格式错误，正确格式：转账 @用户 金额")
        amount = float(amount_str)
    else:
        # 没有@，使用原来的方式（QQ号 金额）
        args_list = arg_str.split()
        if len(args_list) != 2 or not args_list[0].isdigit() or not args_list[1].replace('.', '', 1).isdigit():
            await transfer_cmd.finish("格式错误，正确格式：转账 [对方QQ号] 金额")
        target_id = int(args_list[0])
        amount = float(args_list[1])
        amount = float(args_list[1])
    
    result = transfer(group_id, user_id, target_id, amount)
    await transfer_cmd.finish(result)


@rob_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    # 获取完整消息对象，用于提取@信息
    message = event.message
    
    # 检查消息中是否有@用户
    at_segment = None
    for segment in message:
        if segment.type == "at":
            at_segment = segment
            break
    
    # 处理@用户的情况
    if at_segment:
        victim_id = int(at_segment.data["qq"])
    else:
        # 没有@，使用原来的方式（QQ号）
        if not arg_str or not arg_str.isdigit():
            await rob_cmd.finish("格式错误，正确格式：抢劫 @用户 或 抢劫 [对方QQ号]")
        victim_id = int(arg_str)
    
    result = rob_user(group_id, user_id, victim_id)
    await rob_cmd.finish(result)


@start_robbery_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    result = start_bank_robbery_team(group_id, user_id)
    await start_robbery_cmd.finish(result)


@join_robbery_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    # 使用join_bank_robbery_team函数，不需要队伍ID
    result = join_bank_robbery_team(group_id, user_id)
    await join_robbery_cmd.finish(result)


@start_rob_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    # 使用start_bank_robbery函数，不需要队伍ID
    result = start_bank_robbery(group_id, user_id)
    await start_rob_cmd.finish(result)


@jailbreak_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    result = jailbreak(group_id, user_id)
    await jailbreak_cmd.finish(result)


@bail_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    # 获取完整消息对象，用于提取@信息
    message = event.message
    
    # 检查消息中是否有@用户
    at_segment = None
    for segment in message:
        if segment.type == "at":
            at_segment = segment
            break
    
    # 处理@用户的情况
    if at_segment:
        target_id = int(at_segment.data["qq"])
    else:
        # 没有@，使用原来的方式（QQ号）
        if not arg_str or not arg_str.isdigit():
            await bail_cmd.finish("格式错误，正确格式：保释 @用户 或 保释 [对方QQ号]")
        target_id = int(arg_str)
    
    result = bail(group_id, user_id, target_id)
    await bail_cmd.finish(result)


@heal_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    # 获取完整消息对象，用于提取@信息
    message = event.message
    
    # 检查消息中是否有@用户
    at_segment = None
    for segment in message:
        if segment.type == "at":
            at_segment = segment
            break
    
    # 处理@用户的情况
    if at_segment:
        target_id = int(at_segment.data["qq"])
    else:
        # 没有@，使用原来的方式（QQ号）
        if not arg_str or not arg_str.isdigit():
            await heal_cmd.finish("格式错误，正确格式：治疗 @用户 或 治疗 [对方QQ号]")
        target_id = int(arg_str)
    
    # 治疗功能应该使用target_id而不是user_id
    result = heal(group_id, target_id)
    await heal_cmd.finish(result)


@catch_wanted_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    # 获取完整消息对象，用于提取@信息
    message = event.message
    
    # 检查消息中是否有@用户
    at_segment = None
    for segment in message:
        if segment.type == "at":
            at_segment = segment
            break
    
    # 处理@用户的情况
    if at_segment:
        wanted_id = int(at_segment.data["qq"])
    else:
        # 没有@，使用原来的方式（QQ号）
        if not arg_str or not arg_str.isdigit():
            await catch_wanted_cmd.finish("格式错误，正确格式：抓 @用户 或 抓 [对方QQ号]")
        wanted_id = int(arg_str)
    
    result = catch_wanted(group_id, user_id, wanted_id)
    await catch_wanted_cmd.finish(result)


@jail_break_all_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    result = jail_break_all(group_id, user_id)
    await jail_break_all_cmd.finish(result)


# 市场系统命令处理函数
@buy_item_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    args_list = arg_str.split()
    if len(args_list) != 2 or not args_list[1].isdigit():
        await buy_item_cmd.finish("格式错误，正确格式：购买物品 [物品名称] [数量]")
    
    item_name = args_list[0]
    amount = int(args_list[1])
    
    item_type = -1
    if item_name in ["至尊签到卡", "签到卡"]:
        item_type = ITEM_SUPREME_CARD
    elif item_name in ["大别野", "豪宅", "别墅"]:
        item_type = ITEM_LUXURY_HOUSE
    elif item_name in ["生产卡", "生产加倍卡"]:
        item_type = ITEM_PRODUCTION_CARD
    elif item_name in ["体力卡", "体力恢复卡"]:
        item_type = ITEM_STAMINA_CARD
    else:
        await buy_item_cmd.finish("物品名称错误，可选：至尊签到卡、大别野、生产卡、体力卡")
    
    result = buy_item(group_id, user_id, item_type, amount)
    await buy_item_cmd.finish(result)


@use_production_card_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    result = use_production_card(group_id, user_id)
    await use_production_card_cmd.finish(result)


@use_stamina_card_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    result = use_stamina_card(group_id, user_id)
    await use_stamina_card_cmd.finish(result)


@buy_lottery_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str or not arg_str.isdigit():
        await buy_lottery_cmd.finish("请输入正确的彩票面额，可选：500、1000、5000、10000、20000")
    
    amount = int(arg_str)
    if amount not in [500, 1000, 5000, 10000, 20000]:
        await buy_lottery_cmd.finish("彩票面额错误，可选：500、1000、5000、10000、20000")
    
    result = buy_lottery(group_id, user_id, amount)
    await buy_lottery_cmd.finish(result)


@sell_to_system_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    args_list = arg_str.split()
    if len(args_list) != 3 or not args_list[2].isdigit():
        await sell_to_system_cmd.finish("格式错误，正确格式：卖给系统 [物品类型] [物品名称] [数量]")
    
    item_type_str = args_list[0]
    item_name = args_list[1]
    amount = int(args_list[2])
    
    if item_type_str == "资源":
        item_type = 0
        resource_type = -1
        if item_name in ["食物", "食品"]:
            resource_type = RESOURCE_FOOD
        elif item_name in ["木材", "木头"]:
            resource_type = RESOURCE_WOOD
        elif item_name in ["矿石", "矿物"]:
            resource_type = RESOURCE_ORE
        else:
            await sell_to_system_cmd.finish("资源类型错误，可选：食物、木材、矿石")
        
        # 传入4个位置参数:群号,用户ID,物品类型,资源类型
        result = sell_to_system(group_id, user_id, item_type, resource_type)
    else:
        await sell_to_system_cmd.finish("物品类型错误，目前只支持出售资源")
    
    await sell_to_system_cmd.finish(result)


@create_market_listing_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    args_list = arg_str.split()
    if len(args_list) < 4:
        await create_market_listing_cmd.finish("格式错误，正确格式：\n创建市场挂单 资源 [食物/木材/矿石] [数量] [单价]\n创建市场挂单 工具 [铁质/精金/强化合金/不毁] [镐/锄/斧] [价格]\n创建市场挂单 特殊材料 [海蓝宝石/超级植株/恶魔树枝干] [数量] [单价]")
    
    item_type_str = args_list[0]
    item_name = args_list[1]
    
    if item_type_str == "资源":
        if len(args_list) != 4 or not args_list[2].isdigit() or not args_list[3].replace('.', '', 1).isdigit():
            await create_market_listing_cmd.finish("格式错误，正确格式：创建市场挂单 资源 [食物/木材/矿石] [数量] [单价]")
        
        quantity = int(args_list[2])
        price = float(args_list[3])
        
        item_type = 0
        resource_type = -1
        if item_name in ["食物", "食品"]:
            resource_type = RESOURCE_FOOD
        elif item_name in ["木材", "木头"]:
            resource_type = RESOURCE_WOOD
        elif item_name in ["矿石", "矿物"]:
            resource_type = RESOURCE_ORE
        else:
            await create_market_listing_cmd.finish("资源类型错误，可选：食物、木材、矿石")
        
        result = create_market_listing(group_id, user_id, item_type, resource_type=resource_type, price_per_unit=price, quantity=quantity)
    
    elif item_type_str == "工具":
        if len(args_list) != 4 or not args_list[3].replace('.', '', 1).isdigit():
            await create_market_listing_cmd.finish("格式错误，正确格式：创建市场挂单 工具 [铁质/精金/强化合金/不毁] [镐/锄/斧] [价格]")
        
        tool_type_str = item_name
        tool_category_str = args_list[2]
        price = float(args_list[3])
        
        # 解析工具类型
        tool_type = -1
        if tool_type_str == "铁质":
            tool_type = TOOL_IRON
        elif tool_type_str == "精金":
            tool_type = TOOL_FINE_GOLD
        elif tool_type_str == "强化合金":
            tool_type = TOOL_ALLOY
        elif tool_type_str in ["不毁", "强化合金不毁"]:
            tool_type = TOOL_ALLOY_PERM
        else:
            await create_market_listing_cmd.finish("工具类型错误，可选：铁质、精金、强化合金、不毁")
        
        # 解析工具种类
        tool_category = -1
        if tool_category_str == "镐":
            tool_category = TOOL_TYPE_PICKAXE
        elif tool_category_str == "锄":
            tool_category = TOOL_TYPE_HOE
        elif tool_category_str == "斧":
            tool_category = TOOL_TYPE_AXE
        else:
            await create_market_listing_cmd.finish("工具种类错误，可选：镐、锄、斧")
        
        result = create_market_listing(group_id, user_id, 1, tool_type=tool_type, tool_category=tool_category, price_per_unit=price)
    
    elif item_type_str == "特殊材料":
        if len(args_list) != 4 or not args_list[2].isdigit() or not args_list[3].replace('.', '', 1).isdigit():
            await create_market_listing_cmd.finish("格式错误，正确格式：创建市场挂单 特殊材料 [海蓝宝石/超级植株/恶魔树枝干] [数量] [单价]")
        
        special_resource_str = item_name
        quantity = int(args_list[2])
        price = float(args_list[3])
        
        # 解析特殊材料类型
        special_resource_type = -1
        if special_resource_str in ["海蓝宝石", "宝石"]:
            special_resource_type = SPECIAL_BLUE_GEM
        elif special_resource_str in ["超级植株", "植株"]:
            special_resource_type = SPECIAL_SUPER_PLANT
        elif special_resource_str in ["恶魔树枝干", "树枝干", "恶魔树枝"]:
            special_resource_type = SPECIAL_DEMON_BRANCH
        else:
            await create_market_listing_cmd.finish("特殊材料类型错误，可选：海蓝宝石、超级植株、恶魔树枝干")
        
        result = create_market_listing(group_id, user_id, 2, special_resource_type=special_resource_type, price_per_unit=price, quantity=quantity)
    
    else:
        await create_market_listing_cmd.finish("物品类型错误，可选：资源、工具、特殊材料")
    
    await create_market_listing_cmd.finish(result)


@buy_from_market_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    args_list = arg_str.split()
    if len(args_list) == 1:
        if not args_list[0].isdigit():
            await buy_from_market_cmd.finish("请输入正确的挂单ID，例如：从市场购买 1 或 从市场购买 1 5")
        
        listing_id = int(args_list[0])
        # 默认购买挂单的全部数量,传入-1表示购买全部
        quantity = -1
    elif len(args_list) == 2:
        if not args_list[0].isdigit() or not args_list[1].isdigit():
            await buy_from_market_cmd.finish("格式错误，正确格式：从市场购买 [挂单ID] [数量]\n注意：购买工具类型时数量只能为1")
        
        listing_id = int(args_list[0])
        quantity = int(args_list[1])
    else:
        await buy_from_market_cmd.finish("格式错误，正确格式：从市场购买 [挂单ID] 或 从市场购买 [挂单ID] [数量]")
    
    result = buy_from_market(group_id, user_id, listing_id, quantity)
    await buy_from_market_cmd.finish(result)


@cancel_market_listing_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str or not arg_str.isdigit():
        await cancel_market_listing_cmd.finish("请输入正确的挂单ID，例如：取消市场挂单 1")
    
    listing_id = int(arg_str)
    result = cancel_market_listing(group_id, user_id, listing_id)
    await cancel_market_listing_cmd.finish(result)


@get_market_listings_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str:
        # 查看所有挂单
        result = get_market_listings(group_id)
    else:
        # 查看指定资源类型的挂单
        resource_type = -1
        if arg_str in ["食物", "食品"]:
            resource_type = RESOURCE_FOOD
        elif arg_str in ["木材", "木头"]:
            resource_type = RESOURCE_WOOD
        elif arg_str in ["矿石", "矿物"]:
            resource_type = RESOURCE_ORE
        else:
            await get_market_listings_cmd.finish("资源类型错误，可选：食物、木材、矿石")
        
        # 传入资源类型参数
        result = get_market_listings(group_id)
    
    await get_market_listings_cmd.finish(result)


@get_item_info_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    result = get_item_info(group_id, user_id)
    await get_item_info_cmd.finish(result)


@get_shop_info_cmd.handle()
async def _(event: GroupMessageEvent):
    result = get_shop_info()
    await get_shop_info_cmd.finish(result)


@get_resource_price_info_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    
    result = get_resource_price_info(group_id)
    await get_resource_price_info_cmd.finish(result)


@event_info_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    active_events = get_active_events(group_id)
    
    if not active_events:
        await event_info_cmd.finish("当前没有正在进行的事件")
    
    message = "===== 当前事件 =====\n"
    
    for event_type, event_info in active_events.items():
        event_subtype = event_info["type"]
        end_time = event_info["end_time"]
        effect = event_info["effect"]
        
        # 计算剩余时间
        remaining = end_time - datetime.datetime.now()
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        
        # 获取事件类型描述
        if event_type == EVENT_NATURAL_DISASTER:
            event_type_str = "自然灾害"
            if event_subtype == 0:
                event_desc = f"干旱：食物产量{effect*100:.0f}%"
            elif event_subtype == 1:
                event_desc = f"风暴：木材产量{effect*100:.0f}%"
            elif event_subtype == 2:
                event_desc = f"地震：矿石产量{effect*100:.0f}%"
            else:
                event_desc = "未知灾害"
        
        elif event_type == EVENT_MARKET:
            event_type_str = "市场事件"
            if event_subtype == 0:
                event_desc = f"价格飙升：资源价格+{effect*100:.0f}%"
            elif event_subtype == 1:
                event_desc = f"市场崩溃：资源价格{effect*100:.0f}%"
            else:
                event_desc = "未知市场事件"
        
        elif event_type == EVENT_SPECIAL:
            event_type_str = "特殊事件"
            if event_subtype == 0:
                event_desc = f"黄金时间：资源产量+{effect*100:.0f}%"
            elif event_subtype == 1:
                event_desc = f"能量提升：体力消耗{effect*100:.0f}%"
            else:
                event_desc = "未知特殊事件"
        
        elif event_type == EVENT_WEALTH:
            event_type_str = "贫富事件"
            event_desc = "富豪遭到抢劫"
        
        elif event_type == EVENT_INFLATION:
            event_type_str = "通胀事件"
            event_desc = "银行遭到劫匪"
        
        else:
            event_type_str = "未知事件"
            event_desc = "未知效果"
        
        message += f"【{event_type_str}】{event_desc}\n"
        message += f"剩余时间：{minutes}分{seconds}秒\n\n"
    
    await event_info_cmd.finish(message.strip())


@wealth_rank_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    message = await get_wealth_ranking_message(group_id)
    await wealth_rank_cmd.finish(message)


# 装备系统命令处理函数
@equip_tool_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    args_list = arg_str.split()
    if len(args_list) != 2:
        await equip_tool_cmd.finish(
            "格式错误，正确格式：装备工具 [工具类型] [工具种类]\n" +
            "工具类型：铁质、精金、强化合金、不毁合金\n" +
            "工具种类：镐、锄、斧"
        )
    
    tool_type_str = args_list[0]
    tool_category_str = args_list[1]
    
    # 解析工具类型
    tool_type = -1
    if tool_type_str in ["铁质", "铁"]:
        tool_type = TOOL_IRON
    elif tool_type_str in ["精金"]:
        tool_type = TOOL_FINE_GOLD
    elif tool_type_str in ["强化合金", "合金"]:
        tool_type = TOOL_ALLOY
    elif tool_type_str in ["不毁合金", "不毁"]:
        tool_type = TOOL_ALLOY_PERM
    else:
        await equip_tool_cmd.finish("工具类型错误，可选：铁质、精金、强化合金、不毁合金")
    
    # 解析工具种类
    tool_category = -1
    if tool_category_str in ["镐", "镐子", "稿"]:
        tool_category = TOOL_TYPE_PICKAXE
    elif tool_category_str in ["锄", "锄头"]:
        tool_category = TOOL_TYPE_HOE
    elif tool_category_str in ["斧", "斧头"]:
        tool_category = TOOL_TYPE_AXE
    else:
        await equip_tool_cmd.finish("工具种类错误，可选：镐、锄、斧")
    
    result = equip_tool(group_id, user_id, tool_type, tool_category)
    await equip_tool_cmd.finish(result)


@unequip_tool_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str:
        await unequip_tool_cmd.finish("格式错误，正确格式：卸下工具 [工具种类]\n工具种类：镐、锄、斧")
    
    # 解析工具种类
    tool_category = -1
    if arg_str in ["镐", "镐子", "稿"]:
        tool_category = TOOL_TYPE_PICKAXE
    elif arg_str in ["锄", "锄头"]:
        tool_category = TOOL_TYPE_HOE
    elif arg_str in ["斧", "斧头"]:
        tool_category = TOOL_TYPE_AXE
    else:
        await unequip_tool_cmd.finish("工具种类错误，可选：镐、锄、斧")
    
    result = unequip_tool(group_id, user_id, tool_category)
    await unequip_tool_cmd.finish(result)


@equipment_info_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    result = get_equipment_info(group_id, user_id)
    await equipment_info_cmd.finish(result)


# 赌场系统命令处理函数
@casino_info_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    from .casino import get_casino_info
    result = get_casino_info(group_id)
    await casino_info_cmd.finish(result)


@buy_chips_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str or not arg_str.isdigit():
        await buy_chips_cmd.finish("请输入正确的筹码数量，例如：购买筹码 1000")
    
    amount = int(arg_str)
    from .casino import buy_chips
    result = buy_chips(group_id, user_id, amount)
    await buy_chips_cmd.finish(result)


@sell_chips_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str or not arg_str.isdigit():
        await sell_chips_cmd.finish("请输入正确的筹码数量，例如：出售筹码 1000")
    
    amount = int(arg_str)
    from .casino import sell_chips
    result = sell_chips(group_id, user_id, amount)
    await sell_chips_cmd.finish(result)


@play_blackjack_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str or not arg_str.isdigit():
        await play_blackjack_cmd.finish("请输入正确的下注筹码数量，例如：玩21点 100")
    
    bet_amount = int(arg_str)
    from .casino import play_blackjack
    result = play_blackjack(group_id, user_id, bet_amount)
    await play_blackjack_cmd.finish(result)


@casino_hit_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    from .casino import casino_hit
    result = casino_hit(group_id, user_id)
    await casino_hit_cmd.finish(result)


@casino_stand_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    from .casino import casino_stand
    result = casino_stand(group_id, user_id)
    await casino_stand_cmd.finish(result)


@casino_record_cmd.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    from .casino import get_user_casino_records
    result = get_user_casino_records(group_id, user_id)
    await casino_record_cmd.finish(result)


@trigger_event_cmd.handle()
async def _(event: GroupMessageEvent, args=CommandArg()):
    group_id = event.group_id
    
    # 检查是否为目标群聊(443234650)，只在该群聊中触发事件
    if group_id != 443234650:
        await trigger_event_cmd.finish("事件系统只在特定群聊中生效")
        
    arg_str = args.extract_plain_text().strip()
    
    if not arg_str:
        # 随机触发一个事件
        event_message = await trigger_random_event(group_id)
        if event_message:
            await trigger_event_cmd.finish(f"已触发随机事件：\n{event_message}")
        else:
            await trigger_event_cmd.finish("触发事件失败，请稍后再试")
    
    # 解析参数，格式：事件类型 子类型
    args_list = arg_str.split()
    if len(args_list) != 2 or not args_list[0].isdigit() or not args_list[1].isdigit():
        await trigger_event_cmd.finish("格式错误，正确格式：触发事件 [事件类型] [子类型]\n事件类型：0-自然灾害, 1-市场事件, 2-特殊事件, 3-贫富事件, 4-通胀事件")
    
    event_type = int(args_list[0])
    event_subtype = int(args_list[1])
    
    # 根据事件类型触发具体事件
    if event_type == EVENT_NATURAL_DISASTER:
        if event_subtype < 0 or event_subtype > 2:
            await trigger_event_cmd.finish("自然灾害子类型错误，可选：0-干旱, 1-风暴, 2-地震")
        from .event import trigger_natural_disaster
        event_message = await trigger_natural_disaster(group_id)
    
    elif event_type == EVENT_MARKET:
        if event_subtype < 0 or event_subtype > 1:
            await trigger_event_cmd.finish("市场事件子类型错误，可选：0-价格飙升, 1-市场崩溃")
        from .event import trigger_market_event
        event_message = await trigger_market_event(group_id)
    
    elif event_type == EVENT_SPECIAL:
        if event_subtype < 0 or event_subtype > 1:
            await trigger_event_cmd.finish("特殊事件子类型错误，可选：0-黄金时间, 1-能量提升")
        from .event import trigger_special_event
        event_message = await trigger_special_event(group_id)
    
    elif event_type == EVENT_WEALTH:
        from .event import trigger_wealth_event
        event_message = await trigger_wealth_event(group_id)
    
    elif event_type == EVENT_INFLATION:
        from .event import trigger_inflation_event
        event_message = await trigger_inflation_event(group_id)
    
    else:
        await trigger_event_cmd.finish("事件类型错误，可选：0-自然灾害, 1-市场事件, 2-特殊事件, 3-贫富事件, 4-通胀事件")
    
    await trigger_event_cmd.finish(f"已触发事件：\n{event_message}")


@test_event_system_cmd.handle()
async def test_event_system_handler(event: GroupMessageEvent):
    """测试事件系统是否正常工作"""
    from .event import test_event_system
    result = await test_event_system()
    await test_event_system_cmd.finish(f"事件系统测试结果: {result}")
