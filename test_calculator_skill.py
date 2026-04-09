#!/usr/bin/env python3
"""测试 Calculator Skill

使用方式：
    uv run test_calculator_skill.py
"""

import asyncio
from skills.calculator import calculate, calculate_sync


async def test_async():
    """测试异步调用"""
    print("=== 测试异步调用 ===")
    
    # 测试基础运算
    result = await calculate("2 + 3 * 4")
    print(result)
    
    # 测试数学函数
    result = await calculate("sqrt(16)")
    print(result)
    
    # 测试三角函数
    result = await calculate("sin(pi/2)")
    print(result)
    
    # 测试幂运算
    result = await calculate("2 ** 10")
    print(result)
    
    # 测试复合表达式
    result = await calculate("sqrt(16) + pow(2, 3)")
    print(result)


def test_sync():
    """测试同步调用"""
    print("\n=== 测试同步调用 ===")
    
    # 测试基础运算
    result = calculate_sync("10 - 4")
    print(result)
    
    # 测试数学函数
    result = calculate_sync("log(100, 10)")
    print(result)
    
    # 测试错误处理
    result = calculate_sync("unknown_function(123)")
    print(result)


async def main():
    """主函数"""
    await test_async()
    test_sync()
    
    print("\n所有测试通过！")


if __name__ == "__main__":
    asyncio.run(main())
