# services/memorial.py
import os
import json
from datetime import datetime
from pathlib import Path
from django.conf import settings

# 张雪峰老师去世时间: 2026年3月24日 15:50:00
ZHANG_XUEFENG_PASSING_TIME = datetime(2026, 3, 24, 15, 50, 0)

# 数据文件路径
MEMORIAL_DATA_FILE = os.path.join(settings.BASE_DIR, 'static', 'activities', 'memorial_data.json')


def ensure_data_file():
    """确保数据文件存在"""
    os.makedirs(os.path.dirname(MEMORIAL_DATA_FILE), exist_ok=True)
    if not os.path.exists(MEMORIAL_DATA_FILE):
        with open(MEMORIAL_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({'total_flowers': 0, 'users': {}}, f, ensure_ascii=False)


def get_memorial_stats():
    """获取悼念统计数据"""
    ensure_data_file()
    try:
        with open(MEMORIAL_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('total_flowers', 0)
    except (json.JSONDecodeError, FileNotFoundError):
        return 0


def add_flower(user_id, username):
    """添加献花"""
    ensure_data_file()
    try:
        with open(MEMORIAL_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        data = {'total_flowers': 0, 'users': {}}

    # 更新统计
    data['total_flowers'] = data.get('total_flowers', 0) + 1

    # 记录用户献花次数
    user_key = str(user_id)
    if user_key not in data['users']:
        data['users'][user_key] = {'username': username, 'count': 0}
    data['users'][user_key]['count'] += 1

    with open(MEMORIAL_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data['total_flowers']


def get_time_since_passing():
    """计算张老师去世至今的时间差"""
    now = datetime.now()
    delta = now - ZHANG_XUEFENG_PASSING_TIME

    # 计算各项时间
    years = delta.days // 365
    remaining_days = delta.days % 365
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    seconds = delta.seconds % 60

    # 总天数
    total_days = delta.days

    # 总分钟数
    total_minutes = delta.days * 24 * 60 + delta.seconds // 60

    # 总秒数
    total_seconds = int(delta.total_seconds())

    return {
        'years': years,
        'days': remaining_days,
        'total_days': total_days,
        'hours': hours,
        'minutes': minutes,
        'total_minutes': total_minutes,
        'seconds': seconds,
        'total_seconds': total_seconds,
        'passing_time': ZHANG_XUEFENG_PASSING_TIME.strftime('%Y年%m月%d日 %H:%M:%S')
    }