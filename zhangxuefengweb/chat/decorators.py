# decorators.py - 在 chat 目录下新建此文件

from django.http import JsonResponse
from django.shortcuts import render
from functools import wraps


def login_required_json(view_func):
    """要求登录的装饰器，返回JSON格式错误"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({
                'error': '请先登录',
                'redirect': '/auth/'
            }, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


def login_required_view(view_func):
    """要求登录的视图装饰器，返回页面"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return render(request, 'auth/auth.html')
        return view_func(request, *args, **kwargs)
    return wrapper