# auth_views.py - 新建文件
import os

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.core.files.base import ContentFile
from django.conf import settings
import json
import uuid
import random
import re
import base64
from datetime import datetime, timedelta
from PIL import Image
import io

from .models import User, VerificationCode, Conversation
from .decorators import login_required_json


def generate_verification_code():
    """生成6位数字验证码"""
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])


def validate_phone(phone):
    """验证手机号格式"""
    pattern = re.compile(r'^1[3-9]\d{9}$')
    return pattern.match(phone) is not None


@csrf_exempt
@require_http_methods(["POST"])
def send_verification_code(request):
    """
    发送验证码（模拟）
    实际项目中需要接入短信服务商API
    """
    try:
        data = json.loads(request.body)
        phone = data.get('phone', '').strip()
        code_type = data.get('type', 'register')  # register, login, reset

        if not validate_phone(phone):
            return JsonResponse({'error': '请输入正确的手机号格式'}, status=400)

        # 检查是否频繁发送（1分钟内不能重复发送）
        one_minute_ago = timezone.now() - timedelta(minutes=1)
        recent_codes = VerificationCode.objects.filter(
            phone=phone,
            type=code_type,
            created_at__gte=one_minute_ago
        ).count()

        if recent_codes >= 3:
            return JsonResponse({'error': '发送过于频繁，请稍后再试'}, status=429)

        # 生成验证码
        code = generate_verification_code()

        # 删除该手机号该类型的旧验证码
        VerificationCode.objects.filter(
            phone=phone,
            type=code_type,
            is_used=False
        ).delete()

        # 保存验证码（有效期5分钟）
        expires_at = timezone.now() + timedelta(minutes=5)
        VerificationCode.objects.create(
            phone=phone,
            code=code,
            type=code_type,
            expires_at=expires_at
        )

        # 模拟发送验证码（实际开发中，这里应该调用短信API）
        print(f"【验证码】{phone} 的验证码是: {code}，有效期5分钟")

        # 返回成功（生产环境不要返回验证码）
        return JsonResponse({
            'success': True,
            'message': '验证码已发送，请注意查收',
            'debug_code': code if settings.DEBUG else None  # 开发环境返回验证码方便测试
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的JSON格式'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'发送失败: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def register(request):
    """用户注册"""
    try:
        data = json.loads(request.body)
        phone = data.get('phone', '').strip()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        code = data.get('code', '').strip()

        # 验证必填字段
        if not all([phone, username, password, confirm_password, code]):
            return JsonResponse({'error': '请填写所有必填字段'}, status=400)

        # 验证手机号格式
        if not validate_phone(phone):
            return JsonResponse({'error': '请输入正确的手机号格式'}, status=400)

        # 验证用户名
        if len(username) < 2 or len(username) > 20:
            return JsonResponse({'error': '用户名长度应为2-20个字符'}, status=400)

        if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fa5]+$', username):
            return JsonResponse({'error': '用户名只能包含字母、数字、下划线和中文字符'}, status=400)

        # 验证密码
        if len(password) < 6:
            return JsonResponse({'error': '密码长度不能少于6位'}, status=400)

        if password != confirm_password:
            return JsonResponse({'error': '两次输入的密码不一致'}, status=400)

        # 检查手机号是否已注册
        if User.objects.filter(phone=phone).exists():
            return JsonResponse({'error': '该手机号已注册'}, status=400)

        # 检查用户名是否已存在
        if User.objects.filter(username=username).exists():
            return JsonResponse({'error': '用户名已存在'}, status=400)

        # 验证验证码
        try:
            verify_code = VerificationCode.objects.filter(
                phone=phone,
                code=code,
                type='register',
                is_used=False
            ).latest('created_at')

            if not verify_code.is_valid():
                return JsonResponse({'error': '验证码已过期'}, status=400)

            verify_code.is_used = True
            verify_code.save()

        except VerificationCode.DoesNotExist:
            return JsonResponse({'error': '验证码无效'}, status=400)

        # 创建用户
        user = User.objects.create(
            phone=phone,
            username=username,
            nickname=username,
            password=make_password(password)
        )

        # 自动登录
        login(request, user)

        # 更新session过期时间（默认2周）
        request.session.set_expiry(1209600)

        return JsonResponse({
            'success': True,
            'message': '注册成功',
            'user': {
                'id': str(user.id),
                'username': user.username,
                'nickname': user.nickname,
                'phone': user.phone,
                'avatar_url': user.get_avatar_url()
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的JSON格式'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'注册失败: {str(e)}'}, status=500)


# auth_views.py - 修改 user_login 函数

@csrf_exempt
@require_http_methods(["POST"])
def user_login(request):
    """用户登录"""
    try:
        data = json.loads(request.body)
        account = data.get('phone', '').strip()  # 改为 account
        password = data.get('password', '')

        if not account or not password:
            return JsonResponse({'error': '请填写账号和密码'}, status=400)

        # 先尝试用手机号查找
        user = None
        try:
            user = User.objects.get(phone=account)
        except User.DoesNotExist:
            pass

        # 如果手机号找不到，尝试用用户名查找
        if not user:
            try:
                user = User.objects.get(username=account)
            except User.DoesNotExist:
                pass

        if not user:
            return JsonResponse({'error': '账号或密码错误'}, status=401)

        # 验证密码
        from django.contrib.auth.hashers import check_password
        if not check_password(password, user.password):
            return JsonResponse({'error': '账号或密码错误'}, status=401)

        # 登录
        login(request, user)
        request.session.set_expiry(1209600)

        return JsonResponse({
            'success': True,
            'message': '登录成功',
            'user': {
                'id': str(user.id),
                'username': user.username,
                'nickname': user.nickname,
                'phone': user.phone,
                'avatar_url': user.get_avatar_url()
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的JSON格式'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'登录失败: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def sms_login(request):
    """短信验证码登录"""
    try:
        data = json.loads(request.body)
        phone = data.get('phone', '').strip()
        code = data.get('code', '').strip()

        if not validate_phone(phone):
            return JsonResponse({'error': '请输入正确的手机号格式'}, status=400)

        if not code:
            return JsonResponse({'error': '请输入验证码'}, status=400)

        # 验证验证码
        try:
            verify_code = VerificationCode.objects.filter(
                phone=phone,
                code=code,
                type='login',
                is_used=False
            ).latest('created_at')

            if not verify_code.is_valid():
                return JsonResponse({'error': '验证码已过期'}, status=400)

            verify_code.is_used = True
            verify_code.save()

        except VerificationCode.DoesNotExist:
            return JsonResponse({'error': '验证码无效'}, status=400)

        # 获取或创建用户
        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={
                'username': f'user_{phone[-6:]}',
                'nickname': f'用户{phone[-4:]}',
                'password': make_password(None)
            }
        )

        if created:
            # 确保用户名唯一
            while User.objects.filter(username=user.username).count() > 1:
                user.username = f'user_{phone[-6:]}_{uuid.uuid4().hex[:4]}'
            user.save()

        # 登录
        login(request, user)

        # 更新session过期时间
        request.session.set_expiry(1209600)

        return JsonResponse({
            'success': True,
            'message': '登录成功' if not created else '注册并登录成功',
            'user': {
                'id': str(user.id),
                'username': user.username,
                'nickname': user.nickname,
                'phone': user.phone,
                'avatar_url': user.get_avatar_url()
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的JSON格式'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'登录失败: {str(e)}'}, status=500)


@require_http_methods(["GET"])
def check_login_status(request):
    """检查登录状态"""
    if request.user.is_authenticated:
        return JsonResponse({
            'is_authenticated': True,
            'user': {
                'id': str(request.user.id),
                'username': request.user.username,
                'nickname': request.user.nickname,
                'phone': request.user.phone,
                'avatar_url': request.user.get_avatar_url()
            }
        })
    else:
        return JsonResponse({
            'is_authenticated': False,
            'user': None
        })


@require_http_methods(["POST", "GET"])
def user_logout(request):
    """用户登出"""
    # 清除 session
    logout(request)
    # 清除所有 session 数据
    request.session.flush()

    # 判断是否是 API 请求
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'redirect': '/auth/'})

    # 普通请求重定向到登录页
    from django.shortcuts import redirect
    return redirect('/')


@login_required_json
@csrf_exempt
@require_http_methods(["GET", "POST"])
def user_profile(request):
    """获取/更新用户资料"""
    if request.method == "GET":
        return JsonResponse({
            'success': True,
            'user': {
                'id': str(request.user.id),
                'username': request.user.username,
                'nickname': request.user.nickname,
                'phone': request.user.phone,
                'email': request.user.email,
                'avatar_url': request.user.get_avatar_url(),
                'theme': request.user.theme,
                'audio_auto_play': request.user.audio_auto_play,
                'date_joined': request.user.date_joined.strftime('%Y-%m-%d %H:%M')
            }
        })

    # POST - 更新资料
    try:
        data = json.loads(request.body)

        if 'nickname' in data:
            nickname = data['nickname'].strip()
            if nickname and len(nickname) <= 50:
                request.user.nickname = nickname
                if not request.user.username.startswith('user_'):
                    # 如果用户手动设置了昵称，不同步修改username
                    pass

        if 'theme' in data and data['theme'] in ['light', 'dark', 'auto']:
            request.user.theme = data['theme']

        if 'audio_auto_play' in data:
            request.user.audio_auto_play = bool(data['audio_auto_play'])

        request.user.save()

        return JsonResponse({
            'success': True,
            'message': '资料更新成功',
            'user': {
                'id': str(request.user.id),
                'username': request.user.username,
                'nickname': request.user.nickname,
                'phone': request.user.phone,
                'avatar_url': request.user.get_avatar_url(),
                'theme': request.user.theme,
                'audio_auto_play': request.user.audio_auto_play
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的JSON格式'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'更新失败: {str(e)}'}, status=500)


@login_required_json
@csrf_exempt
@require_http_methods(["POST"])
def upload_avatar(request):
    """上传用户头像"""
    try:
        if 'avatar' not in request.FILES:
            return JsonResponse({'error': '请上传头像文件'}, status=400)

        avatar_file = request.FILES['avatar']

        # 检查文件类型
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
        if avatar_file.content_type not in allowed_types:
            return JsonResponse({'error': '不支持的文件类型，请上传JPG、PNG、GIF或WEBP格式'}, status=400)

        # 检查文件大小（限制2MB）
        if avatar_file.size > 2 * 1024 * 1024:
            return JsonResponse({'error': '头像文件不能超过2MB'}, status=400)

        # 删除旧头像
        if request.user.avatar:
            old_avatar_path = request.user.avatar.path
            if os.path.exists(old_avatar_path):
                os.remove(old_avatar_path)

        # 保存新头像
        request.user.avatar = avatar_file
        request.user.save()

        return JsonResponse({
            'success': True,
            'message': '头像上传成功',
            'avatar_url': request.user.get_avatar_url()
        })

    except Exception as e:
        return JsonResponse({'error': f'上传失败: {str(e)}'}, status=500)


@login_required_json
@require_http_methods(["POST"])
def change_password(request):
    """修改密码"""
    try:
        data = json.loads(request.body)
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')
        confirm_password = data.get('confirm_password', '')

        # 验证旧密码
        from django.contrib.auth.hashers import check_password
        if not check_password(old_password, request.user.password):
            return JsonResponse({'error': '原密码错误'}, status=401)

        # 验证新密码
        if len(new_password) < 6:
            return JsonResponse({'error': '新密码长度不能少于6位'}, status=400)

        if new_password != confirm_password:
            return JsonResponse({'error': '两次输入的新密码不一致'}, status=400)

        # 修改密码
        request.user.set_password(new_password)
        request.user.save()

        # 重新登录（密码修改后需要重新登录）
        from django.contrib.auth import login, update_session_auth_hash
        update_session_auth_hash(request, request.user)

        return JsonResponse({
            'success': True,
            'message': '密码修改成功'
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的JSON格式'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'修改失败: {str(e)}'}, status=500)