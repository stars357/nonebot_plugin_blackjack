import random
import numpy as np

def simulate_rental_scenario_1(num_simulations=10000):
    """
    情况一：月租1140元，月付，从第2个月开始每月5%跑路概率，跑路亏损两个月房租
    """
    monthly_rent = 1140
    total_costs = []
    losses = []
    
    for _ in range(num_simulations):
        total_cost = 0
        loss = 0
        ran_away = False
        
        # 第1个月正常付租
        total_cost += monthly_rent
        
        # 第2-12个月，每月5%概率跑路
        for month in range(2, 13):
            if not ran_away:
                total_cost += monthly_rent
                # 5%概率跑路
                if random.random() < 0.05:
                    ran_away = True
                    # 根据跑路月份计算亏损：第12个月跑路只损失1个月房租，其他月份损失2个月房租
                    if month == 12:
                        loss = 1 * monthly_rent  # 第12个月跑路只亏损一个月房租
                    else:
                        loss = 2 * monthly_rent  # 其他月份跑路亏损两个月房租
                    break
        
        total_costs.append(total_cost)
        losses.append(loss)
    
    return total_costs, losses

def simulate_rental_scenario_2():
    """
    情况二：月租1300元，季付，不跑路，每年收180元管理费
    """
    monthly_rent = 1300
    annual_management_fee = 180
    
    # 一年总花费
    total_cost = monthly_rent * 12 + annual_management_fee
    loss = 0  # 不会跑路，无亏损
    
    return total_cost, loss

def analyze_scenarios():
    print("租房方案对比分析")
    print("=" * 50)
    
    # 模拟情况一
    print("\n情况一：月租1140元，月付，从第2个月开始每月5%跑路概率")
    costs_1, losses_1 = simulate_rental_scenario_1()
    
    avg_cost_1 = np.mean(costs_1)
    avg_loss_1 = np.mean(losses_1)
    max_cost_1 = max(costs_1)
    min_cost_1 = min(costs_1)
    
    # 计算跑路概率
    runaway_count = sum(1 for loss in losses_1 if loss > 0)
    runaway_probability = runaway_count / len(losses_1)
    
    print(f"平均总花费：{avg_cost_1:.2f}元")
    print(f"平均亏损：{avg_loss_1:.2f}元")
    print(f"最高花费：{max_cost_1}元")
    print(f"最低花费：{min_cost_1}元")
    print(f"实际跑路概率：{runaway_probability:.2%}")
    
    # 情况二
    print("\n情况二：月租1300元，季付，不跑路，每年收180元管理费")
    cost_2, loss_2 = simulate_rental_scenario_2()
    
    print(f"总花费：{cost_2}元")
    print(f"亏损：{loss_2}元")
    
    # 对比分析
    print("\n对比分析")
    print("=" * 30)
    print(f"情况一平均总成本：{avg_cost_1 + avg_loss_1:.2f}元")
    print(f"情况二总成本：{cost_2}元")
    
    cost_difference = (avg_cost_1 + avg_loss_1) - cost_2
    if cost_difference > 0:
        print(f"情况一比情况二平均多花费：{cost_difference:.2f}元")
    else:
        print(f"情况二比情况一平均多花费：{abs(cost_difference):.2f}元")
    
    # 风险分析
    print("\n风险分析")
    print("=" * 30)
    worst_case_1 = max_cost_1 + 2280  # 最坏情况：第2-11个月跑路，付满该月+跑路亏损2个月房租
    print(f"情况一最坏情况总成本：{worst_case_1}元（第2-11个月跑路）")
    print(f"情况一第12个月跑路总成本：{12 * 890 + 890}元")
    print(f"情况二确定总成本：{cost_2}元")
    
    # 详细统计
    print("\n详细统计（基于10000次模拟）")
    print("=" * 40)
    
    # 计算不同花费区间的概率
    total_costs_with_loss_1 = [cost + loss for cost, loss in zip(costs_1, losses_1)]
    
    ranges = [
        (0, 13000, "低于13000元"),
        (13000, 14000, "13000-14000元"),
        (14000, 15000, "14000-15000元"),
        (15000, 16000, "15000-16000元"),
        (16000, float('inf'), "高于16000元")
    ]
    
    print("情况一花费分布：")
    for min_val, max_val, label in ranges:
        count = sum(1 for cost in total_costs_with_loss_1 if min_val <= cost < max_val)
        percentage = count / len(total_costs_with_loss_1) * 100
        print(f"  {label}：{percentage:.1f}%")

if __name__ == "__main__":
    # 设置随机种子以便结果可重现
    random.seed(42)
    np.random.seed(42)
    
    analyze_scenarios()
    
    print("\n\n理论计算验证")
    print("=" * 50)
    
    # 理论计算情况一的期望
    # 从第2个月开始每月跑路概率5%，11个月内跑路的概率
    # P(不跑路) = 0.95^11 ≈ 0.569
    # 期望跑路月份计算较复杂，用模拟结果更准确
    
    monthly_rent_1 = 890
    monthly_rent_2 = 1300
    management_fee_2 = 180
    
    print(f"情况一基础年租金：{monthly_rent_1 * 12}元")
    print(f"情况二基础年租金：{monthly_rent_2 * 12}元")
    print(f"情况二管理费：{management_fee_2}元")
    print(f"情况二总费用：{monthly_rent_2 * 12 + management_fee_2}元")
    
    # 计算情况一在不同跑路时间的成本
    print("\n情况一不同跑路时间的成本：")
    for month in range(2, 12):
        cost_if_runaway = month * monthly_rent_1 + 2 * monthly_rent_1
        print(f"  第{month}个月跑路：{cost_if_runaway}元（亏损2个月房租）")
    
    # 第12个月跑路特殊处理
    cost_if_runaway_12 = 12 * monthly_rent_1 + 1 * monthly_rent_1
    print(f"  第12个月跑路：{cost_if_runaway_12}元（亏损1个月房租）")
    
    print(f"  不跑路（12个月）：{12 * monthly_rent_1}元")