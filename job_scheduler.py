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

import job_crawler


class JobScheduler:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self.scheduler = None
        self.thread_timer = None
        self.is_running = False
        self.job_id = "communication_job_fetch"
        self.on_fetch_callback: Optional[Callable] = None
        self.last_fetch_time = None
        self.fetch_count = 0

    def set_fetch_callback(self, callback: Callable):
        self.on_fetch_callback = callback

    def start(self):
        if self.is_running:
            print("[调度器] 调度器已在运行中")
            return False

        if APSCHEDULER_AVAILABLE:
            return self._start_apscheduler()
        else:
            return self._start_thread_timer()

    def _start_apscheduler(self) -> bool:
        try:
            self.scheduler = BackgroundScheduler()
            config = job_crawler.load_job_config()
            interval_hours = config.get("fetch_interval_hours", 6)

            self.scheduler.add_job(
                self._fetch_job_task,
                trigger=IntervalTrigger(hours=interval_hours),
                id=self.job_id,
                name="通信工程岗位招聘信息抓取",
                replace_existing=True,
                next_run_time=datetime.now()
            )

            self.scheduler.start()
            self.is_running = True
            print(f"[调度器-APScheduler] 启动成功，每{interval_hours}小时自动抓取一次")
            return True
        except Exception as e:
            print(f"[调度器-APScheduler] 启动失败: {e}")
            return self._start_thread_timer()

    def _start_thread_timer(self) -> bool:
        try:
            config = job_crawler.load_job_config()
            interval_hours = config.get("fetch_interval_hours", 6)
            interval_seconds = interval_hours * 3600

            self.is_running = True

            def run_loop():
                while self.is_running:
                    try:
                        self._fetch_job_task()
                    except Exception as e:
                        print(f"[调度器-ThreadTimer] 执行任务出错: {e}")

                    for _ in range(interval_seconds):
                        if not self.is_running:
                            break
                        time.sleep(1)

            self.thread_timer = threading.Thread(target=run_loop, daemon=True)
            self.thread_timer.start()

            print(f"[调度器-ThreadTimer] 启动成功，每{interval_hours}小时自动抓取一次")
            return True
        except Exception as e:
            print(f"[调度器-ThreadTimer] 启动失败: {e}")
            return False

    def _fetch_job_task(self):
        print(f"\n[调度器] 开始执行定时抓取任务 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.last_fetch_time = datetime.now()
        self.fetch_count += 1

        try:
            config = job_crawler.load_job_config()
            if not config.get("auto_fetch_enabled", True):
                print("[调度器] 自动抓取已关闭，跳过本次任务")
                return

            jobs = job_crawler.fetch_all_jobs(use_mock_fallback=True)
            deleted = job_crawler.delete_old_jobs(days=90)
            if deleted > 0:
                print(f"[调度器] 清理了{deleted}条过期招聘信息")

            if self.on_fetch_callback:
                try:
                    self.on_fetch_callback(jobs)
                except Exception as e:
                    print(f"[调度器] 回调执行出错: {e}")

            print(f"[调度器] 任务完成，当前共{len(jobs)}条招聘信息")

        except Exception as e:
            print(f"[调度器] 任务执行出错: {e}")

    def stop(self):
        if not self.is_running:
            return

        self.is_running = False

        if self.scheduler and APSCHEDULER_AVAILABLE:
            try:
                self.scheduler.shutdown(wait=False)
                print("[调度器-APScheduler] 已停止")
            except Exception as e:
                print(f"[调度器-APScheduler] 停止失败: {e}")

        if self.thread_timer:
            self.thread_timer = None
            print("[调度器-ThreadTimer] 已停止")

    def fetch_now(self) -> list:
        print(f"[调度器] 立即执行一次抓取 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.last_fetch_time = datetime.now()
        self.fetch_count += 1
        jobs = job_crawler.fetch_all_jobs(use_mock_fallback=True)
        if self.on_fetch_callback:
            try:
                self.on_fetch_callback(jobs)
            except Exception as e:
                print(f"[调度器] 回调执行出错: {e}")
        return jobs

    def update_interval(self, hours: int):
        if hours < 1:
            hours = 1

        config = job_crawler.load_job_config()
        config["fetch_interval_hours"] = hours
        job_crawler.save_job_config(config)

        if APSCHEDULER_AVAILABLE and self.scheduler and self.scheduler.running:
            try:
                self.scheduler.reschedule_job(
                    self.job_id,
                    trigger=IntervalTrigger(hours=hours)
                )
                print(f"[调度器-APScheduler] 已更新抓取间隔为{hours}小时")
            except Exception as e:
                print(f"[调度器-APScheduler] 更新间隔失败: {e}")
                self.stop()
                self.start()

        print(f"[调度器] 抓取间隔已更新为{hours}小时（重启后生效）")

    def set_auto_fetch(self, enabled: bool):
        config = job_crawler.load_job_config()
        config["auto_fetch_enabled"] = enabled
        job_crawler.save_job_config(config)
        print(f"[调度器] 自动抓取已{'开启' if enabled else '关闭'}")

    def get_status(self) -> dict:
        config = job_crawler.load_job_config()
        jobs = job_crawler.load_job_recruitments()

        return {
            "is_running": self.is_running,
            "using_apscheduler": APSCHEDULER_AVAILABLE,
            "auto_fetch_enabled": config.get("auto_fetch_enabled", True),
            "fetch_interval_hours": config.get("fetch_interval_hours", 6),
            "last_fetch_time": self.last_fetch_time.strftime("%Y-%m-%d %H:%M:%S") if self.last_fetch_time else config.get("last_fetch_time"),
            "fetch_count": self.fetch_count,
            "total_jobs": len(jobs),
            "new_jobs": sum(1 for j in jobs if j.get("is_new", False)),
            "scheduler_type": "APScheduler" if APSCHEDULER_AVAILABLE else "ThreadTimer"
        }


job_scheduler = JobScheduler()


def init_scheduler():
    job_crawler.init_job_data()
    job_scheduler.start()
    return job_scheduler
