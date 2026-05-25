# admin_views.py
import os

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.contrib.auth.hashers import make_password
import json
import re
from datetime import datetime, timedelta
from collections import Counter

from zhangxuefengweb import settings
from .cache_utils import StatsCache
from .models import User, Conversation, Message, VerificationCode
from .decorators import login_required_view


def admin_login_required(view_func):
    """管理员登录验证装饰器"""

    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/auth/')
        # 检查是否为管理员（用户名或密码为 zhangxuefeng）
        if request.user.username != 'zhangxuefeng' and request.user.phone != 'zhangxuefeng':
            return render(request, 'admin/dashboard.html')
        return view_func(request, *args, **kwargs)

    return wrapper


@admin_login_required
def admin_dashboard(request):
    """管理员后台首页"""
    return render(request, 'admin/dashboard.html')


@admin_login_required
@require_http_methods(["GET"])
def admin_stats(request):
    """获取统计数据"""
    # 用户统计
    total_users = User.objects.count()
    today_users = User.objects.filter(date_joined__date=timezone.now().date()).count()
    week_users = User.objects.filter(date_joined__gte=timezone.now() - timedelta(days=7)).count()

    # 对话统计
    total_conversations = Conversation.objects.count()
    today_conversations = Conversation.objects.filter(created_at__date=timezone.now().date()).count()
    avg_messages_per_conv = Message.objects.count() / total_conversations if total_conversations > 0 else 0

    # 消息统计
    total_messages = Message.objects.count()
    today_messages = Message.objects.filter(created_at__date=timezone.now().date()).count()
    user_messages = Message.objects.filter(role='user').count()
    assistant_messages = Message.objects.filter(role='assistant').count()

    # 近7天对话趋势
    trend_data = []
    for i in range(6, -1, -1):
        date = timezone.now().date() - timedelta(days=i)
        count = Conversation.objects.filter(created_at__date=date).count()
        trend_data.append({
            'date': date.strftime('%m-%d'),
            'count': count
        })

    # 活跃用户排行
    active_users = User.objects.annotate(
        conv_count=Count('conversations')
    ).order_by('-conv_count')[:10].values('id', 'username', 'nickname', 'conv_count')

    return JsonResponse({
        'success': True,
        'users': {
            'total': total_users,
            'today': today_users,
            'week': week_users
        },
        'conversations': {
            'total': total_conversations,
            'today': today_conversations,
            'avg_messages': round(avg_messages_per_conv, 1)
        },
        'messages': {
            'total': total_messages,
            'today': today_messages,
            'user': user_messages,
            'assistant': assistant_messages
        },
        'trend': trend_data,
        'active_users': list(active_users)
    })


@admin_login_required
@require_http_methods(["GET"])
def admin_users(request):
    """获取用户列表"""
    users = User.objects.all().order_by('-date_joined')
    data = []
    for user in users:
        conv_count = user.conversations.count()
        msg_count = sum(conv.messages.count() for conv in user.conversations.all())
        data.append({
            'id': str(user.id),
            'username': user.username,
            'nickname': user.nickname,
            'phone': user.phone,
            'avatar_url': user.get_avatar_url(),
            'conv_count': conv_count,
            'msg_count': msg_count,
            'date_joined': user.date_joined.strftime('%Y-%m-%d %H:%M'),
            'last_login': user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else '-'
        })
    return JsonResponse({'users': data})


@admin_login_required
@require_http_methods(["GET"])
def admin_conversations(request):
    """获取所有对话记录"""
    conversations = Conversation.objects.select_related('user').all().order_by('-created_at')
    data = []
    for conv in conversations:
        data.append({
            'id': conv.session_id,
            'user': conv.user.username if conv.user else '匿名用户',
            'user_id': str(conv.user.id) if conv.user else None,
            'title': conv.title,
            'message_count': conv.messages.count(),
            'created_at': conv.created_at.strftime('%Y-%m-%d %H:%M'),
            'updated_at': conv.updated_at.strftime('%Y-%m-%d %H:%M')
        })
    return JsonResponse({'conversations': data})


