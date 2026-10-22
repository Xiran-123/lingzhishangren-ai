"""验证：点击导航后主区域原地切换为功能页，返回首页恢复"""
import asyncio
from playwright.async_api import async_playwright

BASE = "http://121.40.21.238:5000"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1200, "height": 800})
        page = await ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))

        await page.goto(BASE + "/login", timeout=30000)
        await page.fill("#studentNo", "2505080703000")
        await page.fill("#studentName", "lh")
        await page.fill("#password", "tongxin2024")
        await page.click("#loginBtn")
        await page.wait_for_url("**/", timeout=15000)
        await page.wait_for_timeout(2000)
        print("✅ 登录成功")

        # 1. 点侧边导航「互动练习」→ 内容区隐藏、承载层显示
        await page.click("#hxSideNav a[href='/exercise-page']")
        await page.wait_for_timeout(2500)
        content_hidden = await page.evaluate("getComputedStyle(document.querySelector('#hxHome > .hx-layout')).display === 'none'")
        pv_visible = await page.evaluate("document.getElementById('hxPageView').style.display === 'block'")
        src = await page.evaluate("document.getElementById('hxPageIframe').src")
        title = await page.evaluate("document.getElementById('hxPageTitle').textContent")
        url_still = page.url == BASE + "/"
        print(("✅" if content_hidden and pv_visible and "/exercise-page" in src else "❌") +
              f" 点导航[互动练习]: 内容区隐藏={content_hidden} 承载层显示={pv_visible} iframe={src} 标题={title} URL未跳转={url_still}")

        # 2. iframe 内内容确实加载了互动练习页
        frame_el = page.frame_locator("#hxPageIframe")
        try:
            await frame_el.locator("body").wait_for(timeout=8000)
            body_text = await page.evaluate("document.getElementById('hxPageIframe').contentDocument.body.innerText.slice(0,60)")
            print(f"✅ iframe 内容已加载: {body_text[:40]}...")
        except Exception as e:
            print(f"❌ iframe 内容加载异常: {str(e)[:80]}")
        await page.screenshot(path="_embed_test.png")

        # 3. 点「返回首页」→ 恢复
        await page.click(".hx-pageback")
        await page.wait_for_timeout(600)
        content_back = await page.evaluate("getComputedStyle(document.querySelector('#hxHome > .hx-layout')).display !== 'none'")
        pv_hidden = await page.evaluate("document.getElementById('hxPageView').style.display === 'none'")
        print(("✅" if content_back and pv_hidden else "❌") + f" 返回首页恢复: 内容区显示={content_back} 承载层隐藏={pv_hidden}")

        # 4. 点宫格卡片「错题本」→ 内嵌切换
        await page.click("#hxQuickGrid a[href='/wrong-questions-page']")
        await page.wait_for_timeout(2000)
        src2 = await page.evaluate("document.getElementById('hxPageIframe').src")
        print(("✅" if "/wrong-questions-page" in src2 else "❌") + f" 点宫格[错题本] 内嵌切换: iframe={src2}")

        # 5. 切 Tab 应关闭内嵌页回宫格
        await page.click(".hx-tab[data-cat='study']")
        await page.wait_for_timeout(600)
        pv_hidden2 = await page.evaluate("document.getElementById('hxPageView').style.display === 'none'")
        home_back2 = await page.evaluate("document.getElementById('hxHome').style.display === 'block'")
        print(("✅" if pv_hidden2 and home_back2 else "❌") + f" 切Tab关闭内嵌页: 承载层隐藏={pv_hidden2} 首页恢复={home_back2}")

        if errs:
            print(f"\n⚠️ JS 错误: {errs[:3]}")
        else:
            print("\n✅ 无 JS 错误")
        await browser.close()

asyncio.run(main())
