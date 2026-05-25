# urls.py - 添加管理员路由

from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views
from . import auth_views
from . import admin_views
from .views import save_mute_status, get_mute_status

app_name = 'chat'

urlpatterns = [
    # 认证相关
    path('auth/', include([
        path('', auth_views.check_login_status, name='auth_check'),
        path('register/', auth_views.register, name='register'),
        path('login/', auth_views.user_login, name='login'),
        path('sms-login/', auth_views.sms_login, name='sms_login'),
        path('logout/', auth_views.user_logout, name='logout'),
        path('check/', auth_views.check_login_status, name='check_login'),
        path('send-code/', auth_views.send_verification_code, name='send_code'),
        path('profile/', auth_views.user_profile, name='profile'),
        path('upload-avatar/', auth_views.upload_avatar, name='upload_avatar'),
        path('change-password/', auth_views.change_password, name='change_password'),
    ])),

    # 管理员后台
    path('zxfadmin/', include([
        path('', admin_views.admin_dashboard, name='admin_dashboard'),
        path('stats/', admin_views.admin_stats, name='admin_stats'),
        path('users/', admin_views.admin_users, name='admin_users'),
        path('users/<uuid:user_id>/delete/', admin_views.admin_delete_user, name='admin_delete_user'),
        path('conversations/', admin_views.admin_conversations, name='admin_conversations'),
        path('conversations/<str:conv_id>/delete/', admin_views.admin_delete_conversation,
             name='admin_delete_conversation'),
        path('messages/', admin_views.admin_messages, name='admin_messages'),

        path('wordcloud/', admin_views.admin_wordcloud, name='admin_wordcloud'),
        path('logs/', admin_views.admin_logs, name='admin_logs'),
        path('token-stats/', admin_views.admin_token_stats, name='admin_token_stats'),
        path('refresh-cache/', admin_views.admin_refresh_cache, name='admin_refresh_cache'),
    ])),

    # 主应用
    path('', views.index, name='index'),
    path('api/send/', views.send_message, name='send_message'),
    path('api/upload/', views.upload_image, name='upload_image'),
    path('api/tts/', views.text_to_speech, name='text_to_speech'),
    path('api/conversations/', views.get_conversations, name='get_conversations'),
    path('api/conversations/<str:conversation_id>/', views.get_conversation, name='get_conversation'),
    path('api/conversations/<str:conversation_id>/delete/', views.delete_conversation, name='delete_conversation'),
    path('api/save-mute-status/', save_mute_status, name='save_mute_status'),
    path('api/get-mute-status/', get_mute_status, name='get_mute_status'),
    path('detect-device/', views.detect_device, name='detect_device'),
    path('api/activity/<str:activity_name>/data/', views.get_activity_data, name='activity_data'),
    path('api/activity/memorial/time/', views.get_memorial_time, name='memorial_time'),
    path('api/activity/memorial/flower/', views.add_memorial_flower, name='memorial_flower'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)