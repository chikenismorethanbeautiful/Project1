# models.py - 完整修复版

import time
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.deconstruct import deconstructible


@deconstructible
class UniqueFilename:
    """生成唯一文件名"""

    def __init__(self, sub_path):
        self.path = sub_path

    def __call__(self, instance, filename):
        # 获取文件扩展名
        ext = filename.split('.')[-1] if '.' in filename else 'jpg'
        # 使用 UUID + 时间戳生成唯一文件名
        new_filename = f"{uuid.uuid4().hex}_{int(time.time())}.{ext}"
        return f"{self.path}/{new_filename}"


class User(AbstractUser):
    """自定义用户模型"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    avatar = models.ImageField(
        upload_to=UniqueFilename('avatars'),
        null=True,
        blank=True,
        verbose_name='头像'
    )
    avatar_url = models.URLField(max_length=500, blank=True, null=True, verbose_name='头像URL')
    nickname = models.CharField(max_length=50, blank=True, null=True, verbose_name='昵称')
    phone = models.CharField(max_length=20, blank=True, null=True, unique=True, verbose_name='手机号')

    # 用户设置
    theme = models.CharField(max_length=20, default='light', verbose_name='主题')
    audio_auto_play = models.BooleanField(default=False, verbose_name='自动播放语音')
    audio_muted = models.BooleanField(default=False, verbose_name='静音状态')  # 新增：静音偏好

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 解决 groups 和 user_permissions 冲突
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to.',
        related_name="chat_user_set",
        related_query_name="chat_user",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name="chat_user_set",
        related_query_name="chat_user",
    )

    class Meta:
        db_table = 'chat_user'
        verbose_name = '用户'
        verbose_name_plural = '用户'

    def get_avatar_url(self):
        """获取头像URL"""
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        if self.avatar_url:
            return self.avatar_url
        return f'https://api.dicebear.com/7.x/avataaars/svg?seed={self.username}'

    def save(self, *args, **kwargs):
        # 如果上传了新头像，删除旧头像文件
        if self.pk:
            try:
                old = User.objects.get(pk=self.pk)
                if old.avatar and old.avatar != self.avatar:
                    old.avatar.delete(save=False)
            except User.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username


class VerificationCode(models.Model):
    """验证码模型"""
    TYPE_REGISTER = 'register'
    TYPE_LOGIN = 'login'
    TYPE_RESET = 'reset'

    TYPE_CHOICES = [
        (TYPE_REGISTER, '注册'),
        (TYPE_LOGIN, '登录'),
        (TYPE_RESET, '重置密码'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=20, verbose_name='手机号')
    code = models.CharField(max_length=6, verbose_name='验证码')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name='类型')
    is_used = models.BooleanField(default=False, verbose_name='是否已使用')
    expires_at = models.DateTimeField(verbose_name='过期时间')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_verification_code'
        verbose_name = '验证码'
        verbose_name_plural = '验证码'
        indexes = [
            models.Index(fields=['phone', 'code']),
            models.Index(fields=['expires_at']),
        ]

    def is_valid(self):
        """检查验证码是否有效"""
        from django.utils import timezone
        return not self.is_used and self.expires_at > timezone.now()

    def __str__(self):
        return f"{self.phone} - {self.code}"


class Conversation(models.Model):
    """对话会话模型"""
    session_id = models.CharField(max_length=100, unique=True, db_index=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='conversations',
        null=True,
        blank=True
    )
    title = models.CharField(max_length=200, default='新对话')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_conversation'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.title} ({self.session_id})"


class Message(models.Model):
    """消息模型"""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=[('user', '用户'), ('assistant', '助手')])
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_message'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"