/* ========================================================
   全局桌宠 Desktop Pet（可拖动 · 位置持久化 · 互动菜单）
   放在 static/desktop_pet.js，所有页面通过 <script> 引入
   ======================================================== */
(function() {
    'use strict';

    const STORAGE_KEY = 'lzr_pet_pos_v1';

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
        '点击我有惊喜 🎁'
    ];
    const PET_JOKES = [
        '为什么程序员分不清万圣节和圣诞节？Oct 31 == Dec 25 🎃',
        '基站和 Wi-Fi 打架谁赢？基站！因为信号更强 📡',
        'AI 会做梦吗？会！梦到自己跑成了死循环 💭',
        '路由器从不迷路，因为它有路由表 🗺️',
        '5G 为什么快？因为它不堵车 🚗💨',
        '为什么数据不会飞？因为它走的是光纤 🪶'
    ];
    const PET_TIPS = [
        '💡 小贴士：选"深度思考"模式获得更详细回答',
        '💡 小贴士：知识图谱里可以点击节点看详情',
        '💡 小贴士：周任务支持故障排查和AI报告',
        '💡 小贴士：岗位匹配帮你找到适合方向',
        '💡 小贴士：把我拖到喜欢的位置吧～'
    ];
    const PET_GREETS = [
        '嗨~你好呀！👋',
        '今天也要加油哦！✨',
        '灵智尚人，随时为你服务！🤖',
        '欢迎回来！想聊点什么？💬'
    ];

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
                <div class="pet-menu-item" data-act="tip">💡 今日提示</div>
                <div class="pet-menu-item" data-act="joke">😄 讲个冷知识</div>
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
                // 边界检查，防止上次保存的位置超出当前屏幕
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
        // 默认位置：右下角
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

    /* ---------- 拖拽 ---------- */
    function enableDrag(el) {
        let isDragging = false;
        let startX, startY, origLeft, origTop;
        let moved = false;
        const DRAG_THRESHOLD = 5; // 移动超过 5px 才算拖拽

        function onDown(e) {
            // 如果点的是菜单里的按钮，不启动拖拽
            if (e.target.closest('.pet-menu')) return;
            isDragging = true;
            moved = false;
            const pt = e.touches ? e.touches[0] : e;
            startX = pt.clientX; startY = pt.clientY;
            const rect = el.getBoundingClientRect();
            origLeft = rect.left;
            origTop = rect.top;
            el.style.left = origLeft + 'px';
            el.style.top = origTop + 'px';
            el.style.right = 'auto';
            el.style.bottom = 'auto';
            el.classList.add('dragging');
            document.body.style.userSelect = 'none';
            e.preventDefault();
        }
        function onMove(e) {
            if (!isDragging) return;
            const pt = e.touches ? e.touches[0] : e;
            const dx = pt.clientX - startX;
            const dy = pt.clientY - startY;
            if (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD) {
                moved = true;
                // 边界约束
                const w = el.offsetWidth, h = el.offsetHeight;
                const nx = Math.min(Math.max(0, origLeft + dx), window.innerWidth - w);
                const ny = Math.min(Math.max(0, origTop + dy), window.innerHeight - h);
                el.style.left = nx + 'px';
                el.style.top = ny + 'px';
            }
            if (e.cancelable) e.preventDefault();
        }
        function onUp() {
            if (!isDragging) return;
            isDragging = false;
            el.classList.remove('dragging');
            document.body.style.userSelect = '';
            if (moved) savePos(el);
            // 拖拽结束后，如果没怎么移动，当成点击（由 click 处理器处理）
        }

        el.addEventListener('mousedown', onDown);
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
        el.addEventListener('touchstart', onDown, {passive: false});
        document.addEventListener('touchmove', onMove, {passive: false});
        document.addEventListener('touchend', onUp);
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

    function bindMenu(el) {
        const menu = el.querySelector('.pet-menu');

        // 点击（非拖拽）→ 切换菜单
        let clickStartX, clickStartY;
        el.addEventListener('mousedown', (e) => {
            if (e.target.closest('.pet-menu')) return;
            clickStartX = e.clientX; clickStartY = e.clientY;
        });
        el.addEventListener('mouseup', (e) => {
            if (e.target.closest('.pet-menu')) return;
            const dx = e.clientX - clickStartX, dy = e.clientY - clickStartY;
            if (Math.abs(dx) < 5 && Math.abs(dy) < 5) {
                // 还没被 menu 的 click stopPropagation 挡住，所以 toggle
                e.stopPropagation();
                menu.classList.toggle('show');
                if (menu.classList.contains('show')) {
                    // 调整菜单方向：如果靠右，菜单向左展开
                    const rect = el.getBoundingClientRect();
                    if (rect.left + 150 > window.innerWidth) {
                        menu.style.right = 'auto';
                        menu.style.left = '0';
                    } else {
                        menu.style.left = 'auto';
                        menu.style.right = '0';
                    }
                }
            }
        });

        // 点页面其他地方关菜单
        document.addEventListener('click', (e) => {
            if (!el.contains(e.target)) menu.classList.remove('show');
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
            case 'greet': say(el, PET_GREETS[Math.floor(Math.random()*PET_GREETS.length)]); break;
            case 'tip':   say(el, PET_TIPS[Math.floor(Math.random()*PET_TIPS.length)], 3500); break;
            case 'joke':  say(el, PET_JOKES[Math.floor(Math.random()*PET_JOKES.length)], 4500); break;
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

    /* ---------- 自动眨眼 & 自动说话 ---------- */
    function blinkLoop(el) {
        setInterval(() => {
            // 用 class 控制眨眼
            const img = el.querySelector('img');
            if (!img) return;
            // 眨眼通过 scaleY 实现——但 SVG 不好直接控制，用 opacity 闪烁代替
            img.style.transition = 'opacity 0.08s';
            img.style.opacity = '0.7';
            setTimeout(() => { img.style.opacity = '1'; }, 90);
            setTimeout(() => { img.style.opacity = '0.55'; }, 100);
            setTimeout(() => { img.style.opacity = '1'; }, 190);
        }, 3500 + Math.random() * 2500);
    }
    function autoChatLoop(el) {
        setTimeout(function tick() {
            const msg = PET_MSGS[Math.floor(Math.random()*PET_MSGS.length)];
            say(el, msg);
            setTimeout(tick, 25000 + Math.random() * 25000);
        }, 6000 + Math.random() * 4000);
    }

    /* ---------- 启动 ---------- */
    function init() {
        if (document.getElementById('globalPet')) return; // 防止重复注入
        const el = buildPet();
        loadPos(el);
        enableDrag(el);
        bindMenu(el);
        blinkLoop(el);
        autoChatLoop(el);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
