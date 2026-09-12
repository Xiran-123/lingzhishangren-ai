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

    /* 进入页面欢迎语：时段问候 + 存在感提示（每次进入都会说，让用户第一时间看见桌宠） */
    function entryGreeting() {
        return pick([
            getTimePhrase() + ' 我在这儿哦 👋',
            getTimePhrase() + ' 需要我就点我一下～ 💬',
            pick(PET_GREETS),
            '我上线啦！双击我还有彩蛋 🌀',
            '看好我哦，我会一直陪着你 🫶'
        ]);
    }

    /* ---------- 错题数查询（桌宠动态提醒用） ---------- */
    let _wrongCache = { count: -1, ts: 0 }; // 缓存30秒，避免每次都请求
    async function fetchWrongCount() {
        try {
            const now = Date.now();
            if (_wrongCache.count >= 0 && now - _wrongCache.ts < 30000) {
                return _wrongCache;
            }
            const resp = await fetch('/api/wrong-questions', { credentials: 'same-origin' });
            if (!resp.ok) return null;
            const data = await resp.json();
            if (!data.success) return null;
            const unmastered = data.unmastered || 0;
            _wrongCache = { count: unmastered, ts: now };
            return _wrongCache;
        } catch (_) { return null; }
    }

    /* 生成错题提醒消息（有概率触发，且只有当有错题时才说） */
    function pickWrongReminder(count) {
        if (!count || count <= 0) return null;
        const phrases = [
            `还有 ${count} 道错题没复习呢，抽空看看吧 📝`,
            `${count} 道错题等着你哦，复习一下更牢靠 💪`,
            `错题本里还有 ${count} 道待攻克，加油鸭 🐤`,
            `嘿，你有 ${count} 道错题还没掌握～去错题本看看？📕`,
            `${count} 道错题在召唤你！复习完就打勾 ✅`
        ];
        return pick(phrases);
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
                <div class="pet-menu-item" data-act="chat">💬 聊天互动</div>
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
                // v3: 先尝试侧边磁吸，吸不上才按原位保存
                if (!trySnap(el)) savePos(el);
                if (Math.random() < 0.3) say(el, pick(PET_LAND), 1600);
            }
        }

        /* ---------- v3: 侧边磁吸 ---------- */
        const SNAP_DIST = 36; // 距边缘 36px 内自动吸附
        function trySnap(el) {
            const rect = el.getBoundingClientRect();
            const cands = [
                { d: rect.left,                            x: 0,                               y: rect.top },
                { d: window.innerWidth  - rect.right,      x: window.innerWidth - rect.width,  y: rect.top },
                { d: rect.top,                             x: rect.left,                       y: 0 },
                { d: window.innerHeight - rect.bottom,     x: rect.left,                       y: window.innerHeight - rect.height }
            ].sort((a, b) => a.d - b.d);
            const near = cands[0];
            if (near.d > SNAP_DIST) return false;
            // 弹性吸附动画
            el.style.transition = 'left 0.28s cubic-bezier(0.34,1.56,0.64,1), top 0.28s cubic-bezier(0.34,1.56,0.64,1)';
            el.style.left = near.x + 'px';
            el.style.top  = near.y + 'px';
            setTimeout(() => { el.style.transition = ''; savePos(el); }, 320);
            // 贴边挤压小动画
            playAnim(el, 'pet-anim-wiggle', 500);
            if (Math.random() < 0.8) say(el, '吸住啦 🧲', 1300);
            return true;
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
            case 'chat': toggleChat(el); break;
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

    /* ========================================================
       v3: 迷你聊天面板（实时互动 · 娱乐 + 平台使用助手）
       在线：转发到 Flask /chat 接口（真 AI 对话）
       离线/未登录：本地应答（娱乐闲聊 + 功能导航跳转）
       ======================================================== */
    const PET_NAV = [
        { kws: ['周任务', '任务'],        name: '📋 周任务',   url: '/weekly-tasks-page' },
        { kws: ['沉浸式'],                name: '🎬 沉浸式剧情', url: '/scenario-demo' },
        { kws: ['剧情', '演绎'],          name: '🎭 剧情演绎', url: '/scenario-page' },
        { kws: ['知识图谱', '图谱'],      name: '🧠 知识图谱', url: '/knowledge-graph-page' },
        { kws: ['岗位', '招聘', '求职'],  name: '💼 岗位招聘', url: '/job-recruitment-page' },
        { kws: ['错题'],                  name: '📕 错题本',   url: '/wrong-questions-page' },
        { kws: ['画像', '能力'],          name: '📊 能力画像', url: '/student-portrait-page' },
        { kws: ['班级', '通知'],          name: '📢 班级通知', url: '/class-notification-page' },
        { kws: ['练习', '刷题'],          name: '✏️ 互动练习', url: '/exercise-page' },
        { kws: ['报告'],                  name: '📄 学生报告', url: '/student-report-page' },
        { kws: ['问卷', '调查'],          name: '📝 调查问卷', url: '/survey-page' },
        { kws: ['上传', '知识库'],        name: '📤 知识上传', url: '/upload-knowledge-page' },
        { kws: ['日志', '记录'],          name: '🔍 日志查询', url: '/search-logs-page' }
    ];
    const PET_SMALLTALK = [
        '嘿嘿，我在听～然后呢？👀',
        '哈哈，被你发现了，我最爱聊天了 💬',
        '嗯嗯！继续说，我拿小本本记着呢 📝',
        '你说话的样子真好看（虽然我看不见）😄',
        '哔——收到信号！🛰️'
    ];
    const PET_FALLBACK = [
        '嗯…这个问题有点超纲了 🤔 换个说法试试？',
        '我的小脑瓜转不动了，回主界面问我吧，那里的我更聪明 💪',
        '嘀嘀——信号不好，稍后再问我一次？📡'
    ];

    let chatPanel = null;
    let chatHistory = [];   // [{role, content}] 供 AI 上下文
    let chatBusy = false;
    let chatWelcomed = false;

    function toggleChat(el) {
        if (!chatPanel) chatPanel = buildChatPanel(el);
        const show = !chatPanel.classList.contains('show');
        chatPanel.classList.toggle('show', show);
        if (show) {
            positionChat(el);
            const input = chatPanel.querySelector('input');
            setTimeout(() => input.focus(), 200);
            if (!chatWelcomed) {
                chatWelcomed = true;
                botSay(el, '嗨！我是灵智小助手 🤖<br>可以和我闲聊解闷，也可以问我平台怎么用～<br>试试：<b>打开剧情演绎</b> / <b>帮助</b> / <b>讲个笑话</b>');
            }
        }
    }
    function buildChatPanel(el) {
        const p = document.createElement('div');
        p.className = 'pet-chat-panel';
        p.innerHTML = `
            <div class="pet-chat-head">
                <span class="pet-chat-dot"></span>
                <span class="pet-chat-title">灵智小助手 · 在线</span>
                <span class="pet-chat-clear" title="清空对话">🗑️</span>
                <span class="pet-chat-close" title="收起">✕</span>
            </div>
            <div class="pet-chat-list"></div>
            <div class="pet-chat-input-row">
                <input type="text" maxlength="200" placeholder="说点什么吧…（Enter 发送）">
                <button class="pet-chat-send">➤</button>
            </div>
        `;
        document.body.appendChild(p);

        p.querySelector('.pet-chat-close').addEventListener('click', () => p.classList.remove('show'));
        p.querySelector('.pet-chat-clear').addEventListener('click', () => {
            p.querySelector('.pet-chat-list').innerHTML = '';
            chatHistory = [];
            botSay(el, '对话已清空～我们重新开始吧 ✨');
        });
        const input = p.querySelector('input');
        const send = () => sendChat(el);
        p.querySelector('.pet-chat-send').addEventListener('click', send);
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
        return p;
    }
    function positionChat(el) {
        const rect = el.getBoundingClientRect();
        const W = 264, H = 360, M = 8;
        let left = rect.left - W + 60;
        let top  = rect.top - H - 10;
        if (left < M) left = M;
        if (left + W > window.innerWidth - M) left = window.innerWidth - W - M;
        if (top < M) top = Math.min(M, window.innerHeight - H - M);
        if (top + H > window.innerHeight - M) top = window.innerHeight - H - M;
        chatPanel.style.left = left + 'px';
        chatPanel.style.top  = top + 'px';
    }
    function escapeHtml(s) {
        return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }
    function pushMsg(el, role, html) {
        const list = chatPanel.querySelector('.pet-chat-list');
        const div = document.createElement('div');
        div.className = 'pet-chat-msg ' + role;
        div.innerHTML = html;
        list.appendChild(div);
        while (list.children.length > 30) list.removeChild(list.firstChild);
        list.scrollTop = list.scrollHeight;
    }
    function botSay(el, html) { pushMsg(el, 'bot', html); }
    function showTyping(el) {
        botSay(el, '<span class="pet-typing"><i></i><i></i><i></i></span>');
        chatPanel.querySelector('.pet-chat-list').lastChild.classList.add('typing-msg');
    }
    function removeTyping() {
        const t = chatPanel.querySelector('.typing-msg');
        if (t) t.remove();
    }

    /* 本地指令匹配（导航 / 帮助 / 娱乐），命中返回 HTML，否则 null */
    function matchLocal(text) {
        const t = text.trim().toLowerCase();
        // 1. 页面导航：消息很短且像"打开XX / 去XX / XX怎么去"
        if (t.length <= 12) {
            const clean = t.replace(/^(打开|去|进入|跳转|带我(去|到)?)/, '').replace(/(页面|呗|吧|呀|啊)$/, '').trim();
            for (const nav of PET_NAV) {
                if (nav.kws.some(kw => clean.includes(kw))) {
                    return `好的，带你前往 ${nav.name} 🚀<br><a class="pet-nav-link" href="${nav.url}">点击进入 →</a><br><small>（也可以直接点上面的链接）</small>`;
                }
            }
        }
        // 2. 帮助
        if (/^(帮助|帮忙|怎么用|使用说明|指南|help)/.test(t)) {
            let html = '📖 <b>快速上手指南</b><br>';
            html += '· 和我聊天：直接打字，AI 在线时能实时回答<br>';
            html += '· 快速跳转：输入"打开周任务"、"去岗位招聘"等<br>';
            html += '· 侧边吸附：把我拖到屏幕边缘试试 🧲<br>';
            html += '· 双击我：转圈圈 🌀 · 连点5下：有惊喜 😵‍💫<br>';
            html += '· 常用入口：<a class="pet-nav-link" href="/scenario-demo">沉浸式剧情</a> · <a class="pet-nav-link" href="/weekly-tasks-page">周任务</a> · <a class="pet-nav-link" href="/job-recruitment-page">岗位招聘</a>';
            return html;
        }
        // 3. 娱乐指令
        if (/笑话|冷知识|逗/.test(t)) { return escapeHtml(pick(PET_JOKES)); }
        if (/加油|鼓励|夸|鸡汤|打气/.test(t)) { return '💪 ' + escapeHtml(pick(PET_CHEERS)); }
        if (/几点|时间|日期/.test(t)) {
            const d = new Date();
            return `现在是 ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}，${getTimePhrase()}`;
        }
        if (/你是谁|你叫什么|介绍/.test(t)) {
            return '我是<b>灵智小助手</b> 🤖 灵智尚人 AI 工程训练平台的桌宠！主职卖萌与导航，兼职 AI 聊天（主界面里的我更聪明哦）✨';
        }
        // 4. 寒暄类短消息 → 本地娱乐回复
        if (t.length <= 8 && /^(你好|嗨|哈喽|hello|hi|在吗|在么)/.test(t)) {
            return escapeHtml(pick(PET_GREETS));
        }
        return null;
    }

    async function sendChat(el) {
        if (chatBusy || !chatPanel) return;
        const input = chatPanel.querySelector('input');
        const text = input.value.trim();
        if (!text) return;
        input.value = '';

        pushMsg(el, 'user', escapeHtml(text));

        // 本地指令优先（导航/帮助/娱乐，秒回）
        const local = matchLocal(text);
        if (local) { botSay(el, local); return; }

        // 走后端真 AI
        chatBusy = true;
        showTyping(el);
        try {
            const r = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    mode: 'fast',
                    stream: false,
                    persona: 'pet',  // 幽默桌宠人设
                    conversation_history: chatHistory.slice(-6)
                })
            });
            removeTyping();
            if (r.status === 401) {
                botSay(el, '登录之后我就能聪明地聊天啦～现在只有娱乐模式 😜<br>' + escapeHtml(pick(PET_SMALLTALK)));
            } else {
                const d = await r.json().catch(() => ({}));
                if (d.response) {
                    botSay(el, escapeHtml(d.response));
                    chatHistory.push({ role: 'user', content: text });
                    chatHistory.push({ role: 'assistant', content: d.response });
                    if (chatHistory.length > 12) chatHistory = chatHistory.slice(-12);
                } else {
                    botSay(el, escapeHtml(pick(PET_FALLBACK)));
                }
            }
        } catch (err) {
            removeTyping();
            botSay(el, escapeHtml(pick(PET_SMALLTALK)) + '<br><small>（AI 信号不佳，先陪我玩会儿～）</small>');
        }
        chatBusy = false;
        const inp = chatPanel.querySelector('input');
        if (chatPanel.classList.contains('show')) inp.focus();
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
        setTimeout(async function tick() {
            // 先查错题数（异步，失败静默）
            const w = await fetchWrongCount();
            let msg = null;
            if (w && w.count > 0 && Math.random() < 0.35) {
                // 35%概率说错题提醒
                msg = pickWrongReminder(w.count);
            }
            if (!msg) msg = pickAutoMsg();
            say(el, msg);
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
        if (localStorage.getItem('pet_disabled') === '1') return; // 设置里可关闭桌宠
        if (document.getElementById('globalPet')) return; // 防止重复注入
        const el = buildPet();
        const state = { moved: false }; // 拖拽状态，拖拽与点击判定共享
        loadPos(el);
        enableDrag(el, state);
        bindMenu(el, state);
        blinkLoop(el);
        autoChatLoop(el);
        idleActionLoop(el);
        // 每次进入页面：0.6秒后主动打招呼 + 弹跳动画，让用户第一时间注意到桌宠
        setTimeout(() => {
            say(el, entryGreeting(), 4500);
            playAnim(el, 'pet-anim-bounce', 700);
        }, 600);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
