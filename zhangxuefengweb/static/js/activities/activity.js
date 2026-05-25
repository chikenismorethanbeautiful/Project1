// static/js/activities/activity.js
// 哀悼张雪峰老师活动组件

class MemorialActivity extends BaseActivityComponent {
    constructor(container, activityId) {
        super(container, activityId);
        this.audio = null;
        this.updateTimer = null;
    }

    render() {
        const timeInfo = this.data.time_info;
        const totalFlowers = this.data.total_flowers;

        this.container.innerHTML = `
            <div class="memorial-activity" id="memorialActivity">
                <style>
                    .memorial-activity {
                        background: linear-gradient(135deg, #2c2c3e 0%, #1a1a2e 100%);
                        border-radius: 20px;
                        padding: 20px;
                        color: #fff;
                        margin: 10px 0;
                        box-shadow: 0 8px 32px rgba(0,0,0,0.2);
                        animation: memorialFadeIn 0.5s ease;
                    }
                    
                    @keyframes memorialFadeIn {
                        from {
                            opacity: 0;
                            transform: translateY(20px);
                        }
                        to {
                            opacity: 1;
                            transform: translateY(0);
                        }
                    }
                    
                    .memorial-header {
                        text-align: center;
                        border-bottom: 1px solid rgba(255,255,255,0.1);
                        padding-bottom: 15px;
                        margin-bottom: 20px;
                    }
                    
                    .memorial-header h3 {
                        font-size: 1.5rem;
                        color: #ffd700;
                        margin: 0 0 5px 0;
                    }
                    
                    .memorial-header p {
                        color: #aaa;
                        margin: 0;
                        font-size: 0.85rem;
                    }
                    
                    .memorial-stats {
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                        gap: 15px;
                        margin-bottom: 20px;
                    }
                    
                    .stat-card {
                        background: rgba(255,255,255,0.1);
                        border-radius: 12px;
                        padding: 15px;
                        text-align: center;
                        backdrop-filter: blur(10px);
                    }
                    
                    .stat-label {
                        display: block;
                        font-size: 0.85rem;
                        color: #ccc;
                        margin-bottom: 8px;
                    }
                    
                    .stat-value {
                        font-size: 2rem;
                        font-weight: bold;
                        color: #ffd700;
                    }
                    
                    .stat-unit {
                        font-size: 0.9rem;
                        color: #ccc;
                        margin-left: 4px;
                    }
                    
                    .time-detail {
                        background: rgba(0,0,0,0.3);
                        border-radius: 12px;
                        padding: 15px;
                        text-align: center;
                        margin-bottom: 20px;
                        font-family: monospace;
                        font-size: 1.1rem;
                    }
                    
                    .flower-btn {
                        width: 100%;
                        padding: 14px;
                        background: linear-gradient(135deg, #ff6b6b, #ee5a24);
                        border: none;
                        border-radius: 40px;
                        color: white;
                        font-size: 1.2rem;
                        font-weight: bold;
                        cursor: pointer;
                        transition: transform 0.2s, box-shadow 0.2s;
                        margin-top: 10px;
                    }
                    
                    .flower-btn:hover {
                        transform: translateY(-2px);
                        box-shadow: 0 5px 20px rgba(238,90,36,0.4);
                    }
                    
                    .flower-btn:active {
                        transform: translateY(0);
                    }
                    
                    .flower-btn.disabled {
                        opacity: 0.6;
                        cursor: not-allowed;
                        transform: none;
                    }
                    
                    .flower-message {
                        margin-top: 15px;
                        text-align: center;
                        font-size: 0.9rem;
                        color: #ffd700;
                        animation: messageFade 0.5s ease;
                    }
                    
                    @keyframes messageFade {
                        from {
                            opacity: 0;
                            transform: translateY(-10px);
                        }
                        to {
                            opacity: 1;
                            transform: translateY(0);
                        }
                    }
                    
                    .memorial-note {
                        text-align: center;
                        font-size: 0.75rem;
                        color: #666;
                        margin-top: 15px;
                        padding-top: 15px;
                        border-top: 1px solid rgba(255,255,255,0.1);
                    }
                </style>
                
                <div class="memorial-header">
                    <h3>🕯️ 深切缅怀张雪峰老师</h3>
                    <p>中国著名高考志愿指导专家 · 教育工作者</p>
                </div>
                
                <div class="memorial-stats">
                    <div class="stat-card">
                        <span class="stat-label">📅 已离开</span>
                        <span class="stat-value" id="memorialYears">${timeInfo.years}</span>
                        <span class="stat-unit">年</span>
                        <span class="stat-value" id="memorialDays">${timeInfo.days}</span>
                        <span class="stat-unit">天</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-label">🌸 献花人数</span>
                        <span class="stat-value" id="memorialFlowerCount">${totalFlowers}</span>
                        <span class="stat-unit">人</span>
                    </div>
                </div>
                
                <div class="time-detail" id="timeDetail">
                    总计: ${this.formatTimeDetail(timeInfo)}
                </div>
                
                <button class="flower-btn" id="memorialFlowerBtn">
                    🌹 献花哀悼
                </button>
                <div id="memorialFlowerMessage" class="flower-message"></div>
                <div class="memorial-note">
                    张雪峰老师(1984-2026) 永远活在我们心中
                </div>
            </div>
        `;

        // 启动实时计时器
        this.startTimer();
    }

