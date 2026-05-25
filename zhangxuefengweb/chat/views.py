from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
from django.contrib.auth.decorators import login_required
import json
import uuid
import os
import base64
import hashlib
import hmac
import time
import threading
import ssl
import struct
from datetime import datetime
from time import mktime
from wsgiref.handlers import format_date_time
from urllib.parse import urlencode
from queue import Queue

import websocket
import requests

from .memorial import get_time_since_passing, get_memorial_stats, add_flower
from .models import Conversation, Message
from .services import GaokaoAssistant, SYSTEM_PROMPT
from .decorators import login_required_json, login_required_view

assistant = GaokaoAssistant()

# ==================== 讯飞TTS配置 ====================
XF_APP_ID = '530466d0'
XF_API_KEY = '3ad6e600d2b9ba02e3778415b5331ad7'
XF_API_SECRET = 'MGIzNmJmMWRlOWM3MThjYzE3NzMyZjk1'


class Ws_Param:
    """讯飞TTS请求参数封装"""

    def __init__(self, appid, apikey, apisecret, text):
        self.APPID = appid
        self.APIKey = apikey
        self.APISecret = apisecret
        self.Text = text

        self.CommonArgs = {"app_id": self.APPID}
        self.BusinessArgs = {"aue": "raw", "auf": "audio/L16;rate=16000", "vcn": "x4_xiaobei", "tte": "utf8"}
        self.Data = {"status": 2, "text": str(base64.b64encode(self.Text.encode('utf-8')), "UTF8")}

    def create_url(self):
        """生成鉴权后的WebSocket URL"""
        url = 'wss://tts-api.xfyun.cn/v2/tts'
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        signature_origin = "host: " + "ws-api.xfyun.cn" + "\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + "/v2/tts " + "HTTP/1.1"
        signature_sha = hmac.new(self.APISecret.encode('utf-8'), signature_origin.encode('utf-8'),
                                 digestmod=hashlib.sha256).digest()
        signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')

        authorization_origin = f'api_key="{self.APIKey}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
        v = {
            "authorization": authorization,
            "date": date,
            "host": "ws-api.xfyun.cn"
        }
        return url + '?' + urlencode(v)


def pcm_to_wav(pcm_data, sample_rate=16000):
    """PCM 转 WAV 字节数据"""
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(pcm_data)

    wav_header = struct.pack('<4sI4s4sIHHIIHH',
                             b'RIFF', 36 + data_size,
                             b'WAVE', b'fmt ',
                             16, 1, num_channels,
                             sample_rate, byte_rate,
                             block_align, bits_per_sample
                             )

    data_chunk = struct.pack('<4sI', b'data', data_size)

    return wav_header + data_chunk + pcm_data


