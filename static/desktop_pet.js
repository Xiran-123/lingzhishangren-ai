/* ========================================================
   全局桌宠 Desktop Pet v2（可拖动 · 位置持久化 · 丰富互动）
   放在 static/desktop_pet.js，所有页面通过 <script> 引入
   v2: 修复"拖拽后一直跟随鼠标" bug（Pointer Events + 指针捕获）
       + 文案库大扩充 + 双击/连点彩蛋 + 时段问候 + 随机小动作
   ======================================================== */
(function() {
    'use strict';

    const STORAGE_KEY = 'lzr_pet_pos_v1';

    /* ---------- 工具 ---------- */
    const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

    /* ---------- 文案库 ---------- */
    const PET_MSGS = [
        '系统在线 ✨',
        '有什么可以帮你的？',
        '试试"沉浸式剧情"吧 🎬',
        '知识图谱可以查知识点 🧠',
        '错题本要及时复习哦 📚',
        '每天进步一点点！💪',
        '别忘了完成周任务 📋',
        '信号塔已就绪 📡',
        'AI 随时待命！⚡',
        '点击我有惊喜 🎁',
        '能力画像里藏着你的成长曲线 📈',
        '岗位招聘帮你匹配未来方向 💼',
        '上传知识库，我就能学更多东西 📤',
        '互动练习做起来，手感最重要 ✏️',
        '班级通知有新消息我会提醒你 📢',
        '调查问卷填一下，让我更懂你 📝',
        '学生报告每周自动生成，超方便 📄',
        '日志查询能找到你的历史提问 🔍',
        '双击我可以转圈圈哦 🌀',
        '拖着我到屏幕任何角落～ 🖱️',
        '连续戳我 5 下试试？😏',
        '我会眨眼睛，你发现了吗 👀',
        '悄悄说：我喜欢蓝紫色 💜',
        '今天也要元气满满哦！🌟'
    ];
    const PET_JOKES = [
        '为什么程序员分不清万圣节和圣诞节？Oct 31 == Dec 25 🎃',
        '基站和 Wi-Fi 打架谁赢？基站！因为信号更强 📡',
        'AI 会做梦吗？会！梦到自己跑成了死循环 💭',
        '路由器从不迷路，因为它有路由表 🗺️',
        '5G 为什么快？因为它不堵车 🚗💨',
        '为什么数据不会飞？因为它走的是光纤 🪶',
        '程序员最讨厌的事：接手别人的代码，以及自己三个月前的代码 😅',
        '交换机开会说什么？大家都在同一个广播域里 📢',
        '云服务器为什么淡定？因为它在高处 ☁️',
        'Bug 和 Feature 的区别？看你能不能自圆其说 😉',
        '为什么服务器很冷静？因为它见过太多请求了 🧊',
        '光纤和网线赛跑，网线说：光速你赢了，但我便宜 💰'
    ];
    const PET_TIPS = [
        '💡 小贴士：选"深度思考"模式获得更详细回答',
        '💡 小贴士：知识图谱里可以点击节点看详情',
        '💡 小贴士：周任务支持故障排查和AI报告',
        '💡 小贴士：岗位匹配帮你找到适合方向',
        '💡 小贴士：把我拖到喜欢的位置吧～',
        '💡 小贴士：错题本支持一键AI讲解',
        '💡 小贴士：上传 docx/pptx 教案可自动入库',
        '💡 小贴士：能力画像雷达图会随练习更新',
        '💡 小贴士：沉浸式剧情有引导线索和毛玻璃面板',
        '💡 小贴士：双击我有惊喜，连点 5 下也有 😏'
    ];
    const PET_GREETS = [
        '嗨~你好呀！👋',
        '今天也要加油哦！✨',
        '灵智尚人，随时为你服务！🤖',
        '欢迎回来！想聊点什么？💬',
        '见到你真开心！🌟',
        '你好呀，我是你的 AI 小助手 🤖',
        '嗨！准备好学习了吗？📚',
        '哟！今天状态如何？💪'
    ];
    const PET_CHEERS = [
        '你是最棒的！冲就完了 🔥',
        '相信自己，你可以的 💪',
        '每一步都算数，继续前进 🚀',
        '别怕困难，我陪你一起 🤝',
        '今天流的汗，是明天的光 ✨',
        '坚持就是胜利，加油 🏆',
        '你已经比昨天更强了 📈',
        '深呼吸，你可以搞定一切 🍀'
    ];
    const PET_DRAG = [
        '哇~飞起来啦！🚀',
        '轻点儿~别把我甩出去 😵',
        '去哪呀？带我一个！🧭',
        '咻——自由飞翔 ✈️',
        '放手，我相信你 🫶',
        '啦啦啦~兜风中 🌬️'
    ];
    const PET_LAND = [
        '到站啦 🛬',
        '这里视野不错 👀',
        '安家落户 ✓',
        '就放这儿吧～',
        '新位置已存档 💾'
    ];
    const PET_DIZZY = [
        '别戳啦，好晕~ 😵‍💫',
        '再戳我要罢工了！😤',
        '咕噜咕噜...转晕了 🌀',
        '住手！我要告老师了 🫨',
        '哎呀呀，头都大了 🤯'
    ];
    const PET_SPIN = [
        '哇~转圈圈 🌀',
        '陀螺模式启动！🎡',
        '呼~有点晕 😵‍💫'
    ];

    /* 时段问候 */
    function getTimePhrase() {
        const h = new Date().getHours();
        if (h >= 5 && h < 11)  return pick(['早上好！新的一天元气满满 ☀️', '早呀！今天也要加油鸭 🐤', '一日之计在于晨 🌅']);
        if (h < 14)            return pick(['中午好！记得吃午饭哦 🍚', '午安！小憩一下更高效 😴']);
        if (h < 18)            return pick(['下午好！来杯下午茶 ☕', '下午加油，胜利在望 💪']);
        if (h < 23)            return pick(['晚上好！今晚也要努力哦 🌙', '夜色真美，学习正当时 ✨']);
        return pick(['夜深了，早点休息哦 🌃', '深夜好，注意身体呀 😴']);
    }
    function pickAutoMsg() {
        return Math.random() < 0.3 ? getTimePhrase() : pick(PET_MSGS);
    }

    /* ---------- 构建 DOM ---------- */
    function buildPet() {
        const el = document.createElement('div');
        el.className = 'global-desktop-pet';
        el.id = 'globalPet';
        el.innerHTML = `
            <div class="pet-drag-handle"></div>
            <div class="pet-body-wrap">
                <img src="/static/desktop_pet.svg" alt="桌宠" draggable="false">
            </div>
            <div class="pet-bubble" id="petBubble">系统在线 ✨</div>
            <div class="pet-menu" id="petMenu">
                <div class="pet-menu-title">🤖 灵智尚人 桌宠</div>
                <div class="pet-menu-item" data-act="greet">👋 打个招呼</div>
                <div class="pet-menu-item" data-act="cheer">🔥 加油打气</div>
                <div class="pet-menu-item" data-act="tip">💡 今日提示</div>
                <div class="pet-menu-item" data-act="joke">😄 讲个冷知识</div>
                <div class="pet-menu-item" data-act="random">🎲 随机惊喜</div>
                <div class="pet-menu-item" data-act="time">🕐 报个时间</div>
                <div class="pet-menu-item" data-act="hide">🙈 暂时隐藏 30s</div>
                <div class="pet-menu-item" data-act="sleep">😴 休眠 60s</div>
                <div class="pet-reset-btn" data-act="reset">↺ 重置位置</div>
            </div>
        `;
        document.body.appendChild(el);
        return el;
    }

    /* ---------- 位置持久化 ---------- */
    function loadPos(el) {
        try {
            const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
            if (saved && typeof saved.x === 'number' && typeof saved.y === 'number') {
                const maxX = window.innerWidth - el.offsetWidth;
                const maxY = window.innerHeight - el.offsetHeight;
                const x = Math.min(Math.max(0, saved.x), Math.max(0, maxX));
                const y = Math.min(Math.max(0, saved.y), Math.max(0, maxY));
                el.style.left = x + 'px';
                el.style.top = y + 'px';
                el.style.right = 'auto';
                el.style.bottom = 'auto';
                return;
            }
        } catch(e) {}
        el.style.right = '24px';
        el.style.bottom = '90px';
    }
    function savePos(el) {
        const rect = el.getBoundingClientRect();
        localStorage.setItem(STORAGE_KEY, JSON.stringify({
            x: Math.round(rect.left),
            y: Math.round(rect.top)
        }));
    }

    /* ---------- 拖拽（v2 修复版：Pointer Events + 指针捕获）----------
       修复"拖动后一直跟着鼠标"：
       旧版 mouseup 监听在 document 上，鼠标在浏览器窗口外松开时
       mouseup 不触发，isDragging 永远卡在 true → 桌宠持续跟随。
       新版用 setPointerCapture：捕获后即使指针移出窗口，pointerup
       也保证派发给桌宠元素，拖拽必然结束；另加 pointercancel +
       窗口失焦双保险。 */
    function enableDrag(el, state) {
        let isDragging = false;
        let startX, startY, origLeft, origTop;
        let saidDragMsg = false;
        const DRAG_THRESHOLD = 5; // 移动超过 5px 才算拖拽

        function endDrag(e) {
            if (!isDragging) return;
            isDragging = false;
            el.classList.remove('dragging');
            document.body.style.userSelect = '';
            if (e && e.pointerId !== undefined) {
                try { el.releasePointerCapture(e.pointerId); } catch(err) {}
            }
            if (state.moved) {
                savePos(el);
                if (Math.random() < 0.4) say(el, pick(PET_LAND), 1600);
            }
        }

        function onDown(e) {
            // 点的是菜单里的按钮 → 不拖拽
            if (e.target.closest('.pet-menu')) return;
            // 只响应主键（左键/触摸/笔）
            if (e.pointerType === 'mouse' && e.button !== 0) return;
            isDragging = true;
            state.moved = false;
            saidDragMsg = false;
            startX = e.clientX; startY = e.clientY;
            const rect = el.getBoundingClientRect();
            origLeft = rect.left;
            origTop = rect.top;
            el.style.left = origLeft + 'px';
            el.style.top = origTop + 'px';
            el.style.right = 'auto';
            el.style.bottom = 'auto';
            el.classList.add('dragging');
            document.body.style.userSelect = 'none';
            // 核心：捕获指针，窗口外松手也能收到 pointerup
            try { el.setPointerCapture(e.pointerId); } catch(err) {}
        }

        function onMove(e) {
            if (!isDragging) return;
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            if (!state.moved && (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD)) {
                state.moved = true;
                if (!saidDragMsg) {
                    saidDragMsg = true;
                    say(el, pick(PET_DRAG), 1600);
                }
            }
            if (state.moved) {
                const w = el.offsetWidth, h = el.offsetHeight;
                const nx = Math.min(Math.max(0, origLeft + dx), window.innerWidth - w);
                const ny = Math.min(Math.max(0, origTop + dy), window.innerHeight - h);
                el.style.left = nx + 'px';
                el.style.top = ny + 'px';
            }
        }

        el.addEventListener('pointerdown', onDown);
        el.addEventListener('pointermove', onMove);
        el.addEventListener('pointerup', endDrag);
        el.addEventListener('pointercancel', endDrag);
        // 双保险：窗口失焦时强制结束拖拽
        window.addEventListener('blur', () => endDrag(null));
    }

    /* ---------- 小动画 ---------- */
    function playAnim(el, cls, ms) {
        el.classList.remove('pet-anim-bounce', 'pet-anim-spin', 'pet-anim-wiggle');
        void el.offsetWidth; // 强制重排，保证动画可重触发
        el.classList.add(cls);
        setTimeout(() => el.classList.remove(cls), ms);
    }

    /* ---------- 气泡 & 菜单 ---------- */
    let hideTimer = null;
    function say(el, text, duration) {
        const bubble = el.querySelector('.pet-bubble');
        bubble.textContent = text;
        bubble.classList.add('show');
        if (hideTimer) clearTimeout(hideTimer);
        duration = duration || 2500;
        hideTimer = setTimeout(() => bubble.classList.remove('show'), duration);
    }

    function bindMenu(el, state) {
        const menu = el.querySelector('.pet-menu');

        // 点击（非拖拽）→ 切换菜单
        el.addEventListener('mouseup', (e) => {
            if (e.target.closest('.pet-menu')) return;
            if (state.moved) return; // 刚拖拽过，不当成点击
            e.stopPropagation();
            menu.classList.toggle('show');
            if (menu.classList.contains('show')) {
                // 菜单方向自适应：靠右则向左展开
                const rect = el.getBoundingClientRect();
                if (rect.left + 170 > window.innerWidth) {
                    menu.style.right = 'auto';
                    menu.style.left = '0';
                } else {
                    menu.style.left = 'auto';
                    menu.style.right = '0';
                }
            }
        });

        // 点页面其他地方关菜单
        document.addEventListener('click', (e) => {
            if (!el.contains(e.target)) menu.classList.remove('show');
        });

        // 双击彩蛋：转圈圈
        el.addEventListener('dblclick', (e) => {
            if (e.target.closest('.pet-menu')) return;
            menu.classList.remove('show');
            playAnim(el, 'pet-anim-spin', 850);
            say(el, pick(PET_SPIN), 2200);
        });

        // 连点 5 次彩蛋：戳晕了
        let clickTimes = [];
        el.addEventListener('click', (e) => {
            if (e.target.closest('.pet-menu')) return;
            const now = Date.now();
            clickTimes = clickTimes.filter(t => now - t < 1600);
            clickTimes.push(now);
            if (clickTimes.length >= 5) {
                clickTimes = [];
                menu.classList.remove('show');
                playAnim(el, 'pet-anim-wiggle', 700);
                say(el, pick(PET_DIZZY), 2600);
            }
        });

        // 菜单项点击
        menu.addEventListener('click', (e) => {
            const item = e.target.closest('[data-act]');
            if (!item) return;
            const act = item.dataset.act;
            menu.classList.remove('show');
            doAction(el, act);
        });
    }

    function doAction(el, act) {
        switch(act) {
            case 'greet':
                say(el, pick(PET_GREETS));
                playAnim(el, 'pet-anim-bounce', 700);
                break;
            case 'cheer':
                say(el, pick(PET_CHEERS), 3500);
                playAnim(el, 'pet-anim-bounce', 700);
                break;
            case 'tip':   say(el, pick(PET_TIPS), 3800); break;
            case 'joke':  say(el, pick(PET_JOKES), 4500); break;
            case 'random': {
                const pools = [PET_MSGS, PET_JOKES, PET_TIPS, PET_GREETS, PET_CHEERS];
                say(el, pick(pick(pools)), 4000);
                playAnim(el, 'pet-anim-bounce', 700);
                break;
            }
            case 'time': {
                const d = new Date();
                const hh = String(d.getHours()).padStart(2, '0');
                const mm = String(d.getMinutes()).padStart(2, '0');
                say(el, `现在是 ${hh}:${mm}，${getTimePhrase()}`, 4200);
                break;
            }
            case 'hide':  hidePet(el, 30000); break;
            case 'sleep': hidePet(el, 60000); break;
            case 'reset': resetPos(el); break;
        }
    }
    function hidePet(el, ms) {
        el.style.transition = 'opacity 0.5s, transform 0.5s';
        el.style.opacity = '0';
        el.style.transform = 'scale(0.3)';
        setTimeout(() => {
            el.style.display = 'none';
        }, 500);
        setTimeout(() => {
            el.style.display = '';
            setTimeout(() => {
                el.style.opacity = '1';
                el.style.transform = '';
                say(el, '我回来了~ 🫣');
            }, 50);
        }, ms);
    }
    function resetPos(el) {
        localStorage.removeItem(STORAGE_KEY);
        el.style.transition = 'all 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)';
        el.style.left = 'auto';
        el.style.top = 'auto';
        el.style.right = '24px';
        el.style.bottom = '90px';
        setTimeout(() => el.style.transition = '', 600);
        say(el, '位置已重置 ↺', 1800);
    }

    /* ---------- 眨眼 / 自动说话 / 随机小动作 ---------- */
    function blinkLoop(el) {
        const img = el.querySelector('img');
        if (!img) return;
        setTimeout(function blink() {
            if (el.style.display !== 'none') {
                img.style.transition = 'opacity 0.08s';
                img.style.opacity = '0.6';
                setTimeout(() => { img.style.opacity = '1'; }, 90);
                setTimeout(() => { img.style.opacity = '0.5'; }, 100);
                setTimeout(() => { img.style.opacity = '1'; }, 190);
            }
            setTimeout(blink, 2800 + Math.random() * 3200);
        }, 2000 + Math.random() * 2000);
    }
    function autoChatLoop(el) {
        setTimeout(function tick() {
            say(el, pickAutoMsg());
            setTimeout(tick, 25000 + Math.random() * 25000);
        }, 6000 + Math.random() * 4000);
    }
    function idleActionLoop(el) {
        // 没人理它的时候，偶尔自己蹦跶一下
        setTimeout(function tick() {
            if (el.style.display !== 'none' && !el.classList.contains('dragging')) {
                const r = Math.random();
                if (r < 0.4)      playAnim(el, 'pet-anim-bounce', 700);
                else if (r < 0.7) playAnim(el, 'pet-anim-wiggle', 600);
            }
            setTimeout(tick, 18000 + Math.random() * 15000);
        }, 12000 + Math.random() * 8000);
    }

    /* ---------- 启动 ---------- */
    function init() {
        if (document.getElementById('globalPet')) return; // 防止重复注入
        const el = buildPet();
        const state = { moved: false }; // 拖拽状态，拖拽与点击判定共享
        loadPos(el);
        enableDrag(el, state);
        bindMenu(el, state);
        blinkLoop(el);
        autoChatLoop(el);
        idleActionLoop(el);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