    formatTimeDetail(timeInfo) {
        return `${timeInfo.total_days}天 ${timeInfo.hours}小时 ${timeInfo.minutes}分钟 ${timeInfo.seconds}秒`;
    }

    startTimer() {
        if (this.updateTimer) clearInterval(this.updateTimer);

        this.updateTimer = setInterval(async () => {
            try {
                const response = await fetch('/api/activity/memorial/time/');
                const data = await response.json();
                if (data.success) {
                    const yearsEl = document.getElementById('memorialYears');
                    const daysEl = document.getElementById('memorialDays');
                    const timeDetailEl = document.getElementById('timeDetail');

                    if (yearsEl) yearsEl.textContent = data.time_info.years;
                    if (daysEl) daysEl.textContent = data.time_info.days;
                    if (timeDetailEl) {
                        timeDetailEl.textContent = `总计: ${data.time_info.total_days}天 ${data.time_info.hours}小时 ${data.time_info.minutes}分钟 ${data.time_info.seconds}秒`;
                    }

                    const flowerCountEl = document.getElementById('memorialFlowerCount');
                    if (flowerCountEl && data.total_flowers) {
                        flowerCountEl.textContent = data.total_flowers;
                    }
                }
            } catch (error) {
                console.error('更新时间失败:', error);
            }
        }, 1000);
    }

    bindEvents() {
        const flowerBtn = document.getElementById('memorialFlowerBtn');
        if (flowerBtn) {
            flowerBtn.addEventListener('click', async () => {
                if (flowerBtn.classList.contains('disabled')) return;

                flowerBtn.classList.add('disabled');
                flowerBtn.textContent = '⏳ 献花中...';

                try {
                    const response = await fetch('/api/activity/memorial/flower/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCsrfToken()
                        }
                    });

                    const data = await response.json();
                    const messageDiv = document.getElementById('memorialFlowerMessage');

                    if (data.success) {
                        const flowerCountEl = document.getElementById('memorialFlowerCount');
                        if (flowerCountEl) flowerCountEl.textContent = data.total_flowers;

                        messageDiv.innerHTML = '🌹 感谢您的哀悼！张老师会记得您的这份心意 🙏';
                        messageDiv.style.color = '#ffd700';

                        this.playFlowerSound();

                        setTimeout(() => {
                            flowerBtn.classList.remove('disabled');
                            flowerBtn.textContent = '🌹 献花哀悼';
                            setTimeout(() => {
                                if (messageDiv) messageDiv.innerHTML = '';
                            }, 3000);
                        }, 3000);
                    } else {
                        messageDiv.innerHTML = data.error || '献花失败，请稍后重试';
                        messageDiv.style.color = '#ff6b6b';
                        flowerBtn.classList.remove('disabled');
                        flowerBtn.textContent = '🌹 献花哀悼';
                    }
                } catch (error) {
                    console.error('献花失败:', error);
                    const messageDiv = document.getElementById('memorialFlowerMessage');
                    messageDiv.innerHTML = '网络错误，请稍后重试';
                    messageDiv.style.color = '#ff6b6b';
                    flowerBtn.classList.remove('disabled');
                    flowerBtn.textContent = '🌹 献花哀悼';
                }
            });
        }
    }

    playFlowerSound() {
        try {
            const audio = new Audio('/static/activities/flower.mp3');
            audio.volume = 0.3;
            audio.play().catch(e => console.log('音效播放失败:', e));
        } catch (e) {}
    }

    destroy() {
        if (this.updateTimer) {
            clearInterval(this.updateTimer);
            this.updateTimer = null;
        }
        if (this.audio) {
            this.audio.pause();
            this.audio = null;
        }
    }
}

// 注册哀悼活动组件
window.registerActivity('memorial', MemorialActivity);