# ==================== TTS 内部函数（供其他视图调用） ====================
def generate_audio_for_text(text):
    """
    内部函数：给定文本，生成音频文件并返回可访问的 URL。
    若失败则返回 None。
    """
    if not text or len(text.strip()) == 0:
        return None

    text = text.strip()
    if len(text) > 500:
        text = text[:500]

    text_md5 = hashlib.md5(text.encode('utf-8')).hexdigest()
    audio_dir = os.path.join(settings.BASE_DIR, 'static', 'audio')
    if not os.path.exists(audio_dir):
        os.makedirs(audio_dir)

    wav_filename = f"{text_md5}.wav"
    wav_filepath = os.path.join(audio_dir, wav_filename)
    wav_url = f"/static/audio/{wav_filename}"

    # 如果缓存存在，直接返回 URL
    if os.path.exists(wav_filepath):
        print(f"[TTS] 命中缓存: {wav_filename}")
        return wav_url

    print(f"[TTS] 开始合成: {text[:50]}...")

    wsParam = Ws_Param(XF_APP_ID, XF_API_KEY, XF_API_SECRET, text)

    audio_queue = Queue()
    error_msg = None

    def on_message(ws, message):
        nonlocal error_msg
        try:
            resp = json.loads(message)
            if resp['code'] != 0:
                error_msg = resp.get('message', '合成失败')
                audio_queue.put(None)
                ws.close()
                return
            audio_b64 = resp['data'].get('audio')
            if audio_b64:
                pcm_chunk = base64.b64decode(audio_b64)
                audio_queue.put(pcm_chunk)
            if resp['data'].get('status') == 2:
                audio_queue.put(None)
                ws.close()
        except Exception as e:
            print(f"解析错误: {e}")
            audio_queue.put(None)
            ws.close()

    def on_error(ws, error):
        print(f"WebSocket错误: {error}")
        audio_queue.put(None)

    def on_close(ws, close_status_code, close_msg):
        print(f"WebSocket关闭: {close_status_code}")

    def on_open(ws):
        d = {
            "common": {"app_id": XF_APP_ID},
            "business": {"aue": "raw", "auf": "audio/L16;rate=16000", "vcn": "x4_xiaobei", "tte": "utf8"},
            "data": {"status": 2, "text": str(base64.b64encode(text.encode('utf-8')), "UTF8")}
        }
        ws.send(json.dumps(d))

    ws = websocket.WebSocketApp(
        wsParam.create_url(),
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    wst = threading.Thread(target=ws.run_forever, kwargs={'sslopt': {'cert_reqs': ssl.CERT_NONE}})
    wst.start()

    all_pcm = b''
    while True:
        chunk = audio_queue.get()
        if chunk is None:
            break
        all_pcm += chunk

    if error_msg or not all_pcm:
        return None

    wav_data = pcm_to_wav(all_pcm, 16000)
    with open(wav_filepath, 'wb') as f:
        f.write(wav_data)

    print(f"[TTS] 文件已保存: {wav_filepath}")
    return wav_url


# ==================== 视图函数 ====================

@login_required_view
def index(request):
    """主页"""
    conversations = Conversation.objects.filter(user=request.user)

    # 获取设备类型：优先从 GET 参数、Cookie 或 User-Agent 判断
    device = request.GET.get('device')
    if not device:
        device = request.COOKIES.get('device')
    if not device:
        ua = request.META.get('HTTP_USER_AGENT', '').lower()
        if 'mobile' in ua or 'android' in ua or 'iphone' in ua:
            device = 'mobile'
        elif 'pad' in ua or 'tablet' in ua:
            device = 'tablet'
        else:
            device = 'desktop'

    template_name = f'index_{device}.html'
    return render(request, template_name, {
        'conversations': conversations
    })


def detect_device(request):
    """检测设备类型并重定向"""
    return render(request, 'detect_device.html')


@csrf_exempt
@require_http_methods(["POST"])
def text_to_speech(request):
    """文字转语音 - 生成完整音频文件后返回URL（兼容公网部署）"""
    try:
        data = json.loads(request.body)
        text = data.get('text', '').strip()

        if not text:
            return JsonResponse({'error': '文字内容不能为空'}, status=400)

        audio_url = generate_audio_for_text(text)
        if audio_url:
            return JsonResponse({'success': True, 'audio_url': audio_url, 'cached': os.path.exists(os.path.join(settings.BASE_DIR, 'static', audio_url[1:]))})
        else:
            return JsonResponse({'error': '语音合成失败'}, status=500)

    except Exception as e:
        print(f"TTS错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def upload_image(request):
    """上传图片并调用OCR接口识别内容"""
    try:
        if 'image' not in request.FILES:
            return JsonResponse({'error': '没有上传图片'}, status=400)

        image = request.FILES['image']

        allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/gif', 'image/webp', 'image/bmp']
        if image.content_type not in allowed_types:
            return JsonResponse({'error': f'不支持的文件类型: {image.content_type}'}, status=400)

        image_data = image.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')

        ext = image.content_type.split('/')[-1]
        if ext == 'jpeg':
            ext = 'jpg'

        api_url = 'https://api.ocr.space/parse/image'

        payload = {
            'apikey': 'K88651827788957',
            'base64Image': f'data:image/{ext};base64,{image_base64}',
            'language': 'chs',
            'isOverlayRequired': False,
            'detectOrientation': True,
            'scale': True
        }

        response = requests.post(api_url, data=payload, timeout=30)
        result = response.json()

        if result.get('OCRExitCode') == 1:
            parsed_text = result.get('ParsedResults', [{}])[0].get('ParsedText', '')
            if parsed_text and parsed_text.strip():
                parsed_text = parsed_text.strip()
                return JsonResponse({
                    'success': True,
                    'text': parsed_text,
                    'preview': f"【OCR识别结果】\n{parsed_text[:200]}{'...' if len(parsed_text) > 200 else ''}"
                })
            else:
                return JsonResponse({'error': '未识别到文字内容，请确保图片中包含清晰的文字'}, status=500)
        else:
            error_msg = result.get('ErrorMessage', ['OCR识别失败'])[0] if result.get('ErrorMessage') else 'OCR识别失败'
            return JsonResponse({'error': f'OCR识别失败: {error_msg}'}, status=500)

    except requests.Timeout:
        return JsonResponse({'error': 'OCR服务响应超时，请稍后重试'}, status=504)
    except Exception as e:
        return JsonResponse({'error': f'处理失败: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def send_message(request):
    """发送消息并获取回复（需要登录）"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': '请先登录'}, status=401)

    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')
        image_text = data.get('image_text', '')

        if not user_message and not image_text:
            return JsonResponse({'error': '消息不能为空'}, status=400)

        if image_text:
            full_message = f"{user_message}\n\n【图片OCR识别内容】\n{image_text}" if user_message else f"【图片OCR识别内容】\n{image_text}"
        else:
            full_message = user_message

        # 处理会话（创建或获取）
        if conversation_id:
            try:
                conversation = Conversation.objects.get(session_id=conversation_id, user=request.user)
                if conversation.messages.count() == 0:
                    title = full_message[:30] + ('...' if len(full_message) > 30 else '')
                    conversation.title = title
                    conversation.save()
            except Conversation.DoesNotExist:
                conversation = Conversation.objects.create(
                    session_id=conversation_id,
                    user=request.user,
                    title=full_message[:30] + ('...' if len(full_message) > 30 else '')
                )
        else:
            session_id = str(uuid.uuid4())
            conversation = Conversation.objects.create(
                session_id=session_id,
                user=request.user,
                title=full_message[:30] + ('...' if len(full_message) > 30 else '')
            )

        # 保存用户消息
        Message.objects.create(
            conversation=conversation,
            role='user',
            content=full_message
        )

        # 构建对话历史
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in conversation.messages.all():
            messages.append({"role": msg.role, "content": msg.content})

        # 获取AI回复
        try:
            ai_response = assistant.chat_with_tools(messages)
        except Exception as e:
            import traceback
            traceback.print_exc()
            ai_response = f"抱歉，AI服务出了点问题：{str(e)}"

        # 保存助手消息（不保存任何音频URL）
        Message.objects.create(
            conversation=conversation,
            role='assistant',
            content=ai_response
        )

        conversation.save()

        # 返回响应（不包含 audio_url）
        return JsonResponse({
            'success': True,
            'conversation_id': conversation.session_id,
            'conversation_title': conversation.title,
            'response': ai_response
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的JSON格式'}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f'服务器错误: {str(e)}'}, status=500)


@require_http_methods(["GET"])
def get_conversations(request):
    """获取当前用户的所有对话会话列表"""
    if not request.user.is_authenticated:
        return JsonResponse({'conversations': []})

    conversations = Conversation.objects.filter(user=request.user)
    data = [
        {
            'id': conv.session_id,
            'title': conv.title,
            'created_at': conv.created_at.strftime('%Y-%m-%d %H:%M'),
            'updated_at': conv.updated_at.strftime('%m-%d %H:%M'),
            'message_count': conv.messages.count()
        }
        for conv in conversations
    ]
    return JsonResponse({'conversations': data})


@require_http_methods(["GET"])
def get_conversation(request, conversation_id):
    """获取指定会话的所有消息"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': '请先登录'}, status=401)

    try:
        conversation = Conversation.objects.get(session_id=conversation_id, user=request.user)
        messages = [
            {
                'role': msg.role,
                'content': msg.content,
                'created_at': msg.created_at.strftime('%H:%M')
            }
            for msg in conversation.messages.all()
        ]
        return JsonResponse({
            'conversation': {
                'id': conversation.session_id,
                'title': conversation.title
            },
            'messages': messages
        })
    except Conversation.DoesNotExist:
        return JsonResponse({'error': '会话不存在'}, status=404)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_conversation(request, conversation_id):
    """删除指定会话"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': '请先登录'}, status=401)

    try:
        conversation = Conversation.objects.get(session_id=conversation_id, user=request.user)
        conversation.delete()
        return JsonResponse({'success': True})
    except Conversation.DoesNotExist:
        return JsonResponse({'error': '会话不存在'}, status=404)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def save_mute_status(request):
    """保存用户的静音偏好"""
    try:
        data = json.loads(request.body)
        is_muted = data.get('is_muted', False)

        user = request.user
        user.audio_muted = is_muted
        user.save()

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def get_mute_status(request):
    """获取用户的静音偏好"""
    try:
        user = request.user
        return JsonResponse({
            'success': True,
            'is_muted': user.audio_muted if hasattr(user, 'audio_muted') else False
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ==================== 活动组件 API ====================

@require_http_methods(["GET"])
def get_activity_data(request, activity_name):
    """获取活动数据 - 通用接口"""
    if activity_name == 'memorial':
        stats = get_memorial_stats()
        time_info = get_time_since_passing()
        return JsonResponse({
            'success': True,
            'total_flowers': stats,
            'time_info': time_info
        })
    else:
        return JsonResponse({'error': '活动不存在'}, status=404)


@require_http_methods(["GET"])
def get_memorial_time(request):
    """获取实时时间（用于每秒更新）"""
    time_info = get_time_since_passing()
    stats = get_memorial_stats()
    return JsonResponse({
        'success': True,
        'time_info': time_info,
        'total_flowers': stats
    })


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def add_memorial_flower(request):
    """献花接口"""
    try:
        user = request.user
        total = add_flower(user.id, user.username)
        return JsonResponse({
            'success': True,
            'total_flowers': total,
            'message': f'感谢 {user.username} 为张老师献花！'
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
