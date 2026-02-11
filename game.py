from .card import Card
from random import shuffle, randint, random
import sqlite3
from nonebot.adapters.onebot.v11 import Bot
from enum import Enum
from typing import List, Dict, Tuple, Optional, Union

# 导入数据库工具
from .db import db_tool

# 导入公共缓存模块
from .cache import cache_manager


# 添加游戏状态枚举类
class GameStatus(Enum):
    WAITING = 0    # 等待玩家加入
    PLAYING = 1    # 游戏进行中
    FINISHED = 2   # 游戏已结束


# 添加BlackJackGame类
class BlackJackGame:
    def __init__(self, game_id: int, group_id: int, creator_id: int, bet_amount: float, creator_name: str):
        self.game_id = game_id
        self.group_id = group_id
        self.creator_id = creator_id
        self.creator_name = creator_name
        self.opponent_id = None
        self.opponent_name = ""
        self.bet_amount = bet_amount
        self.status = GameStatus.WAITING
        self.deck = generate_cards()
        self.creator_cards = []
        self.opponent_cards = []
        
        shuffle(self.deck)
    
    @property
    def creator_points(self) -> int:
        return self._calculate_points(self.creator_cards)
    
    @property
    def opponent_points(self) -> int:
        return self._calculate_points(self.opponent_cards)
    
    def _calculate_points(self, cards: List[Card]) -> int:
        points = 0
        ace_count = 0
        
        for card in cards:
            if card.value == 1:  # Ace
                ace_count += 1
            elif card.value >= 10:  # 10, J, Q, K
                points += 10
            else:  # 2-9
                points += card.value
        
        # 处理A的点数
        while ace_count > 0:
            if points + 11 <= 21:
                points += 11
            else:
                points += 1
            ace_count -= 1
            
        return points
    
    def draw_card(self) -> Card:
        return self.deck.pop()
    
    def start_game(self, opponent_id: int, opponent_name: str) -> bool:
        if self.status != GameStatus.WAITING or self.opponent_id is not None:
            return False
            
        self.opponent_id = opponent_id
        self.opponent_name = opponent_name
        self.status = GameStatus.PLAYING
        
        # 初始发牌
        self.creator_cards.append(self.draw_card())
        self.creator_cards.append(self.draw_card())
        self.opponent_cards.append(self.draw_card())
        self.opponent_cards.append(self.draw_card())
        
        return True
    
    def hit(self, player_id: int) -> bool:
        """玩家要牌"""
        if self.status != GameStatus.PLAYING:
            return False
            
        if player_id == self.creator_id:
            self.creator_cards.append(self.draw_card())
            if self.creator_points > 21:
                self.status = GameStatus.FINISHED
            return True
        elif player_id == self.opponent_id:
            self.opponent_cards.append(self.draw_card())
            if self.opponent_points > 21:
                self.status = GameStatus.FINISHED
            return True
        return False
    
    def stand(self, player_id: int) -> bool:
        """玩家停牌"""
        if self.status != GameStatus.PLAYING:
            return False
            
        # 如果是庄家停牌，对手自动补牌
        if player_id == self.creator_id:
            while self.opponent_points < 17:
                self.opponent_cards.append(self.draw_card())
            self.status = GameStatus.FINISHED
            return True
        # 如果是对手停牌，庄家自动补牌
        elif player_id == self.opponent_id:
            while self.creator_points < 17:
                self.creator_cards.append(self.draw_card())
            self.status = GameStatus.FINISHED
            return True
        return False
    
    def get_winner(self) -> Optional[int]:
        """获取赢家ID，平局返回None"""
        if self.status != GameStatus.FINISHED:
            return None
            
        creator_pts = self.creator_points
        opponent_pts = self.opponent_points
        
        # 爆牌判断
        if creator_pts > 21 and opponent_pts > 21:
            return None  # 双方都爆牌，平局
        if creator_pts > 21:
            return self.opponent_id  # 庄家爆牌，对手赢
        if opponent_pts > 21:
            return self.creator_id  # 对手爆牌，庄家赢
        
        # 点数比较
        if creator_pts > opponent_pts:
            return self.creator_id
        elif opponent_pts > creator_pts:
            return self.opponent_id
        else:
            return None  # 平局


def generate_cards():
    cards = []
    for i in range(52):
        cards.append(Card(i))
    return cards