@admin_login_required
@require_http_methods(["GET"])
def admin_messages(request):
    """获取消息记录"""
    limit = int(request.GET.get('limit', 100))
    messages = Message.objects.select_related('conversation__user').all().order_by('-created_at')[:limit]
    data = []
    for msg in messages:
        data.append({
            'id': msg.id,
            'conversation_id': msg.conversation.session_id,
            'user': msg.conversation.user.username if msg.conversation.user else '匿名用户',
            'role': msg.role,
            'content': msg.content[:200] + '...' if len(msg.content) > 200 else msg.content,
            'content_full': msg.content,
            'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    return JsonResponse({'messages': data})


@admin_login_required
@require_http_methods(["GET"])
def admin_wordcloud(request):
    """获取词频统计数据"""
    # 获取所有用户消息
    user_messages = Message.objects.filter(role='user').values_list('content', flat=True)

    # 加载停用词表
    stopwords = set()
    stopwords_path = os.path.join(settings.BASE_DIR, 'static', 'stopwords.txt')

    try:
        with open(stopwords_path, 'r', encoding='utf-8') as f:
            for line in f:
                word = line.strip()
                if word:
                    stopwords.add(word)
    except FileNotFoundError:
        # 如果文件不存在，使用默认停用词
        stopwords = {'的', '了', '是', '我', '你', '他', '她', '它', '我们', '你们', '他们', '这', '那', '有', '在',
                     '不', '也', '都', '说', '就', '要', '会', '可以', '能', '想', '问', '帮', '请', '吧', '吗', '呢',
                     '啊', '哦', '嗯', '哈哈', '谢谢'}

    word_counter = Counter()

    for msg in user_messages:
        # 提取中文词汇（长度>=2）
        words = re.findall(r'[\u4e00-\u9fa5]{2,}', msg)
        for word in words:
            if word not in stopwords and len(word) >= 2:
                word_counter[word] += 1

    # 过滤低频词（出现次数<2的过滤掉）
    filtered_words = {w: c for w, c in word_counter.items() if c >= 2}

    # 返回前100个高频词
    top_words = Counter(filtered_words).most_common(100)

    # 生成词云数据格式
    words_data = [{'name': w, 'value': c} for w, c in top_words]

    return JsonResponse({
        'success': True,
        'words': words_data,
        'total_words': sum(filtered_words.values())
    })


@admin_login_required
@require_http_methods(["GET"])
def admin_logs(request):
    """获取用户操作日志（基于会话和消息）"""
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))

    # 获取所有会话，按更新时间倒序
    conversations = Conversation.objects.select_related('user').all().order_by('-updated_at')

    logs = []
    for conv in conversations:
        logs.append({
            'time': conv.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'user': conv.user.username if conv.user else '匿名用户',
            'action': f'创建/更新对话: {conv.title}',
            'details': f'会话ID: {conv.session_id}, 消息数: {conv.messages.count()}'
        })

    # 添加用户登录日志
    users = User.objects.exclude(last_login=None).order_by('-last_login')
    for user in users:
        logs.append({
            'time': user.last_login.strftime('%Y-%m-%d %H:%M:%S'),
            'user': user.username,
            'action': '用户登录',
            'details': f'昵称: {user.nickname or user.username}'
        })

    # 按时间排序
    logs.sort(key=lambda x: x['time'], reverse=True)

    # 分页
    total = len(logs)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_logs = logs[start:end]

    return JsonResponse({
        'logs': paginated_logs,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size
    })


@admin_login_required
@csrf_exempt
@require_http_methods(["POST"])
def admin_delete_user(request, user_id):
    """删除用户"""
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(id=user_id)

        # 不能删除管理员
        if user.username == 'zhangxuefeng':
            return JsonResponse({'error': '不能删除管理员账户'}, status=400)

        user.delete()
        return JsonResponse({'success': True, 'message': '用户已删除'})
    except User.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=404)


