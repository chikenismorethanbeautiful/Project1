/**
 * 高考志愿AI助手 - 最终版
 * 移动端代码块滚动 + 完整高亮（所有文字均可见）
 * 修正：代码块不换行，严格横向滚动
 */
class ChatApp {
    constructor() {
        this.currentConversationId = null;
        this.isLoading = false;
        this.uploadedImageText = '';
        this.uploadedImagePreviewUrl = '';
        this.uploadedImageFile = null;
        this.currentAudio = null;
        this.currentSourceNode = null;
        this.audioContext = null;
        this.gainNode = null;
        this.isMuted = false;
        this.isSending = false;
        this.isUploadingImage = false;
        this.fileInput = null;
        this.isProcessingFile = false;
        this.currentMemorialAudio = null;
        this.isPlaying = false;
        this.audioCache = new Map();

        const savedMute = localStorage.getItem('audioMuted');
        if (savedMute !== null) {
            this.isMuted = savedMute === 'true';
        }

        this.messagesContainer = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');

        this.init();
    }

    init() {
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                highlight: function(code, lang) {
                    if (lang && hljs.getLanguage(lang)) {
                        return hljs.highlight(code, { language: lang }).value;
                    }
                    return hljs.highlightAuto(code).value;
                },
                breaks: true,
                gfm: true
            });
        }

        this.bindEvents();
        this.loadConversationList();
        this.initMuteButton();
        this.createFileInput();
        setTimeout(() => {
            this.updateUserAvatars();
            this.addVoiceButtonsToExistingBotMessages();
            this.applyHighlightToAllCodeBlocks();
        }, 100);
    }

    applyHighlightToAllCodeBlocks() {
        if (typeof hljs === 'undefined') return;
        document.querySelectorAll('.bubble pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
    }

    addVoiceButtonsToExistingBotMessages() {
        const existingBotMessages = document.querySelectorAll('.message.bot');
        existingBotMessages.forEach(msgDiv => {
            if (msgDiv.querySelector('.audio-controls')) return;
            const bubble = msgDiv.querySelector('.bubble');
            if (!bubble) return;
            const textElem = bubble.querySelector('strong, span, div') || bubble;
            let rawText = textElem.innerText || textElem.textContent || '';
            const audioControls = document.createElement('div');
            audioControls.className = 'audio-controls';
            audioControls.style.cssText = 'margin-top: 12px; display: flex; gap: 10px; align-items: center; padding-top: 8px; border-top: 1px solid #eef2f8;';
            audioControls.innerHTML = `
                <button class="play-audio-btn" data-text="${this.escapeHtml(rawText)}" style="background: none; border: none; cursor: pointer; font-size: 14px; color: #667eea; display: flex; align-items: center; gap: 6px; padding: 4px 8px; border-radius: 20px; transition: all 0.2s;">
                    🔊 播放语音
                </button>
                <span class="audio-status" style="font-size: 11px; color: #999;"></span>
            `;
            bubble.appendChild(audioControls);
            const playBtn = audioControls.querySelector('.play-audio-btn');
            if (playBtn) {
                playBtn.originalTextContent = rawText;
                playBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.handlePlayAudio(playBtn, playBtn.originalTextContent);
                });
            }
        });
    }

    getUserAvatarUrl() {
        if (window.currentUser && window.currentUser.avatar_url) {
            return window.currentUser.avatar_url;
        }
        return null;
    }

    updateUserAvatars() {
        const avatarUrl = this.getUserAvatarUrl();
        const userAvatars = document.querySelectorAll('.message.user .avatar');
        userAvatars.forEach(avatar => {
            avatar.innerHTML = '';
            if (avatarUrl) {
                const img = document.createElement('img');
                img.src = avatarUrl;
                img.style.width = '100%';
                img.style.height = '100%';
                img.style.objectFit = 'cover';
                img.style.borderRadius = '50%';
                img.onerror = () => {
                    avatar.innerHTML = '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;">👤</div>';
                };
                avatar.appendChild(img);
            } else {
                const div = document.createElement('div');
                div.style.cssText = 'width:100%;height:100%;display:flex;align-items:center;justify-content:center;';
                div.textContent = '👤';
                avatar.appendChild(div);
            }
        });
    }

    createFileInput() {
        this.fileInput = document.createElement('input');
        this.fileInput.type = 'file';
        this.fileInput.accept = 'image/jpeg,image/png,image/jpg,image/gif,image/webp';
        this.fileInput.style.display = 'none';
        this.fileInput.onchange = (e) => this.handleFileSelect(e);
        document.body.appendChild(this.fileInput);
    }

    async handleFileSelect(e) {
        if (this.isProcessingFile) return;
        const file = e.target.files[0];
        if (!file) return;
        if (this.uploadedImageText) {
            this.showToast('请先发送当前图片或点击移除按钮');
            this.fileInput.value = '';
            return;
        }
        if (this.isUploadingImage) {
            this.showToast('正在上传中，请稍候...');
            this.fileInput.value = '';
            return;
        }
        this.isProcessingFile = true;
        this.isUploadingImage = true;

        const uploadBtn = document.getElementById('uploadImageBtn');
        if (uploadBtn) {
            uploadBtn.disabled = true;
            uploadBtn.style.opacity = '0.5';
            uploadBtn.innerHTML = '⏳ 识别中...';
        }
        const textPreviewDiv = document.getElementById('imageTextPreview');
        if (textPreviewDiv) {
            textPreviewDiv.innerHTML = '<span style="color: #888;">⏳ OCR识别中，请稍候...</span>';
        }

        const result = await this.uploadAndRecognizeImage(file);
        if (result) {
            this.showImagePreviewAndResult(file, result.text);
        } else {
            if (textPreviewDiv) textPreviewDiv.innerHTML = '';
        }
        if (uploadBtn) {
            uploadBtn.disabled = false;
            uploadBtn.style.opacity = '1';
            uploadBtn.innerHTML = '📷 上传图片识别';
        }
        this.isUploadingImage = false;
        setTimeout(() => {
            this.fileInput.value = '';
            this.isProcessingFile = false;
        }, 100);
    }

    initMuteButton() {
        const muteBtn = document.getElementById('muteBtn');
        if (muteBtn) {
            this.updateMuteButtonUI(muteBtn);
            muteBtn.addEventListener('click', () => this.toggleMute());
        }
    }

    toggleMute() {
        this.isMuted = !this.isMuted;
        localStorage.setItem('audioMuted', this.isMuted);
        const muteBtn = document.getElementById('muteBtn');
        if (muteBtn) this.updateMuteButtonUI(muteBtn);
        if (this.currentAudio) this.currentAudio.muted = this.isMuted;
        if (this.gainNode) this.gainNode.gain.value = this.isMuted ? 0 : 1;
        if (this.currentMemorialAudio) this.currentMemorialAudio.muted = this.isMuted;
        this.showToast(`🔇 ${this.isMuted ? '已静音' : '已取消静音'}`);
    }

    updateMuteButtonUI(btn) {
        if (this.isMuted) {
            btn.innerHTML = '🔇 静音中';
            btn.style.background = '#ef4444';
            btn.style.color = 'white';
        } else {
            btn.innerHTML = '🔊 声音开启';
            btn.style.background = 'rgba(255,255,255,0.15)';
            btn.style.color = 'white';
        }
    }

    stopAllAudio() {
        if (this.currentAudio) {
            try {
                this.currentAudio.pause();
                this.currentAudio.currentTime = 0;
                this.currentAudio.onended = null;
                this.currentAudio = null;
            } catch (e) {}
        }
        if (this.currentMemorialAudio) {
            try {
                this.currentMemorialAudio.pause();
                this.currentMemorialAudio.currentTime = 0;
                this.currentMemorialAudio = null;
            } catch (e) {}
        }
        if (this.currentSourceNode) {
            try {
                this.currentSourceNode.stop();
                this.currentSourceNode.disconnect();
                this.currentSourceNode = null;
            } catch (e) {}
        }
        if (this.audioContext) {
            try {
                this.audioContext.close();
            } catch (e) {}
            this.audioContext = null;
        }
        this.gainNode = null;
        this.isPlaying = false;

        document.querySelectorAll('.play-audio-btn').forEach(btn => {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.innerHTML = '🔊 播放语音';
            const statusSpan = btn.parentElement?.querySelector('.audio-status');
            if (statusSpan) statusSpan.textContent = '';
        });
    }

    bindEvents() {
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        document.getElementById('newChatBtn')?.addEventListener('click', () => this.createNewChat());
        document.getElementById('menuToggle')?.addEventListener('click', () => this.toggleSidebar());

        const quickRepliesContainer = document.getElementById('quickReplies');
        if (quickRepliesContainer) {
            quickRepliesContainer.removeEventListener('click', this.quickReplyHandler);
            this.quickReplyHandler = (e) => {
                const chip = e.target.closest('.quick-reply-chip');
                if (chip) {
                    e.stopPropagation();
                    e.preventDefault();
                    const msg = chip.dataset.msg;
                    if (msg) {
                        this.messageInput.value = '';
                        this.messageInput.value = msg;
                        setTimeout(() => this.sendMessage(), 50);
                    }
                }
            };
            quickRepliesContainer.addEventListener('click', this.quickReplyHandler);
        }

        const actionToolbar = document.querySelector('.action-toolbar');
        if (actionToolbar) {
            actionToolbar.removeEventListener('click', this.funcBtnHandler);
            this.funcBtnHandler = (e) => {
                const btn = e.target.closest('.func-btn');
                if (btn) {
                    e.stopPropagation();
                    e.preventDefault();
                    const query = btn.dataset.query;
                    if (query) {
                        this.messageInput.value = '';
                        this.messageInput.value = query;
                        setTimeout(() => this.sendMessage(), 50);
                    }
                }
            };
            actionToolbar.addEventListener('click', this.funcBtnHandler);
        }
        this.setupImageUpload();
    }

    getCSRFToken() {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, 10) === 'csrftoken=') {
                    cookieValue = decodeURIComponent(cookie.substring(10));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // 关键：不添加任何导致换行的内联样式
    renderMarkdown(content) {
        if (typeof marked !== 'undefined') {
            try {
                let html = marked.parse(content);
                // 不再添加任何内联样式，完全依赖CSS控制滚动和不换行
                // 只做表格的简单包装（为了横向滚动，但CSS已经处理了table的display:block，这里不需要额外操作）
                // 如果marked生成的表格没有外部包裹，保持原样即可，因为CSS已经对.bubble table设置了滚动
                return html;
            } catch(e) {
                console.error('Markdown解析失败:', e);
                return content.replace(/\n/g, '<br>');
            }
        }
        return content.replace(/\n/g, '<br>');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    addMessage(role, content, time = null, audioUrl = null) {
        const normalizedRole = (role === 'assistant') ? 'bot' : role;
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${normalizedRole}`;
        const timeStr = time || new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

        const rawText = content;
        let formattedContent;
        if (normalizedRole === 'bot') {
            formattedContent = this.renderMarkdown(content);
        } else {
            formattedContent = content.replace(/\n/g, '<br>');
        }

        let avatarHtml;
        if (normalizedRole === 'user') {
            const avatarUrl = this.getUserAvatarUrl();
            if (avatarUrl) {
                avatarHtml = `<div class="avatar"><img src="${avatarUrl}" alt="用户头像" style="width:100%;height:100%;object-fit:cover;border-radius:50%;" onerror="this.onerror=null;this.parentElement.innerHTML='<div style=\'width:100%;height:100%;display:flex;align-items:center;justify-content:center;\'>👤</div>'"></div>`;
            } else {
                avatarHtml = '<div class="avatar"><div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;">👤</div></div>';
            }
        } else {
            avatarHtml = '<div class="avatar"><img src="/static/images/zhangxuefeng.png" alt="张雪峰" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display=\'none\';this.parentElement.innerHTML=\'🤖\'"></div>';
        }

        let bubbleContent = formattedContent;
        if (normalizedRole === 'bot') {
            bubbleContent = `
                <div class="bot-message-content">
                    ${formattedContent}
                </div>
                <div class="audio-controls" style="margin-top: 12px; display: flex; gap: 10px; align-items: center; padding-top: 8px; border-top: 1px solid #eef2f8;">
                    <button class="play-audio-btn" data-text="${this.escapeHtml(rawText)}" style="background: none; border: none; cursor: pointer; font-size: 14px; color: #667eea; display: flex; align-items: center; gap: 6px; padding: 4px 8px; border-radius: 20px; transition: all 0.2s;">
                        🔊 播放语音
                    </button>
                    <span class="audio-status" style="font-size: 11px; color: #999;"></span>
                </div>
            `;
        }

        messageDiv.innerHTML = `${avatarHtml}<div class="bubble" ${normalizedRole === 'bot' ? 'style="position:relative;"' : ''}>${bubbleContent}</div>`;

        if (normalizedRole === 'bot') {
            const bubble = messageDiv.querySelector('.bubble');
            bubble.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                this.showContextMenu(e, rawText);
            });

            const playBtn = messageDiv.querySelector('.play-audio-btn');
            if (playBtn) {
                playBtn.originalTextContent = rawText;
                playBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.handlePlayAudio(playBtn, playBtn.originalTextContent);
                });
            }
        }

        this.messagesContainer.appendChild(messageDiv);

        const timestampDiv = document.createElement('div');
        timestampDiv.className = 'timestamp';
        if (normalizedRole === 'user') timestampDiv.style.textAlign = 'right';
        timestampDiv.innerText = timeStr;
        this.messagesContainer.appendChild(timestampDiv);

        if (typeof hljs !== 'undefined') {
            messageDiv.querySelectorAll('pre code').forEach((block) => {
                hljs.highlightElement(block);
            });
        }

        this.scrollToBottom();
        return messageDiv;
    }

    addCustomMessage(role, htmlContent, time = null) {
        const normalizedRole = (role === 'assistant') ? 'bot' : role;
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${normalizedRole}`;
        const timeStr = time || new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

        let avatarHtml;
        if (normalizedRole === 'user') {
            const avatarUrl = this.getUserAvatarUrl();
            if (avatarUrl) {
                avatarHtml = `<div class="avatar"><img src="${avatarUrl}" alt="用户头像" style="width:100%;height:100%;object-fit:cover;border-radius:50%;" onerror="this.onerror=null;this.parentElement.innerHTML='<div style=\'width:100%;height:100%;display:flex;align-items:center;justify-content:center;\'>👤</div>'"></div>`;
            } else {
                avatarHtml = '<div class="avatar"><div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;">👤</div></div>';
            }
        } else {
            avatarHtml = '<div class="avatar"><img src="/static/images/zhangxuefeng.png" alt="张雪峰" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display=\'none\';this.parentElement.innerHTML=\'🤖\'"></div>';
        }

        messageDiv.innerHTML = `${avatarHtml}<div class="bubble" style="position:relative;">${htmlContent}</div>`;
        this.messagesContainer.appendChild(messageDiv);

        const timestampDiv = document.createElement('div');
        timestampDiv.className = 'timestamp';
        if (normalizedRole === 'user') timestampDiv.style.textAlign = 'right';
        timestampDiv.innerText = timeStr;
        this.messagesContainer.appendChild(timestampDiv);

        this.scrollToBottom();
        return messageDiv;
    }

    async handlePlayAudio(button, text) {
        this.stopAllAudio();
        const cacheKey = text;
        if (this.audioCache.has(cacheKey)) {
            const cachedUrl = this.audioCache.get(cacheKey);
            this.playAudioFromUrl(button, cachedUrl);
            return;
        }
        await this.playAudio(text, button);
    }

    playAudioFromUrl(button, audioUrl) {
        this.stopAllAudio();
        const statusSpan = button.parentElement?.querySelector('.audio-status');
        const originalText = button.innerHTML;
        button.disabled = true;
        button.style.opacity = '0.6';
        if (statusSpan) {
            statusSpan.textContent = '🔊 播放中...';
            statusSpan.style.color = '#10b981';
        }
        button.innerHTML = '⏸️ 播放中...';
        this.currentAudio = new Audio(audioUrl);
        this.currentAudio.muted = this.isMuted;
        this.currentAudio.onended = () => {
            if (statusSpan) statusSpan.textContent = '';
            button.disabled = false;
            button.style.opacity = '1';
            button.innerHTML = originalText;
            this.currentAudio = null;
            this.isPlaying = false;
        };
        this.currentAudio.onerror = () => {
            if (statusSpan) {
                statusSpan.textContent = '❌ 播放失败';
                statusSpan.style.color = '#ef4444';
            }
            button.disabled = false;
            button.style.opacity = '1';
            button.innerHTML = originalText;
            setTimeout(() => {
                if (statusSpan) statusSpan.textContent = '';
            }, 2000);
            this.currentAudio = null;
            this.isPlaying = false;
        };
        this.currentAudio.play().catch(err => {
            console.error('播放失败', err);
            if (statusSpan) statusSpan.textContent = '❌ 播放失败';
            button.disabled = false;
            button.style.opacity = '1';
            button.innerHTML = originalText;
            this.isPlaying = false;
        });
        this.isPlaying = true;
    }

    showContextMenu(event, text) {
        const existingMenu = document.getElementById('contextMenu');
        if (existingMenu) existingMenu.remove();
        const menu = document.createElement('div');
        menu.id = 'contextMenu';
        menu.style.cssText = `
            position: fixed;
            left: ${event.pageX}px;
            top: ${event.pageY}px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            z-index: 10000;
            overflow: hidden;
            min-width: 150px;
            animation: menuFadeIn 0.15s ease;
        `;
        if (!document.getElementById('menuStyle')) {
            const style = document.createElement('style');
            style.id = 'menuStyle';
            style.textContent = `
                @keyframes menuFadeIn {
                    from { opacity: 0; transform: scale(0.95); }
                    to { opacity: 1; transform: scale(1); }
                }
            `;
            document.head.appendChild(style);
        }
        const copyItem = document.createElement('div');
        copyItem.textContent = '📋 复制文字';
        copyItem.style.cssText = 'padding: 12px 18px; cursor: pointer; transition: background 0.2s; font-size: 14px;';
        copyItem.onmouseenter = () => copyItem.style.background = '#f5f5f5';
        copyItem.onmouseleave = () => copyItem.style.background = 'white';
        copyItem.onclick = () => {
            navigator.clipboard.writeText(text);
            this.showToast('✅ 已复制到剪贴板');
            menu.remove();
        };
        const selectItem = document.createElement('div');
        selectItem.textContent = '🔍 全选文字';
        selectItem.style.cssText = 'padding: 12px 18px; cursor: pointer; transition: background 0.2s; font-size: 14px; border-top: 1px solid #eee;';
        selectItem.onmouseenter = () => selectItem.style.background = '#f5f5f5';
        selectItem.onmouseleave = () => selectItem.style.background = 'white';
        selectItem.onclick = () => {
            const temp = document.createElement('textarea');
            temp.value = text;
            document.body.appendChild(temp);
            temp.select();
            document.execCommand('copy');
            document.body.removeChild(temp);
            this.showToast('✅ 已选中并复制');
            menu.remove();
        };
        menu.appendChild(copyItem);
        menu.appendChild(selectItem);
        document.body.appendChild(menu);
        const closeMenu = (e) => {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        };
        setTimeout(() => document.addEventListener('click', closeMenu), 0);
    }

    showToast(message) {
        const toast = document.createElement('div');
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            bottom: 100px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.8);
            color: white;
            padding: 8px 20px;
            border-radius: 40px;
            font-size: 14px;
            z-index: 10001;
            animation: fadeInOut 1.5s ease;
            pointer-events: none;
        `;
        if (!document.getElementById('toastStyle')) {
            const style = document.createElement('style');
            style.id = 'toastStyle';
            style.textContent = `
                @keyframes fadeInOut {
                    0% { opacity: 0; transform: translateX(-50%) translateY(20px); }
                    15% { opacity: 1; transform: translateX(-50%) translateY(0); }
                    85% { opacity: 1; transform: translateX(-50%) translateY(0); }
                    100% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
                }
            `;
            document.head.appendChild(style);
        }
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 1500);
        return toast;
    }

    async playAudio(text, button) {
        const statusSpan = button.parentElement.querySelector('.audio-status');
        const originalText = button.innerHTML;
        button.disabled = true;
        button.style.opacity = '0.6';
        if (statusSpan) {
            statusSpan.textContent = '⏳ 合成中...';
            statusSpan.style.color = '#f59e0b';
        }
        button.innerHTML = '⏸️ 加载中...';
        try {
            const response = await fetch('/api/tts/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({ text: text.substring(0, 500) })
            });
            const data = await response.json();
            if (data.success && data.audio_url) {
                this.audioCache.set(text, data.audio_url);
                this.playAudioFromUrl(button, data.audio_url);
                return;
            }
            throw new Error('TTS 返回失败');
        } catch (error) {
            console.error('合成错误:', error);
            if (statusSpan) {
                statusSpan.textContent = '❌ 合成失败';
                statusSpan.style.color = '#ef4444';
            }
            button.disabled = false;
            button.style.opacity = '1';
            button.innerHTML = originalText;
            setTimeout(() => {
                if (statusSpan) statusSpan.textContent = '';
            }, 2000);
            this.isPlaying = false;
        }
    }

    showTyping() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message bot';
        typingDiv.id = 'typingIndicator';
        typingDiv.innerHTML = '<div class="avatar"><img src="/static/images/zhangxuefeng.png" alt="张雪峰" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display=\'none\';this.parentElement.innerHTML=\'🤖\'"></div><div class="typing-indicator"><span></span><span></span><span></span></div>';
        this.messagesContainer.appendChild(typingDiv);
        this.scrollToBottom();
    }

    hideTyping() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) indicator.remove();
    }

    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    // ==================== 哀悼活动 ====================
    isMemorialMessage(message) {
        const keywords = ['张雪峰老师，一路走好', '为张老师哀悼', '张老师走好', '缅怀张雪峰'];
        return keywords.some(kw => message.includes(kw));
    }

    async handleMemorialMessage() {
        this.playMemorialAudio();
        const memorialData = await this.getMemorialData();
        this.displayMemorialMessage(memorialData);
    }

    async playMemorialAudio() {
        if (this.isMuted) return;
        this.stopAllAudio();
        const audio = new Audio('/static/activities/丧葬.mp3');
        audio.loop = true;
        audio.volume = 0.5;
        try {
            await audio.play();
            this.currentMemorialAudio = audio;
        } catch (e) {
            console.log('自动播放被阻止:', e);
            this.showToast('🎵 点击页面任意位置播放哀悼音乐');
            const playOnClick = async () => {
                try {
                    await audio.play();
                    this.currentMemorialAudio = audio;
                    document.removeEventListener('click', playOnClick);
                    document.removeEventListener('touchstart', playOnClick);
                } catch(err) {}
            };
            document.addEventListener('click', playOnClick);
            document.addEventListener('touchstart', playOnClick);
        }
    }

    async getMemorialData() {
        try {
            const res = await fetch('/api/activity/memorial/data/');
            return await res.json();
        } catch (e) {
            console.error(e);
            return {
                success: true,
                total_flowers: 0,
                time_info: {
                    years: 0, days: 0, total_days: 0,
                    hours: 0, minutes: 0, seconds: 0,
                    passing_time: '2026年3月24日 15:50:00'
                }
            };
        }
    }

    displayMemorialMessage(data) {
        const timeInfo = data.time_info;
        const totalFlowers = data.total_flowers;
        const messageId = 'memorialMsg_' + Date.now();
        const timeDisplay = `${timeInfo.total_days}天 ${timeInfo.hours}小时 ${timeInfo.minutes}分钟 ${timeInfo.seconds}秒`;
        const html = `
            <div id="${messageId}" class="memorial-container">
                <div style="margin-bottom: 12px;">
                    🕯️ <strong>深切缅怀张雪峰老师</strong> 🙏<br>
                    张老师于 ${timeInfo.passing_time} 离开了我们，至今已有：
                </div>
                <div style="background: #f0f2f5; padding: 12px; border-radius: 12px; margin: 12px 0;">
                    <div>📅 ${timeInfo.years}年 ${timeInfo.days}天</div>
                    <div>⏰ 共计 <span id="memorialTimeSpan_${messageId}">${timeDisplay}</span></div>
                    <div>🌸 已有 <span id="memorialFlowerCount_${messageId}">${totalFlowers}</span> 人为张老师献花</div>
                </div>
                <button id="memorialFlowerBtn_${messageId}" class="flower-btn" style="background: #ee5a24; color: white; border: none; padding: 10px 20px; border-radius: 40px; cursor: pointer; font-size: 14px; width: 100%; margin-top: 8px;">
                    🌹 献花哀悼
                </button>
                <div id="memorialFlowerMsg_${messageId}" style="margin-top: 8px; font-size: 12px; color: #ff9800; text-align: center;"></div>
                <div style="margin-top: 12px; font-size: 11px; color: #888; text-align: center;">张雪峰老师(1984-2026) 永远活在我们心中</div>
            </div>
        `;
        const msgDiv = this.addCustomMessage('bot', html);
        const flowerBtn = msgDiv.querySelector(`#memorialFlowerBtn_${messageId}`);
        if (flowerBtn) {
            flowerBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                await this.submitFlower(messageId);
            });
        }
    }

    async submitFlower(messageId) {
        const flowerBtn = document.getElementById(`memorialFlowerBtn_${messageId}`);
        const msgDiv = document.getElementById(`memorialFlowerMsg_${messageId}`);
        if (!flowerBtn) return;
        flowerBtn.disabled = true;
        flowerBtn.textContent = '⏳ 献花中...';
        try {
            const response = await fetch('/api/activity/memorial/flower/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                }
            });
            const data = await response.json();
            if (data.success) {
                const countSpan = document.getElementById(`memorialFlowerCount_${messageId}`);
                if (countSpan) countSpan.innerText = data.total_flowers;
                if (msgDiv) msgDiv.innerText = '🌹 感谢您的哀悼！张老师会记得您的心意 🙏';
                flowerBtn.disabled = false;
                flowerBtn.textContent = '🌹 献花哀悼';
                setTimeout(() => { if (msgDiv) msgDiv.innerText = ''; }, 3000);
            } else {
                if (msgDiv) msgDiv.innerText = '献花失败，请稍后重试';
                flowerBtn.disabled = false;
                flowerBtn.textContent = '🌹 献花哀悼';
            }
        } catch (err) {
            console.error(err);
            if (msgDiv) msgDiv.innerText = '网络错误，请稍后重试';
            flowerBtn.disabled = false;
            flowerBtn.textContent = '🌹 献花哀悼';
        }
    }

    // ==================== 上传识别 ====================
    async uploadAndRecognizeImage(file) {
        const formData = new FormData();
        formData.append('image', file);
        try {
            const response = await fetch('/api/upload/', {
                method: 'POST',
                headers: { 'X-CSRFToken': this.getCSRFToken() },
                body: formData
            });
            const data = await response.json();
            if (data.success) {
                this.uploadedImageText = data.text;
                this.uploadedImageFile = file;
                return data;
            } else {
                this.showToast('图片识别失败：' + (data.error || '未知错误'));
                return null;
            }
        } catch (error) {
            console.error('上传识别失败:', error);
            this.showToast('网络错误，请稍后重试');
            return null;
        }
    }

    showImagePreviewAndResult(file, ocrText) {
        const reader = new FileReader();
        reader.onload = (e) => {
            this.uploadedImagePreviewUrl = e.target.result;
            const previewContainer = document.getElementById('imagePreviewContainer');
            const previewImg = document.getElementById('imagePreview');
            const textPreviewDiv = document.getElementById('imageTextPreview');
            if (previewImg) previewImg.src = e.target.result;
            if (textPreviewDiv) {
                textPreviewDiv.innerHTML = `<strong>📝 OCR识别内容：</strong><br>${ocrText.substring(0, 200)}${ocrText.length > 200 ? '...' : ''}`;
            }
            if (previewContainer) previewContainer.style.display = 'block';
        };
        reader.readAsDataURL(file);
    }

    removeUploadedImage() {
        this.uploadedImageText = '';
        this.uploadedImagePreviewUrl = '';
        this.uploadedImageFile = null;
        const previewContainer = document.getElementById('imagePreviewContainer');
        const previewImg = document.getElementById('imagePreview');
        const textPreviewDiv = document.getElementById('imageTextPreview');
        if (previewContainer) previewContainer.style.display = 'none';
        if (previewImg) previewImg.src = '';
        if (textPreviewDiv) textPreviewDiv.innerHTML = '';
        if (this.fileInput) this.fileInput.value = '';
    }

    // ==================== 发送消息 ====================
    async sendMessage() {
        if (this.isSending) {
            this.showToast('⏳ 请等待上一条消息回复完成');
            return;
        }
        const message = this.messageInput.value.trim();
        const hasImage = this.uploadedImageText !== '';
        if (!message && !hasImage) return;

        if (message && this.isMemorialMessage(message)) {
            this.messageInput.value = '';
            this.removeUploadedImage();
            await this.handleMemorialMessage();
            return;
        }

        this.isSending = true;
        this.sendBtn.disabled = true;
        this.sendBtn.style.opacity = '0.5';
        this.sendBtn.style.cursor = 'not-allowed';
        const uploadBtn = document.getElementById('uploadImageBtn');
        if (uploadBtn && hasImage) {
            uploadBtn.disabled = true;
            uploadBtn.style.opacity = '0.5';
        }
        this.messageInput.value = '';

        let displayMessage = message;
        if (hasImage) {
            displayMessage = message ? `${message}\n\n📷 [图片识别内容]\n${this.uploadedImageText.substring(0, 150)}${this.uploadedImageText.length > 150 ? '...' : ''}` : `📷 [图片识别内容]\n${this.uploadedImageText.substring(0, 150)}...`;
        }
        this.addMessage('user', displayMessage);
        this.showTyping();

        try {
            const response = await fetch('/api/send/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    message: message || '',
                    conversation_id: this.currentConversationId,
                    image_text: this.uploadedImageText || ''
                })
            });
            const data = await response.json();
            this.hideTyping();
            if (data.success) {
                if (data.conversation_id !== this.currentConversationId) {
                    this.currentConversationId = data.conversation_id;
                    this.loadConversationList();
                }
                this.addMessage('assistant', data.response);
                this.removeUploadedImage();
            } else {
                this.addMessage('assistant', '😅 抱歉出了点问题：' + (data.error || '未知错误'));
            }
        } catch (error) {
            this.hideTyping();
            this.addMessage('assistant', '🌐 网络连接异常，请检查后端服务是否正常运行');
            console.error(error);
        } finally {
            this.isSending = false;
            this.sendBtn.disabled = false;
            this.sendBtn.style.opacity = '1';
            this.sendBtn.style.cursor = 'pointer';
            if (uploadBtn) {
                uploadBtn.disabled = false;
                uploadBtn.style.opacity = '1';
            }
        }
    }

    // ==================== 会话管理 ====================
    async loadConversationList() {
        try {
            const response = await fetch('/api/conversations/');
            const data = await response.json();
            const listContainer = document.getElementById('conversationList');
            if (data.conversations && data.conversations.length > 0) {
                listContainer.innerHTML = data.conversations.map(conv => `
                    <div class="conv-item ${conv.id === this.currentConversationId ? 'active' : ''}" data-id="${conv.id}">
                        <div class="conv-title" data-id="${conv.id}">${this.escapeHtml(conv.title)}</div>
                        <div class="conv-time" data-id="${conv.id}">${conv.updated_at}</div>
                        <span class="conv-delete" data-id="${conv.id}">🗑️</span>
                    </div>
                `).join('');
                listContainer.querySelectorAll('.conv-title, .conv-time').forEach(el => {
                    el.addEventListener('click', (e) => {
                        const id = el.dataset.id;
                        if (id) this.loadConversation(id);
                    });
                });
                listContainer.querySelectorAll('.conv-delete').forEach(el => {
                    el.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const id = el.dataset.id;
                        if (id) this.deleteConversation(id);
                    });
                });
            } else {
                listContainer.innerHTML = '<div class="empty-conversations" style="text-align:center; padding:30px; opacity:0.6;">✨ 暂无对话记录<br>点击上方按钮开始新对话</div>';
            }
        } catch (error) {
            console.error('加载会话列表失败:', error);
        }
    }

    async loadConversation(conversationId) {
        if (this.isLoading) return;
        this.stopAllAudio();
        this.isLoading = true;
        this.currentConversationId = conversationId;
        document.querySelectorAll('.conv-item').forEach(item => {
            item.classList.remove('active');
            if (item.dataset.id === conversationId) item.classList.add('active');
        });
        try {
            const response = await fetch(`/api/conversations/${conversationId}/`);
            const data = await response.json();
            this.messagesContainer.innerHTML = '';
            this.removeUploadedImage();
            if (data.messages && data.messages.length > 0) {
                data.messages.forEach(msg => {
                    this.addMessage(msg.role, msg.content, msg.created_at);
                });
            } else {
                this.addMessage('assistant', '你好！有什么可以帮助你的吗？');
            }
            this.updateUserAvatars();
        } catch (error) {
            this.messagesContainer.innerHTML = '';
            this.addMessage('assistant', '加载会话失败，请刷新重试');
        } finally {
            this.isLoading = false;
        }
    }

    async createNewChat() {
        this.stopAllAudio();
        this.currentConversationId = null;
        this.messagesContainer.innerHTML = '';
        this.removeUploadedImage();
        this.addMessage('assistant', '✨ 你好！我是张雪峰，有什么志愿填报问题尽管问我！');
        this.loadConversationList();
        this.closeSidebarOnMobile();
    }

    async deleteConversation(conversationId) {
        if (!confirm('确定要删除这个对话吗？删除后无法恢复！')) return;
        try {
            const response = await fetch(`/api/conversations/${conversationId}/delete/`, {
                method: 'DELETE',
                headers: { 'X-CSRFToken': this.getCSRFToken() }
            });
            const result = await response.json();
            if (result.success) {
                if (this.currentConversationId === conversationId) this.createNewChat();
                await this.loadConversationList();
            } else {
                alert('删除失败：' + (result.error || '未知错误'));
            }
        } catch (error) {
            console.error('删除失败:', error);
            alert('删除失败，请稍后重试');
        }
    }

    setupImageUpload() {
        const uploadBtn = document.getElementById('uploadImageBtn');
        if (!uploadBtn) return;
        uploadBtn.addEventListener('click', () => {
            if (this.uploadedImageText) {
                this.showToast('请先发送当前图片或点击移除按钮');
                return;
            }
            if (this.isSending) {
                this.showToast('请等待当前消息发送完成');
                return;
            }
            if (this.isUploadingImage) {
                this.showToast('正在上传中，请稍候...');
                return;
            }
            if (this.fileInput) {
                this.fileInput.value = '';
                this.fileInput.click();
            }
        });
        const removeBtn = document.getElementById('removeImageBtn');
        if (removeBtn) {
            removeBtn.addEventListener('click', () => this.removeUploadedImage());
        }
    }

    toggleSidebar() {
        document.getElementById('sidebar')?.classList.toggle('open');
    }

    closeSidebarOnMobile() {
        if (window.innerWidth <= 768) {
            document.getElementById('sidebar')?.classList.remove('open');
        }
    }
}

document.addEventListener('DOMContentLoaded', function() {
    window.chatApp = new ChatApp();
});