class Deck:
    def __init__(self, deck_id: int, group: int, player1: int, point: int, player1_name: str):
        self.deck_id = deck_id
        self.group = group
        self.player1 = player1
        self.player1_name = player1_name
        self.player2: Optional[int] = None
        self.player2_name = ""
        self.point = point
        self.cards = generate_cards()
        self.player1_cards = []
        self.player2_cards = []

        shuffle(self.cards)

    @property
    def player1_point(self):
        return self.get_player_card_points(1)

    @property
    def player2_point(self):
        return self.get_player_card_points(2)

    def pick_one_card(self):
        return self.cards.pop()

    def init_game(self):
        card1 = self.pick_one_card()
        card2 = self.pick_one_card()
        card3 = self.pick_one_card()
        card4 = self.pick_one_card()
        self.player1_cards += [card1, card2]
        self.player2_cards += [card3, card4]

    def get_player_card_points(self, player_num: int):
        cards = [0, self.player1_cards, self.player2_cards]
        point = 0
        ace_num = 0
        for card in cards[player_num]:
            if card.value == 1:
                ace_num += 1
            elif card.value >= 10:
                point += 10
            else:
                point += card.value
        while ace_num > 0:
            if point + 11 <= 21:
                point += 11
            else:
                point += 1
            ace_num -= 1
        return point

    def get_one_card(self, player):
        cards = [0, self.player1_cards, self.player2_cards]
        player_cards = cards[player]
        player_cards += [self.pick_one_card()]


game_ls = []


async def add_game(group: int, uid: int, point: int, player1_name: str) -> int:
    if game_ls:
        latest_deck_id = game_ls[-1].deck_id
        game_ls.append(Deck(latest_deck_id + 1, group, uid, point, player1_name))
        return latest_deck_id + 1
    else:
        game = Deck(1, group, uid, point, player1_name)
        game_ls.append(game)
        return game.deck_id


async def start_game(deck_id: int, player2: int, player2_name: str, group_id: int, user_point: int) -> str:
    if not game_ls:
        return '目前还没有开始任何游戏！'
    for index, game in enumerate(game_ls):
        game: Deck
        if deck_id == game.deck_id and game.player2 is None and game.player1 != player2 and game.group == group_id \
                and user_point >= game.point:
            game.player2 = player2
            game.player2_name = player2_name
            game.init_game()
            player2_point = game.get_player_card_points(2)
            words = f"{game.player1_name}的牌为\n{game.player1_cards[0]} ?\n{game.player2_name}的牌为\n"
            for card in game.player2_cards:
                words += str(card)
            if player2_point == 21:
                words += f"\n黑杰克！牌点为21点\n{game.player2_name}获胜了！"
                result = await count_score(game, 2)
                words += result
                del game_ls[index]
                return words
            else:
                words += f"\n牌点为{player2_point}"
                return words
        elif deck_id == game.deck_id and game.player2 is not None:
            return '该游戏已开始！'
        elif deck_id == game.deck_id and game.player1 == player2:
            return '不能和自己玩！'
        elif deck_id == game.deck_id and game.group != group_id:
            return '不能和群外的玩！'
        elif deck_id == game.deck_id and user_point < game.point:
            return '你的点数不足以游玩该游戏！'
    return '未找到游戏！'


async def call_card(deck_id: int, player: int) -> str:
    if not game_ls:
        return '目前还没有开始任何游戏！'
    for index, game in enumerate(game_ls):
        game: Deck
        if deck_id == game.deck_id and game.player2 == player:
            game.get_one_card(2)
            player2_point = game.player2_point
            words = f"{game.player2_name}的牌为\n"
            for card in game.player2_cards:
                words += str(card)
            if player2_point > 21:
                words += f"\n牌点为{player2_point}\n爆牌！{game.player2_name}输了！\n"
                result = await count_score(game, 1)
                words += result
                del game_ls[index]
                return words
            elif player2_point == 21:
                words += f"\n牌点为{player2_point}\n"
                while game.player1_point < game.player2_point and game.player1_point <= 21:
                    game.get_one_card(1)
                words += f"对手的牌为"
                for card in game.player1_cards:
                    words += str(card)
                words += f"\n牌点为{game.player1_point}\n"
                if game.player1_point > 21:
                    result = await count_score(game, 2)
                else:

                    result = await count_score(game, 0)
                words += result
                del game_ls[index]
                return words
            else:
                words += f"\n牌点为{player2_point}"
                return words
        elif deck_id == game.deck_id and game.player2 != player:
            return '该游戏已开始！'
    return '未找到游戏！'