@admin_login_required
@csrf_exempt
@require_http_methods(["POST"])
def admin_delete_conversation(request, conv_id):
    """删除对话"""
    try:
        conversation = Conversation.objects.get(session_id=conv_id)
        conversation.delete()
        return JsonResponse({'success': True, 'message': '对话已删除'})
    except Conversation.DoesNotExist:
        return JsonResponse({'error': '对话不存在'}, status=404)


@admin_login_required
@require_http_methods(["GET"])
def admin_token_stats(request):
    """Token使用统计（模拟数据）"""
    # 获取所有消息，计算字符数作为token估算
    messages = Message.objects.all()
    total_chars = sum(len(msg.content) for msg in messages)
    # 估算token（约1.5字符/token）
    total_tokens = int(total_chars / 1.5)

    # 按天统计
    daily_stats = []
    for i in range(6, -1, -1):
        date = timezone.now().date() - timedelta(days=i)
        day_msgs = Message.objects.filter(created_at__date=date)
        day_chars = sum(len(msg.content) for msg in day_msgs)
        day_tokens = int(day_chars / 1.5)
        daily_stats.append({
            'date': date.strftime('%m-%d'),
            'messages': day_msgs.count(),
            'tokens': day_tokens
        })

    return JsonResponse({
        'success': True,
        'total_tokens': total_tokens,
        'total_chars': total_chars,
        'total_messages': messages.count(),
        'daily_stats': daily_stats,
        'avg_per_message': int(total_tokens / messages.count()) if messages.count() > 0 else 0
    })


# admin_views.py - 修复 admin_stats 函数

