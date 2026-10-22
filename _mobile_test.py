"""手机视口(375x812)实测首页按钮点击 + 触摸事件"""
import asyncio
from playwright.async_api import async_playwright

BASE = "http://121.40.21.238:5000"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # iPhone 视口 + 触摸
        ctx = await browser.new_context(
            viewport={"width": 375, "height": 812},
            is_mobile=True,
            has_touch=True,
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        )
        page = await ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(f"[console.{m.type}] {m.text}") if m.type == "error" else None)

        # 登录
        await page.goto(BASE + "/login", timeout=30000)
        await page.wait_for_timeout(4000)  # 等 splash 播完
        print("URL:", page.url, "| Title:", await page.title())
        has_input = await page.evaluate("!!document.getElementById('studentNo')")
        splash = await page.evaluate("(()=>{const o=document.getElementById('splashOverlay');return o?getComputedStyle(o).display:'removed'})()")
        await page.screenshot(path="_mobile_login.png")
        print(f"#studentNo 存在: {has_input} | splash 状态: {splash}")
        await page.fill("#studentNo", "2505080703000")
        await page.fill("#studentName", "lh")
        await page.fill("#password", "tongxin2024")
        await page.click("button.login-btn")
        await page.wait_for_url("**/", timeout=15000)
        await page.wait_for_timeout(2500)
        print("✅ 登录成功，URL:", page.url)

        # ---- 测试1: Tab 点击（宫格数量变化）----
        expect_counts = {"study": 5, "res": 3, "grow": 5}
        for label, cat in [("学习中心", "study"), ("资源中心", "res"), ("成长中心", "grow")]:
            tab = page.locator(f".hx-tab[data-cat='{cat}']")
            visible = await tab.is_visible()
            if not visible:
                print(f"❌ Tab[{label}] 不可见/被遮挡! visible={visible}")
                # 遮挡诊断
                box = await tab.bounding_box()
                if box:
                    cover = await page.evaluate(f"""() => {{
                        const el = document.elementFromPoint({box['x']+box['width']/2}, {box['y']+box['height']/2});
                        return el ? el.className + '|' + el.tagName : 'null';
                    }}""")
                    print(f"   遮挡诊断: elementFromPoint = {cover} (期望 hx-tab)")
                continue
            await tab.tap()
            await page.wait_for_timeout(400)
            n = await page.evaluate(f"document.querySelectorAll('#hxQuickGrid .hx-qitem:not(.hx-hide)').length")
            ok = "✅" if n == expect_counts[cat] else "❌"
            print(f"{ok} Tab[{label}] 点击后可见宫格: {n} (期望 {expect_counts[cat]})")

        # 回到实训中心
        await page.locator(".hx-tab[data-cat='all']").tap()
        await page.wait_for_timeout(300)

        # ---- 测试2: AI 助手 Tab ----
        await page.locator(".hx-tab[data-view='chat']").tap()
        await page.wait_for_timeout(500)
        chat_visible = await page.evaluate("document.getElementById('hxChatView').style.display")
        print(("✅" if chat_visible == "block" else "❌") + f" AI助手Tab: hxChatView display={chat_visible}")
        # AI 全屏对话页无 Tab 栏，刷新回首页继续
        await page.goto(BASE + "/", timeout=20000)
        await page.wait_for_timeout(1500)

        # ---- 测试3: 宫格卡片跳转 ----
        for name, path in [("互动练习", "/exercise-page"), ("错题本", "/wrong-questions-page")]:
            try:
                link = page.locator(f"#hxQuickGrid a[href='{path}']")
                await link.tap()
                await page.wait_for_url(f"**{path}", timeout=8000)
                print(f"✅ 宫格[{name}] 跳转成功 → {page.url}")
            except Exception as e:
                # 诊断遮挡
                box = await link.bounding_box()
                cover = await page.evaluate(f"""() => {{
                    const b = arguments[0];
                    const el = document.elementFromPoint(b.x + b.width/2, b.y + b.height/2);
                    return el ? el.className + '|' + el.tagName : 'null';
                }}""", box) if box else "no-box"
                print(f"❌ 宫格[{name}] 跳转失败: {str(e)[:80]} | 遮挡: {cover}")
            await page.goto(BASE + "/", timeout=20000)
            await page.wait_for_timeout(1200)

        # ---- 测试4: 汉堡菜单 + 抽屉链接 ----
        burger = page.locator("#hxBurger")
        if await burger.is_visible():
            await burger.tap()
            await page.wait_for_timeout(500)
            drawer_open = await page.evaluate("document.getElementById('hxDrawer').classList.contains('hx-open')")
            print(("✅" if drawer_open else "❌") + f" 汉堡菜单打开抽屉: {drawer_open}")
            if drawer_open:
                link = page.locator("#hxDrawerNav a[href='/scenario-page']").first
                await link.tap()
                try:
                    await page.wait_for_url("**/scenario-page", timeout=8000)
                    print("✅ 抽屉[剧情演绎] 跳转成功 →", page.url)
                except Exception as e:
                    print("❌ 抽屉[剧情演绎] 跳转失败:", str(e)[:80])
        else:
            print("❌ 汉堡按钮不可见")

        # ---- 测试5: 学生端导航是否有安全审计 ----
        await page.goto(BASE + "/", timeout=20000)
        await page.wait_for_timeout(1500)
        has_audit = await page.evaluate(
        "!!document.querySelector('a[href*=\"audit-log-page\"]')"
        )
        print(("❌ 学生端出现安全审计!" if has_audit else "✅ 学生端无安全审计入口"))

        # ---- JS 错误汇总 ----
        if errors:
            print(f"\n⚠️ JS 错误 {len(errors)} 条:")
            for e in errors[:8]:
                print("  -", e[:150])
        else:
            print("\n✅ 无 JS 错误")

        await browser.close()

asyncio.run(main())
