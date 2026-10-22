# -*- coding: utf-8 -*-
"""前沿知识更新定时调度器（对应教学方案模块4）

与 job_scheduler 结构保持一致（APScheduler 优先，缺失时降级为线程定时器），差异点：
1. 采用懒启动：页面首次访问时才启动，避免导入模块时就发起网络请求
2. 启动后不立即抓取，按配置间隔执行，避免影响应用启动速度
"""

import threading
import time
from datetime import datetime
from typing import Callable, Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False

import frontier_crawler


class FrontierScheduler:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.scheduler = None
        self.thread_timer = None
        self.is_running = False
        self.job_id = "frontier_knowledge_fetch"
        self.on_fetch_callback: Optional[Callable] = None
        self.last_fetch_time = None
        self.last_stats = None
        self.fetch_count = 0

    def set_fetch_callback(self, callback: Callable):
        self.on_fetch_callback = callback

    def start(self) -> bool:
        """启动调度（幂等）"""
        if self.is_running:
            return True
        if APSCHEDULER_AVAILABLE:
            return self._start_apscheduler()
        return self._start_thread_timer()

    def _start_apscheduler(self) -> bool:
        try:
            config = frontier_crawler.load_frontier_config()
            interval_hours = int(config.get("fetch_interval_hours", 12))

            self.scheduler = BackgroundScheduler()
            self.scheduler.add_job(
                self._fetch_task,
                trigger=IntervalTrigger(hours=interval_hours),
                id=self.job_id,
                name="前沿知识自动抓取",
                replace_existing=True,
                next_run_time=None,          # 不立即执行，避免启动时发起网络请求
            )
            self.scheduler.start()
            self.is_running = True
            print(f"[前沿调度器-APScheduler] 启动成功，每{interval_hours}小时抓取一次")
            return True
        except Exception as e:
            print(f"[前沿调度器-APScheduler] 启动失败: {e}")
            return self._start_thread_timer()

    def _start_thread_timer(self) -> bool:
        try:
            config = frontier_crawler.load_frontier_config()
            interval_seconds = int(config.get("fetch_interval_hours", 12)) * 3600
            self.is_running = True

            def run_loop():
                while self.is_running:
                    for _ in range(interval_seconds):
                        if not self.is_running:
                            return
                        time.sleep(1)
                    try:
                        self._fetch_task()
                    except Exception as e:
                        print(f"[前沿调度器-ThreadTimer] 执行任务出错: {e}")

            self.thread_timer = threading.Thread(target=run_loop, daemon=True)
            self.thread_timer.start()
            print("[前沿调度器-ThreadTimer] 启动成功")
            return True
        except Exception as e:
            print(f"[前沿调度器-ThreadTimer] 启动失败: {e}")
            return False

    def _fetch_task(self):
        print(f"\n[前沿调度器] 开始抓取 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.last_fetch_time = datetime.now()
        self.fetch_count += 1
        try:
            config = frontier_crawler.load_frontier_config()
            if not config.get("auto_fetch_enabled", True):
                print("[前沿调度器] 自动抓取已关闭，跳过本次任务")
                return
            stats = frontier_crawler.fetch_all_frontier(use_mock_fallback=True)
            self.last_stats = stats
            if self.on_fetch_callback:
                try:
                    self.on_fetch_callback(stats)
                except Exception as e:
                    print(f"[前沿调度器] 回调执行出错: {e}")
            print(f"[前沿调度器] 任务完成，新增 {stats.get('added', 0)} 条")
        except Exception as e:
            print(f"[前沿调度器] 任务执行出错: {e}")

    def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        if self.scheduler and APSCHEDULER_AVAILABLE:
            try:
                self.scheduler.shutdown(wait=False)
            except Exception as e:
                print(f"[前沿调度器] 停止失败: {e}")
        self.thread_timer = None
        print("[前沿调度器] 已停止")

    def fetch_now(self) -> dict:
        """立即执行一次抓取，返回抓取统计"""
        print(f"[前沿调度器] 手动触发抓取 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.last_fetch_time = datetime.now()
        self.fetch_count += 1
        stats = frontier_crawler.fetch_all_frontier(use_mock_fallback=True)
        self.last_stats = stats
        if self.on_fetch_callback:
            try:
                self.on_fetch_callback(stats)
            except Exception as e:
                print(f"[前沿调度器] 回调执行出错: {e}")
        return stats

    def set_auto_fetch(self, enabled: bool):
        config = frontier_crawler.load_frontier_config()
        config["auto_fetch_enabled"] = bool(enabled)
        frontier_crawler.save_frontier_config(config)
        print(f"[前沿调度器] 自动抓取已{'开启' if enabled else '关闭'}")

    def update_interval(self, hours: int):
        hours = max(1, int(hours))
        config = frontier_crawler.load_frontier_config()
        config["fetch_interval_hours"] = hours
        frontier_crawler.save_frontier_config(config)
        if APSCHEDULER_AVAILABLE and self.scheduler and getattr(self.scheduler, "running", False):
            try:
                self.scheduler.reschedule_job(self.job_id, trigger=IntervalTrigger(hours=hours))
                print(f"[前沿调度器] 抓取间隔已更新为{hours}小时")
            except Exception as e:
                print(f"[前沿调度器] 更新间隔失败: {e}")

    def get_status(self) -> dict:
        config = frontier_crawler.load_frontier_config()
        items = frontier_crawler.load_frontier_items()
        return {
            "is_running": self.is_running,
            "using_apscheduler": APSCHEDULER_AVAILABLE,
            "auto_fetch_enabled": config.get("auto_fetch_enabled", True),
            "fetch_interval_hours": config.get("fetch_interval_hours", 12),
            "freshness_days": config.get("freshness_days", 180),
            "ai_grading_enabled": config.get("ai_grading_enabled", True),
            "last_fetch_time": self.last_fetch_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.last_fetch_time else config.get("last_fetch_time"),
            "fetch_count": self.fetch_count or config.get("fetch_count", 0),
            "enabled_sources": config.get("sources", []),
            "total_items": len(items),
            "last_stats": self.last_stats,
            "scheduler_type": "APScheduler" if APSCHEDULER_AVAILABLE else "ThreadTimer",
        }


frontier_scheduler = FrontierScheduler()
_frontier_autostart_lock = threading.Lock()
_frontier_autostarted = False


def autostart():
    """懒启动：首次访问看板时启动调度器（幂等）"""
    global _frontier_autostarted
    if _frontier_autostarted:
        return frontier_scheduler
    with _frontier_autostart_lock:
        if not _frontier_autostarted:
            frontier_crawler.init_frontier_data()
            frontier_scheduler.start()
            _frontier_autostarted = True
    return frontier_scheduler