@admin_login_required
@require_http_methods(["GET"])
def admin_stats(request):
    """获取统计数据（带缓存）"""
    # 尝试从缓存获取
    cache_key = 'dashboard_stats'
    cached_data = StatsCache.get(cache_key, max_age_minutes=10)

    if cached_data:
        return JsonResponse(cached_data)

    try:
        # 用户统计
        total_users = User.objects.count()
        today_users = User.objects.filter(date_joined__date=timezone.now().date()).count()
        week_users = User.objects.filter(date_joined__gte=timezone.now() - timedelta(days=7)).count()

        # 对话统计
        total_conversations = Conversation.objects.count()
        today_conversations = Conversation.objects.filter(created_at__date=timezone.now().date()).count()
        avg_messages_per_conv = 0
        if total_conversations > 0:
            total_msgs = Message.objects.count()
            avg_messages_per_conv = round(total_msgs / total_conversations, 1)

        # 消息统计
        total_messages = Message.objects.count()
        today_messages = Message.objects.filter(created_at__date=timezone.now().date()).count()
        user_messages = Message.objects.filter(role='user').count()
        assistant_messages = Message.objects.filter(role='assistant').count()

        # 近7天对话趋势
        trend_data = []
        for i in range(6, -1, -1):
            date = timezone.now().date() - timedelta(days=i)
            count = Conversation.objects.filter(created_at__date=date).count()
            trend_data.append({
                'date': date.strftime('%m-%d'),
                'count': count
            })

        # 活跃用户排行（有对话的用户）
        from django.db.models import Count
        active_users = User.objects.filter(conversations__isnull=False).annotate(
            conv_count=Count('conversations')
        ).order_by('-conv_count')[:10].values('id', 'username', 'nickname', 'conv_count')

        result = {
            'success': True,
            'users': {
                'total': total_users,
                'today': today_users,
                'week': week_users
            },
            'conversations': {
                'total': total_conversations,
                'today': today_conversations,
                'avg_messages': avg_messages_per_conv
            },
            'messages': {
                'total': total_messages,
                'today': today_messages,
                'user': user_messages,
                'assistant': assistant_messages
            },
            'trend': list(trend_data),
            'active_users': list(active_users)
        }

        # 保存到缓存
        StatsCache.set(cache_key, result)

        return JsonResponse(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@admin_login_required
@require_http_methods(["GET"])
def admin_users(request):
    """获取用户列表（带缓存）"""
    cache_key = 'users_list'
    cached_data = StatsCache.get(cache_key, max_age_minutes=5)

    if cached_data:
        return JsonResponse({'users': cached_data})

    users = User.objects.all().order_by('-date_joined')
    data = []
    for user in users:
        conv_count = user.conversations.count()
        msg_count = sum(conv.messages.count() for conv in user.conversations.all())
        data.append({
            'id': str(user.id),
            'username': user.username,
            'nickname': user.nickname,
            'phone': user.phone,
            'avatar_url': user.get_avatar_url(),
            'conv_count': conv_count,
            'msg_count': msg_count,
            'date_joined': user.date_joined.strftime('%Y-%m-%d %H:%M'),
            'last_login': user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else '-'
        })

    StatsCache.set(cache_key, data)
    return JsonResponse({'users': data})


@admin_login_required
@require_http_methods(["GET"])
def admin_wordcloud(request):
    """获取词频统计数据（带缓存，缓存时间较长）"""
    cache_key = 'wordcloud_stats'
    cached_data = StatsCache.get(cache_key, max_age_minutes=60)  # 1小时缓存

    if cached_data:
        return JsonResponse(cached_data)

    # 获取所有用户消息
    user_messages = Message.objects.filter(role='user').values_list('content', flat=True)

    # 加载停用词表
    stopwords = set()
    stopwords_path = os.path.join(settings.BASE_DIR, 'static', 'stopwords.txt')

    try:
        with open(stopwords_path, 'r', encoding='utf-8') as f:
            for line in f:
                word = line.strip()
                if word:
                    stopwords.add(word)
    except FileNotFoundError:
        stopwords = {'的', '了', '是', '我', '你', '他', '她', '它', '我们', '你们', '他们', '这', '那', '有', '在',
                     '不', '也', '都', '说', '就', '要', '会', '可以', '能', '想', '问', '帮', '请', '吧', '吗', '呢',
                     '啊', '哦', '嗯', '哈哈', '谢谢'}

    word_counter = Counter()

    for msg in user_messages:
        words = re.findall(r'[\u4e00-\u9fa5]{2,}', msg)
        for word in words:
            if word not in stopwords and len(word) >= 2:
                word_counter[word] += 1

    filtered_words = {w: c for w, c in word_counter.items() if c >= 2}
    top_words = Counter(filtered_words).most_common(100)
    words_data = [{'name': w, 'value': c} for w, c in top_words]

    result = {
        'success': True,
        'words': words_data,
        'total_words': sum(filtered_words.values())
    }

    StatsCache.set(cache_key, result)
    return JsonResponse(result)


@admin_login_required
@require_http_methods(["GET"])
def admin_token_stats(request):
    """Token使用统计（带缓存）"""
    cache_key = 'token_stats'
    cached_data = StatsCache.get(cache_key, max_age_minutes=30)

    if cached_data:
        return JsonResponse(cached_data)

    messages = Message.objects.all()
    total_chars = sum(len(msg.content) for msg in messages)
    total_tokens = int(total_chars / 1.5)

    daily_stats = []
    for i in range(6, -1, -1):
        date = timezone.now().date() - timedelta(days=i)
        day_msgs = Message.objects.filter(created_at__date=date)
        day_chars = sum(len(msg.content) for msg in day_msgs)
        day_tokens = int(day_chars / 1.5)
        daily_stats.append({
            'date': date.strftime('%m-%d'),
            'messages': day_msgs.count(),
            'tokens': day_tokens
        })

    result = {
        'success': True,
        'total_tokens': total_tokens,
        'total_chars': total_chars,
        'total_messages': messages.count(),
        'daily_stats': daily_stats,
        'avg_per_message': int(total_tokens / messages.count()) if messages.count() > 0 else 0
    }

    StatsCache.set(cache_key, result)
    return JsonResponse(result)


@admin_login_required
@require_http_methods(["POST"])
def admin_refresh_cache(request):
    """手动刷新所有缓存"""
    StatsCache.clear_all()
    return JsonResponse({'success': True, 'message': '缓存已刷新'})