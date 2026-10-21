/* =========================================================
   班级管理面板（入口在「班级通知」页，任何页面也可复用）
   用法：页面引入 class_import.css + class_import.js，
        任意按钮 onclick="openClassManager()"
   导入完成后会派发 window 事件 'roster-imported'，页面自行刷新列表
   ========================================================= */
(function () {
    'use strict';

    if (window.__classManagerReady) return;
    window.__classManagerReady = true;

    var ST = {
        classes: [],        // [{id, name, count}]
        preview: null,      // 解析结果
        selectedClass: '',  // 左侧选中的班级名
        busy: false,
    };

    function el(id) { return document.getElementById(id); }

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function toast(msg) {
        if (typeof window.showKbToast === 'function') { window.showKbToast(msg); return; }
        var tip = document.createElement('div');
        tip.textContent = msg;
        tip.style.cssText = 'position:fixed;left:50%;bottom:40px;transform:translateX(-50%);' +
            'background:rgba(20,30,60,.92);color:#fff;padding:10px 20px;border-radius:10px;' +
            'font-size:13px;z-index:2000;box-shadow:0 8px 24px rgba(0,0,0,.3)';
        document.body.appendChild(tip);
        setTimeout(function () { tip.remove(); }, 2200);
    }

    /* ---------------------------- 结构 ---------------------------- */
    function buildModal() {
        if (el('cimOverlay')) return;
        var gradeOpts = '<option value="">按学号自动识别</option>';
        var now = new Date();
        var startYear = now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1;
        for (var i = 0; i < 8; i++) {
            var y = startYear - i;
            gradeOpts += '<option value="' + y + '级">' + y + '级</option>';
        }

        var wrap = document.createElement('div');
        wrap.className = 'cim-overlay';
        wrap.id = 'cimOverlay';
        wrap.innerHTML =
            '<div class="cim-modal">' +
                '<div class="cim-head">' +
                    '<div class="cim-title">🏫 班级管理</div>' +
                    '<button class="cim-close" onclick="closeClassManager()" title="关闭">✕</button>' +
                '</div>' +
                '<div class="cim-body">' +
                    '<div class="cim-left">' +
                        '<div class="cim-sec-title"><span>班级列表</span><b id="cimClassTotal"></b></div>' +
                        '<div id="cimClassList"><div class="cim-empty">加载中…</div></div>' +
                        '<div class="cim-newclass">' +
                            '<input id="cimNewClassName" placeholder="新建班级，如 通信2401" maxlength="30">' +
                            '<button onclick="createClassFromManager()">新建</button>' +
                        '</div>' +
                    '</div>' +
                    '<div class="cim-right">' +
                        '<div class="cim-form">' +
                            '<div class="cim-field"><label>导入到班级</label>' +
                                '<select id="cimTargetClass" onchange="onTargetClassChange()">' +
                                    '<option value="">按表格里的班级列</option>' +
                                '</select></div>' +
                            '<div class="cim-field"><label>年级（可留空）</label>' +
                                '<select id="cimGrade">' + gradeOpts + '</select></div>' +
                            '<div class="cim-field"><label>专业（可留空）</label>' +
                                '<input id="cimMajor" type="text" placeholder="如 通信工程"></div>' +
                        '</div>' +
                        '<div class="cim-drop" id="cimDrop">' +
                            '📄 点击或拖拽名单文件到这里<br>' +
                            '<span style="font-size:12px;color:#a8aec0;">' +
                            '支持 .xlsx / .xlsm / .csv　学习通导出的学生名单可直接上传</span>' +
                        '</div>' +
                        '<input type="file" id="cimFile" accept=".xlsx,.xlsm,.csv" style="display:none">' +
                        '<div id="cimPreview"></div>' +
                    '</div>' +
                '</div>' +
                '<div class="cim-foot">' +
                    '<div class="cim-hint" id="cimHint">先上传名单解析，确认无误后再导入</div>' +
                    '<div style="display:flex;gap:10px;">' +
                        '<button class="cim-btn ghost" onclick="closeClassManager()">关闭</button>' +
                        '<button class="cim-btn primary" id="cimConfirmBtn" disabled ' +
                            'onclick="confirmRosterImport()">确认导入</button>' +
                    '</div>' +
                '</div>' +
            '</div>';
        document.body.appendChild(wrap);

        // 点击遮罩关闭
        wrap.addEventListener('click', function (e) {
            if (e.target === wrap) closeClassManager();
        });

        // 文件选择 / 拖拽
        el('cimDrop').addEventListener('click', function () { el('cimFile').click(); });
        el('cimFile').addEventListener('change', function (e) {
            if (e.target.files && e.target.files[0]) handleFile(e.target.files[0]);
        });
        ['dragenter', 'dragover'].forEach(function (ev) {
            el('cimDrop').addEventListener(ev, function (e) {
                e.preventDefault(); e.stopPropagation();
                el('cimDrop').classList.add('drag');
            });
        });
        ['dragleave', 'drop'].forEach(function (ev) {
            el('cimDrop').addEventListener(ev, function (e) {
                e.preventDefault(); e.stopPropagation();
                el('cimDrop').classList.remove('drag');
            });
        });
        el('cimDrop').addEventListener('drop', function (e) {
            var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
            if (f) handleFile(f);
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && el('cimOverlay') && el('cimOverlay').classList.contains('show')) {
                closeClassManager();
            }
        });
    }

    /* ---------------------------- 班级列表 ---------------------------- */
    async function refreshClasses() {
        var counts = {};
        try {
            var r1 = await fetch('/api/classes');
            var d1 = await r1.json();
            var list = d1.classes || [];
            try {
                var r2 = await fetch('/api/students/filters');
                if (r2.ok) {
                    var d2 = await r2.json();
                    (d2.classes || []).forEach(function (c) { counts[c.value] = c.count; });
                }
            } catch (e) { /* 计数失败不影响列表 */ }

            ST.classes = list.map(function (c) {
                return { id: c.id, name: c.name, count: counts[c.name] || 0,
                         grade: c.grade || '' };
            });
            ST.classes.sort(function (a, b) {
                return String(a.name).localeCompare(String(b.name), 'zh');
            });
        } catch (e) {
            ST.classes = [];
        }
        renderClassList();
        fillTargetSelect();
    }

    function renderClassList() {
        var box = el('cimClassList');
        if (!box) return;
        if (!ST.classes.length) {
            box.innerHTML = '<div class="cim-empty">还没有班级，先在下方新建，或直接导入名单自动建班</div>';
        } else {
            box.innerHTML = ST.classes.map(function (c) {
                var on = ST.selectedClass === c.name ? ' on' : '';
                return '<div class="cim-class' + on + '" onclick="selectClassForImport(\'' +
                    esc(c.name).replace(/'/g, "\\'") + '\')" title="点击选中该班级作为导入目标">' +
                    '<span class="nm">' + esc(c.name) + '</span>' +
                    '<span class="cnt">' + c.count + '人</span>' +
                    '<button class="del" title="删除班级（不会删学生）" onclick="event.stopPropagation();' +
                    'deleteClassFromManager(' + c.id + ',\'' + esc(c.name).replace(/'/g, "\\'") + '\')">✕</button>' +
                    '</div>';
            }).join('');
        }
        var total = el('cimClassTotal');
        if (total) {
            var sum = ST.classes.reduce(function (a, c) { return a + c.count; }, 0);
            total.textContent = ST.classes.length + ' 个班 · ' + sum + ' 人';
        }
    }

    function fillTargetSelect() {
        var sel = el('cimTargetClass');
        if (!sel) return;
        var cur = sel.value;
        var html = '<option value="">按表格里的班级列</option>';
        html += ST.classes.map(function (c) {
            return '<option value="' + esc(c.name) + '">' + esc(c.name) + '（' + c.count + '人）</option>';
        }).join('');
        sel.innerHTML = html;
        if (cur && ST.classes.some(function (c) { return c.name === cur; })) sel.value = cur;
    }

    function selectClassForImport(name) {
        ST.selectedClass = (ST.selectedClass === name) ? '' : name;
        var sel = el('cimTargetClass');
        if (sel) sel.value = ST.selectedClass;
        renderClassList();
    }

    function onTargetClassChange() {
        ST.selectedClass = el('cimTargetClass').value;
        renderClassList();
    }

    async function createClassFromManager() {
        var input = el('cimNewClassName');
        var name = (input.value || '').trim();
        if (!name) { toast('请输入班级名称'); return; }
        try {
            var resp = await fetch('/api/classes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name })
            });
            var d = await resp.json();
            if (!resp.ok) { toast(d.error || '新建失败'); return; }
            input.value = '';
            ST.selectedClass = name;
            await refreshClasses();
            el('cimTargetClass').value = name;
            toast('已新建班级 ' + name);
        } catch (e) {
            toast('新建失败：' + e.message);
        }
    }

    async function deleteClassFromManager(id, name) {
        if (!confirm('确定删除班级「' + name + '」吗？\n只删班级，班级里的学生会保留（变成未分班）。')) return;
        try {
            var resp = await fetch('/api/classes/' + id, { method: 'DELETE' });
            var d = await resp.json();
            if (!resp.ok) { toast(d.error || '删除失败'); return; }
            if (ST.selectedClass === name) ST.selectedClass = '';
            await refreshClasses();
            toast('已删除班级 ' + name);
        } catch (e) {
            toast('删除失败：' + e.message);
        }
    }

    /* ---------------------------- 导入 ---------------------------- */
    async function handleFile(file) {
        var ext = (file.name.split('.').pop() || '').toLowerCase();
        if (['xlsx', 'xlsm', 'csv'].indexOf(ext) < 0) {
            toast('只支持 .xlsx / .xlsm / .csv，旧版 .xls 请先另存为 .xlsx');
            return;
        }
        var box = el('cimPreview');
        box.innerHTML = '<div class="cim-summary">正在解析「' + esc(file.name) + '」…</div>';
        setConfirmEnabled(false);

        var fd = new FormData();
        fd.append('file', file);
        fd.append('class_name', el('cimTargetClass').value || '');
        fd.append('grade', el('cimGrade').value || '');
        fd.append('major', (el('cimMajor').value || '').trim());

        try {
            var resp = await fetch('/api/students/import/preview', { method: 'POST', body: fd });
            var d = await resp.json();
            if (!resp.ok) {
                box.innerHTML = '<div class="cim-issues">❌ ' + esc(d.error || '解析失败') + '</div>';
                ST.preview = null;
                return;
            }
            ST.preview = d;
            renderPreview(d);
        } catch (e) {
            box.innerHTML = '<div class="cim-issues">❌ 网络错误：' + esc(e.message) + '</div>';
            ST.preview = null;
        }
    }

    function renderPreview(d) {
        var rows = d.students || [];
        var cols = d.mapping_detail || {};
        var mappingTxt = Object.keys(cols).map(function (k) {
            var label = { student_no: '学号', name: '姓名', class_name: '班级',
                          grade: '年级', major: '专业', college: '院系', phone: '手机号' }[k] || k;
            return label;
        }).join(' / ');

        var html = '<div class="cim-summary">' +
            '📄 <b>' + esc(d.filename) + '</b>' +
            '（工作表：' + esc(d.sheet || '-') + '，表头第 ' + d.header_row + ' 行）<br>' +
            '识别到的列：<b>' + esc(mappingTxt || '-') + '</b><br>' +
            '共解析 <b>' + d.total + '</b> 人：' +
            '<span style="color:#2e7d32;">新增 ' + d.new_count + '</span>' +
            ' · <span style="color:#e65100;">已存在 ' + d.duplicate_count + '</span>' +
            (d.invalid_count ? ' · <span style="color:#d32f2f;">跳过 ' + d.invalid_count + '</span>' : '') +
            (d.detected_classes && d.detected_classes.length
                ? '<br>涉及班级：<b>' + esc(d.detected_classes.slice(0, 6).join('、')) +
                  (d.detected_classes.length > 6 ? ' 等' : '') + '</b>' : '') +
            '</div>';

        if (d.issues && d.issues.length) {
            html += '<div class="cim-issues">⚠️ ' + d.issues.slice(0, 10).map(esc).join('<br>') + '</div>';
        }

        if (rows.length) {
            html += '<div class="cim-table-wrap"><table class="cim-table"><thead><tr>' +
                '<th>姓名</th><th>学号</th><th>班级</th><th>年级</th><th>专业</th><th>状态</th>' +
                '</tr></thead><tbody>';
            html += rows.slice(0, 200).map(function (s) {
                var badge = s.status === 'new'
                    ? '<span class="cim-badge new">新增</span>'
                    : '<span class="cim-badge dup">' + esc(s.status_text || '已存在') + '</span>';
                return '<tr><td>' + esc(s.name) + '</td><td>' + esc(s.student_no || '-') + '</td>' +
                    '<td>' + esc(s.class_name || '-') + '</td><td>' + esc(s.grade || '-') + '</td>' +
                    '<td>' + esc(s.major || '-') + '</td><td>' + badge + '</td></tr>';
            }).join('');
            html += '</tbody></table></div>';
            if (rows.length > 200) {
                html += '<div class="cim-hint" style="margin-top:6px;">仅显示前 200 行，导入时按全部 ' +
                    rows.length + ' 行处理</div>';
            }
        }

        el('cimPreview').innerHTML = html;

        var canImport = (d.new_count || 0) > 0;
        setConfirmEnabled(canImport);
        if (el('cimConfirmBtn')) {
            el('cimConfirmBtn').textContent = canImport
                ? '确认导入 ' + d.new_count + ' 人'
                : '没有可导入的新学生';
        }
        if (el('cimHint')) {
            el('cimHint').textContent = canImport
                ? '确认后写入学生档案，并按班级自动建档'
                : '名单里的人都已经在系统里了';
        }
    }

    function setConfirmEnabled(on) {
        var btn = el('cimConfirmBtn');
        if (btn) btn.disabled = !on;
    }

    async function confirmRosterImport() {
        if (ST.busy || !ST.preview) return;
        var rows = (ST.preview.students || []).filter(function (s) { return s.status === 'new'; });
        if (!rows.length) { toast('没有可导入的新学生'); return; }

        ST.busy = true;
        setConfirmEnabled(false);
        if (el('cimHint')) el('cimHint').textContent = '正在导入，请稍候…';

        try {
            var resp = await fetch('/api/students/import/confirm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    class_name: el('cimTargetClass').value || '',
                    grade: el('cimGrade').value || '',
                    major: (el('cimMajor').value || '').trim(),
                    students: rows,
                })
            });
            var d = await resp.json();
            if (!resp.ok) throw new Error(d.error || '导入失败');

            var msg = '✅ 已导入 <b>' + d.created + '</b> 人';
            if (d.skipped) msg += '，跳过 ' + d.skipped + ' 人';
            if (d.class_created && d.class_created.length) {
                msg += '<br>新建班级：<b>' + esc(d.class_created.join('、')) + '</b>';
            }
            el('cimPreview').innerHTML =
                '<div class="cim-summary" style="background:rgba(46,125,50,.1);color:#2e7d32;">' +
                msg + '</div>' + (el('cimPreview').innerHTML || '');

            if (el('cimHint')) el('cimHint').textContent = '导入完成，右侧学生列表已刷新';
            ST.preview = null;
            setConfirmEnabled(false);
            if (el('cimConfirmBtn')) el('cimConfirmBtn').textContent = '确认导入';

            await refreshClasses();
            // 通知宿主页面刷新学生列表
            window.dispatchEvent(new CustomEvent('roster-imported', {
                detail: { created: d.created, skipped: d.skipped, classes: d.class_created || [] }
            }));
        } catch (e) {
            if (el('cimHint')) el('cimHint').textContent = '导入失败：' + e.message;
            toast('导入失败：' + e.message);
        } finally {
            ST.busy = false;
        }
    }

    /* ---------------------------- 开关 ---------------------------- */
    async function openClassManager() {
        buildModal();
        el('cimOverlay').classList.add('show');
        document.body.style.overflow = 'hidden';
        await refreshClasses();
    }

    function closeClassManager() {
        var ov = el('cimOverlay');
        if (ov) ov.classList.remove('show');
        document.body.style.overflow = '';
    }

    window.openClassManager = openClassManager;
    window.closeClassManager = closeClassManager;
    window.selectClassForImport = selectClassForImport;
    window.onTargetClassChange = onTargetClassChange;
    window.createClassFromManager = createClassFromManager;
    window.deleteClassFromManager = deleteClassFromManager;
    window.confirmRosterImport = confirmRosterImport;
})();