async def stop_card(deck_id: int, player: int) -> str:
    if not game_ls:
        return '目前还没有开始任何游戏！'
    for index, game in enumerate(game_ls):
        game: Deck
        if deck_id == game.deck_id and game.player2 == player:
            while game.player1_point < game.player2_point and game.player1_point <= 21:
                game.get_one_card(1)
            words = f"{game.player1_name}的牌为\n"
            for card in game.player1_cards:
                words += str(card)
            words += f"\n牌点为{game.player1_point}\n"
            if game.player1_point > 21:
                result = await count_score(game, 2)
            elif game.player1_point < game.player2_point:
                result = await count_score(game, 2)
            elif game.player1_point > game.player2_point:
                result = await count_score(game, 1)
            else:
                result = await count_score(game, 0)
            words += result
            del game_ls[index]
            return words
        elif deck_id == game.deck_id and game.player2 != player:
            return '该游戏已开始！'
    return '未找到游戏！'


async def count_score(game: Deck, player_win: int):
    player1_point = get_point(game.group, game.player1)
    # 确保player2不为None再获取点数
    player2_point = get_point(game.group, game.player2) if game.player2 is not None else 0.0
    if player_win == 1:
        winner_point = player1_point
        loser_point = player2_point
        winner = game.player1
        loser = game.player2
        winner_name = game.player1_name
        loser_name = game.player2_name
    elif player_win == 2:
        winner_point = player2_point
        loser_point = player1_point
        winner = game.player2
        loser = game.player1
        winner_name = game.player2_name
        loser_name = game.player1_name
    else:
        return "\n平局！"
    top_bonus = float(game.point * 0.1)
    winner_bonus = round(random() * top_bonus, 2)  # 使用小数
    loser_bonus = round(random() * 2 * top_bonus - top_bonus, 2)  # 使用小数
    winner_dif_point = game.point + winner_bonus
    loser_dif_point = -game.point + loser_bonus

    winner_point += winner_dif_point
    loser_point += loser_dif_point
    # 确保winner不为None再更新点数
    if winner is not None:
        update_point(game.group, winner, winner_point)
    # 确保loser不为None再更新点数
    if loser is not None:
        update_point(game.group, loser, loser_point)
    words = f"{winner_name}获胜\n{winner_name}获得{game.point}金币！并且获得{winner_bonus}金币奖励\n" \
            f"{winner_name}现在的金币为{winner_point}\n{loser_name}失败"
    if loser_bonus > 0:
        words += f" 但获得{loser_bonus}金币奖励"
    elif loser_bonus < 0:
        words += f" 并获得{-loser_bonus}金币惩罚"
    words += f"\n{loser_name}现在的金币为{loser_point}"
    return words


def get_user_point(group: int, uid: int) -> float:
    # 先检查缓存
    cache_key = (group, uid)
    hit, point = cache_manager.get_cached_value("user_point_cache", cache_key)
    if hit:
        return point
    
    # 从数据库获取
    sql = f"select * from sign_in where belonging_group={group} and uid={uid}"
    result = db_tool.execute_one(sql)
    if result:
        point = float(result[3])
    else:
        point = 0.0
    
    # 更新缓存
    cache_manager.set_cached_value("user_point_cache", cache_key, point)
    
    return point


def update_point(group: int, uid: int, point: float):
    # 更新数据库
    sql = f"""update sign_in set points={point} where belonging_group={group} and uid={uid}"""
    db_tool.execute_update(sql)
    
    # 更新缓存
    cache_key = (group, uid)
    cache_manager.set_cached_value("user_point_cache", cache_key, point)


def get_point(group: int, uid: int) -> float:
    # 先检查缓存
    cache_key = (group, uid)
    hit, point = cache_manager.get_cached_value("user_point_cache", cache_key)
    if hit:
        return point
    
    # 从数据库获取
    sql = f"select * from sign_in where belonging_group={group} and uid={uid}"
    result = db_tool.execute_one(sql)
    if result:
        point = float(result[3])
    else:
        point = 0.0
    
    # 更新缓存
    cache_manager.set_cached_value("user_point_cache", cache_key, point)
    
    return point


