/* =========================================================
   全站顶部导航栏脚本（配合 static/app_nav.css）
   页面只需：<div id="appNav"></div> + 引用本文件
   行为：
     - 按当前路径高亮对应标签
     - 从首页 iframe 内打开时，点击导航改为整页跳转（target=_top）
     - 右键读取 /current-user 显示当前用户，支持退出登录
   ========================================================= */
(function () {
    'use strict';

    var TABS = [
        { key: 'home', label: '🏠 首页', href: '/' },
        { key: 'portrait', label: '🎯 能力画像', href: '/student-portrait-page' },
        { key: 'report', label: '📊 学生分析', href: '/student-report-page' },
        { key: 'weekly', label: '📚 周任务', href: '/weekly-tasks-page' },
        { key: 'ppt', label: '🗂 课件中心', href: '/ppt-resources-page' },
        { key: 'chat', label: '🤖 AI 助手', href: '/?tab=chat' }
    ];

    var inFrame = (function () {
        try { return window.self !== window.top; } catch (e) { return true; }
    })();

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function activeKey(pathname) {
        var p = pathname || location.pathname;
        if (p === '/' || p === '/index' || p === '') return 'home';
        if (p.indexOf('student-portrait') >= 0) return 'portrait';
        if (p.indexOf('student-report') >= 0) return 'report';
        if (p.indexOf('weekly-tasks') >= 0) return 'weekly';
        if (p.indexOf('ppt-resources') >= 0) return 'ppt';
        return '';
    }

    function build() {
        var host = document.getElementById('appNav');
        if (!host) return null;

        var key = activeKey();
        var nav = document.createElement('nav');
        nav.className = 'appnav';
        nav.setAttribute('role', 'navigation');
        nav.setAttribute('aria-label', '全站导航');

        var tabsHTML = TABS.map(function (t) {
            return '<a class="appnav-tab' + (t.key === key ? ' on' : '') + '" href="' + t.href + '"' +
                (inFrame ? ' target="_top"' : '') + '>' + t.label + '</a>';
        }).join('');

        nav.innerHTML =
            '<a class="appnav-logo" href="/"' + (inFrame ? ' target="_top"' : '') + '>' +
                '<span class="appnav-mark">🧠</span>灵智尚人</a>' +
            '<div class="appnav-tabs">' + tabsHTML + '</div>' +
            '<div class="appnav-right">' +
                '<div class="appnav-user" id="appNavUser" title="当前用户">' +
                    '<span class="appnav-ava" id="appNavAva">·</span>' +
                    '<span class="appnav-uname" id="appNavName">加载中</span>' +
                    '<span class="appnav-role" id="appNavRole"></span>' +
                '</div>' +
                '<button class="appnav-logout" id="appNavLogout" type="button">退出</button>' +
            '</div>';

        host.appendChild(nav);
        return nav;
    }

    function fillUser() {
        if (typeof fetch !== 'function') return;
        function setFallback() {
            var nameEl = document.getElementById('appNavName');
            if (nameEl && (nameEl.textContent === '加载中' || !nameEl.textContent)) {
                nameEl.textContent = '未登录';
            }
        }
        fetch('/current-user', { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (u) {
                if (!u || u.error) { setFallback(); return; }
                var name = u.student_name || (u.role === 'teacher' ? '老师' : '同学');
                var roleTxt = u.role === 'teacher' ? '教师' : '学生';
                var nameEl = document.getElementById('appNavName');
                var roleEl = document.getElementById('appNavRole');
                var avaEl = document.getElementById('appNavAva');
                if (nameEl) nameEl.textContent = name;
                if (roleEl) roleEl.textContent = roleTxt;
                if (avaEl) avaEl.textContent = String(name).charAt(0) || '·';
            })
            .catch(setFallback);
    }

    function bindLogout() {
        var btn = document.getElementById('appNavLogout');
        if (!btn) return;
        btn.addEventListener('click', function () {
            if (!confirm('确定要退出登录吗？')) return;
            fetch('/logout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin'
            }).catch(function () { /* 忽略 */ })
              .then(function () {
                  try {
                      localStorage.removeItem('lingzhi_chat_history');
                      localStorage.removeItem('lingzhi_scenario_history');
                  } catch (e) { /* 隐私模式忽略 */ }
                  location.href = '/';
              });
        });
    }

    function init() {
        build();
        // 导航为 fixed 定位，给 body 加类以便内容整体下移
        if (document.body) document.body.classList.add('has-appnav');
        fillUser();
        bindLogout();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
