#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高考助手性能测试（模型 + 工具）
用法：python test.py
输出：5张PNG + 控制台报告
"""
import os
import time
import random
import json
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np
import matplotlib.pyplot as plt
import requests

# ---------- 1. 读取 API Key ----------
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zhangxuefengweb.settings')
import django

django.setup()
from django.conf import settings

API_KEY = settings.DASHSCOPE_API_KEY
MODEL = settings.DASHSCOPE_MODEL
if not API_KEY:
    raise Exception("未找到 DASHSCOPE_API_KEY")

# ---------- 2. 配置 ----------
TEST_COUNT = 12  # 每个场景测试次数
DASHSCOPE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
PROVINCE_CODE = {"四川": 51, "北京": 11, "上海": 31, "广东": 44, "江苏": 32}
SAMPLE_SCHOOLS = ["四川大学", "电子科技大学", "西南财经大学", "成都东软学院"]
SAMPLE_QUESTIONS = [
    "四川理科500分能上什么大学？",
    "张雪峰怎么看待计算机专业？",
    "成都东软学院怎么样？",
    "电子科技大学王牌专业有哪些？"
]

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


# ---------- 3. 工具函数（从原项目精简）----------
def search_university(school_name):
    """搜索大学，返回简短信息"""
    url = "https://api.zjzw.cn/web/api/"
    payload = {"uri": "apidata/api/gkv3/school/lists", "keyword": school_name, "size": 1}
    try:
        r = requests.post(url, json=payload, timeout=5)
        data = r.json().get('data', {}).get('item', [])
        if not data:
            return ""
        s = data[0]
        tags = []
        if s.get('f985') == 1: tags.append("985")
        if s.get('f211') == 1: tags.append("211")
        return f"{s.get('name')} - {s.get('province_name')} {' '.join(tags)}"
    except:
        return ""


def get_admission_score(school_name, province="四川"):
    """查询分数线"""
    try:
        # 获取学校ID
        url = "https://api.zjzw.cn/web/api/"
        payload = {"uri": "apidata/api/gkv3/school/lists", "keyword": school_name, "size": 1}
        r = requests.post(url, json=payload, timeout=5)
        schools = r.json().get('data', {}).get('item', [])
        if not schools:
            return ""
        school_id = schools[0].get('school_id')
        prov = PROVINCE_CODE.get(province, 51)
        score_url = f"https://static-data.gaokao.cn/www/2.0/schoolspecialscore/{school_id}/2025/{prov}.json"
        r2 = requests.get(score_url, timeout=5)
        items = r2.json().get('data', {}).values()
        scores = []
        for item in items:
            if item.get('item'):
                min_score = item['item'][0].get('min')
                if min_score:
                    scores.append(str(min_score))
        if scores:
            return f"{school_name} 最低 {scores[0]} 分"
        return ""
    except:
        return ""


# ---------- 4. 模型调用 ----------
def call_llm(messages):
    """返回 (回复内容, 耗时ms)"""
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "input": {"messages": messages},
        "parameters": {"result_format": "message", "temperature": 0.7}
    }
    start = time.perf_counter()
    try:
        resp = requests.post(DASHSCOPE_URL, headers=headers, json=payload, timeout=30)
        elapsed = (time.perf_counter() - start) * 1000
        if resp.status_code == 200:
            content = resp.json()['output']['choices'][0]['message']['content']
            return content, elapsed
        else:
            return f"错误码 {resp.status_code}", elapsed
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return f"异常: {e}", elapsed


def test_model_only():
    """纯模型调用（无工具）"""
    times = []
    for i in range(TEST_COUNT):
        q = random.choice(SAMPLE_QUESTIONS)
        msg = [{"role": "user", "content": q}]
        _, t = call_llm(msg)
        times.append(t)
        print(f"  模型 {i + 1}/{TEST_COUNT}: {t:.1f} ms")
        time.sleep(0.5)
    return times


def test_model_with_tool():
    """模型 + 工具（先工具查询，再构造 prompt 调用模型）"""
    times = []
    for i in range(TEST_COUNT):
        school = random.choice(SAMPLE_SCHOOLS)
        start_total = time.perf_counter()
        # 工具调用
        uni_info = search_university(school)
        score_info = get_admission_score(school, "四川")
        # 构造 prompt 并调用模型
        user_msg = f"请根据以下信息推荐报考建议：{uni_info}，{score_info}"
        msg = [{"role": "user", "content": user_msg}]
        _, _ = call_llm(msg)
        elapsed = (time.perf_counter() - start_total) * 1000
        times.append(elapsed)
        print(f"  带工具 {i + 1}/{TEST_COUNT}: {elapsed:.1f} ms")
        time.sleep(0.5)
    return times


def test_tools_only():
    """单独测工具函数耗时（不含模型）"""
    tool_times = {"search_university": [], "get_admission_score": []}
    for _ in range(TEST_COUNT):
        school = random.choice(SAMPLE_SCHOOLS)
        start = time.perf_counter()
        search_university(school)
        tool_times["search_university"].append((time.perf_counter() - start) * 1000)

        start = time.perf_counter()
        get_admission_score(school)
        tool_times["get_admission_score"].append((time.perf_counter() - start) * 1000)

    print("\n工具单独耗时:")
    for name, times in tool_times.items():
        print(f"  {name}: avg={np.mean(times):.1f}ms")
    return tool_times


# ---------- 5. 绘图 ----------
def plot_all(tool_times, model_times, model_tool_times):
    # 图1: 模型延迟对比箱线图
    plt.figure(figsize=(8, 6))
    data = [model_times, model_tool_times]
    bp = plt.boxplot(data, labels=["纯模型", "模型+工具"], patch_artist=True, showmeans=True)
    for box in bp['boxes']:
        box.set_facecolor('lightblue')
    plt.ylabel("响应时间 (ms)")
    plt.title("模型响应时间对比")
    plt.grid(axis='y', linestyle='--')
    plt.savefig("01_model_boxplot.png", dpi=150)
    plt.close()

    # 图2: 模型耗时直方图（两个子图）
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].hist(model_times, bins=10, edgecolor='black', color='steelblue')
    axes[0].set_title("纯模型")
    axes[0].set_xlabel("ms")
    axes[0].axvline(np.mean(model_times), color='red', linestyle='--')
    axes[1].hist(model_tool_times, bins=10, edgecolor='black', color='orange')
    axes[1].set_title("模型+工具")
    axes[1].set_xlabel("ms")
    axes[1].axvline(np.mean(model_tool_times), color='red', linestyle='--')
    plt.suptitle("响应时间分布")
    plt.tight_layout()
    plt.savefig("02_histograms.png", dpi=150)
    plt.close()

    # 图3: 工具单独耗时条形图 + 误差
    tools = list(tool_times.keys())
    means = [np.mean(tool_times[t]) for t in tools]
    stds = [np.std(tool_times[t]) for t in tools]
    plt.figure(figsize=(8, 5))
    bars = plt.bar(tools, means, yerr=stds, capsize=8, color=['#1f77b4', '#ff7f0e'])
    for bar, m in zip(bars, means):
        plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5, f"{m:.1f}", ha='center')
    plt.ylabel("平均耗时 (ms)")
    plt.title("工具调用耗时（不含模型）")
    plt.grid(axis='y', linestyle='--')
    plt.savefig("03_tools_bars.png", dpi=150)
    plt.close()

    # 图4: 时间序列折线图（模型 + 带工具）
    plt.figure(figsize=(10, 5))
    plt.plot(range(1, TEST_COUNT + 1), model_times, 'o-', label="纯模型", color='blue')
    plt.plot(range(1, TEST_COUNT + 1), model_tool_times, 's-', label="模型+工具", color='red')
    plt.xlabel("测试轮次")
    plt.ylabel("响应时间 (ms)")
    plt.title("响应时间变化趋势")
    plt.legend()
    plt.grid(True, linestyle='--')
    plt.savefig("04_timeseries.png", dpi=150)
    plt.close()

    # 图5: 饼图（总耗时占比：纯模型 vs 模型+工具 累计）
    total_model = sum(model_times)
    total_model_tool = sum(model_tool_times)
    plt.figure(figsize=(6, 6))
    plt.pie([total_model, total_model_tool], labels=["纯模型", "模型+工具"], autopct='%1.1f%%', startangle=90,
            shadow=True)
    plt.title("总耗时占比")
    plt.savefig("05_pie.png", dpi=150)
    plt.close()

    print("\n图表已生成：01~05.png")


# ---------- 6. 主程序 ----------
def main():
    print("=== 高考助手性能测试 ===")
    print(f"模型: {MODEL}")
    print(f"每项测试次数: {TEST_COUNT}\n")

    print("测试工具单独耗时...")
    tool_times = test_tools_only()

    print("\n测试纯模型调用...")
    model_times = test_model_only()

    print("\n测试模型+工具调用...")
    model_tool_times = test_model_with_tool()

    # 打印统计
    print("\n" + "=" * 50)
    print("统计摘要")
    print("=" * 50)
    print(
        f"纯模型: 平均 {np.mean(model_times):.1f}ms, 中位数 {np.median(model_times):.1f}ms, p95 {np.percentile(model_times, 95):.1f}ms")
    print(
        f"模型+工具: 平均 {np.mean(model_tool_times):.1f}ms, 中位数 {np.median(model_tool_times):.1f}ms, p95 {np.percentile(model_tool_times, 95):.1f}ms")
    for name, times in tool_times.items():
        print(f"{name}: 平均 {np.mean(times):.1f}ms, p95 {np.percentile(times, 95):.1f}ms")

    plot_all(tool_times, model_times, model_tool_times)
    print("\n全部完成！")


if __name__ == "__main__":
    main()