def init():
    sql = """create table if not exists sign_in(
        id integer primary key autoincrement,
        sign_in_date datetime not null,
        total_sign_in int not null,
        points int not null,
        belonging_group int not null,
        uid int not null,
        today_point int
    )
    """
    db_tool.execute_update(sql)

# 初始化数据库
init()

# 定期清理缓存的函数
def clear_cache():
    cache_manager.clear_cache("user_point_cache")

# 导入定时器
import asyncio

# 定期清理缓存（每5分钟）
async def schedule_cache_clear():
    while True:
        await asyncio.sleep(300)
        clear_cache()


async def get_game_ls(group: int):
    s = ""
    for game in game_ls:
        if game.group == group:
            s += f"游戏id:{game.deck_id} 发起人:{game.player1_name} 游戏底金:{game.point}\n"
            if game.player2 is not None:
                s += f"{game.player2_name}正在游戏中\n"
            else:
                s += f"等待玩家二中\n"
    if not s:
        return "当前没有进行中的游戏！"
    return s[:-1]


def duel(group: int, point: float, challenger: int, challenger_point: float, challenger_name: str,
         acceptor: int, acceptor_point: float, acceptor_name: str):
    if random() > 0.5:
        winner_point = challenger_point
        loser_point = acceptor_point
        winner = challenger
        loser = acceptor
        winner_name = challenger_name
        loser_name = acceptor_name
    else:
        winner_point = acceptor_point
        loser_point = challenger_point
        winner = acceptor
        loser = challenger
        winner_name = acceptor_name
        loser_name = challenger_name
    top_bonus = float(point * 0.1)
    winner_bonus = round(random() * top_bonus, 2)  # 使用小数
    loser_bonus = round(random() * 2 * top_bonus - top_bonus, 2)  # 使用小数
    winner_dif_point = point + winner_bonus
    loser_dif_point = -point + loser_bonus

    winner_point += winner_dif_point
    loser_point += loser_dif_point
    update_point(group, winner, winner_point)
    update_point(group, loser, loser_point)
    words = f"{winner_name}获胜！获得{point}金币！并且获得{winner_bonus}金币奖励 现在的金币为{winner_point}\n{loser_name}失败"
    if loser_bonus > 0:
        words += f"但获得{loser_bonus}金币奖励！"
    elif loser_bonus < 0:
        words += f"并获得{-loser_bonus}金币惩罚！"
    words += f"现在的金币为{loser_point}"
    return words


# 定义全局变量battle_dic，避免循环导入
battle_dic: Dict[int, List[List[int]]] = {}

def add_dual(group: int, uid: int, point: int) -> int:
    """添加对战"""
    if group not in battle_dic or not battle_dic[group]:
        battle_dic[group] = [[1, uid, point]]
        return 1
    battle_id = battle_dic[group][-1][0] + 1
    battle_dic[group].append([battle_id, uid, point])
    return battle_id


def get_battle_info(group: int, battle_id: int) -> list:
    """获取对战信息"""
    if group not in battle_dic or battle_id <= 0:
        return []
    for i in battle_dic[group]:
        if i[0] == battle_id:
            return i
    return []


async def get_rank(group_id: int, bot: Bot) -> str:
    # 获取总金币排名
    sql = f'select uid, points from sign_in where belonging_group={group_id} order by points desc limit 3'
    data = db_tool.execute_query(sql)
    count = 1
    msg = "签到金币排名\n"
    for i in data:
        uid = i[0]
        points = i[1]
        sender = await bot.get_group_member_info(group_id=group_id, user_id=uid)
        name = sender['card'] or sender.get('nickname', '')
        msg += f'第{count}名：{name}  {points}金币\n'
        count += 1
    
    # 获取今日金币排名
    sql = f"select uid, today_point from sign_in where belonging_group={group_id} " \
          f"and sign_in_date = date('now', 'localtime') order by today_point desc limit 5"
    data = db_tool.execute_query(sql)
    msg += "\n今日签到金币排名\n"
    count = 1
    for i in data:
        uid = i[0]
        points = i[1]
        sender = await bot.get_group_member_info(group_id=group_id, user_id=uid)
        name = sender['card'] or sender.get('nickname', '')
        msg += f'第{count}名：{name}  {points}金币\n'
        count += 1
    return msg[:-1]
