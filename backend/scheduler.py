"""
每月末自动抓取最新 Visa Bulletin。
运行方式：python scheduler.py
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from scraper import scrape_latest
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

scheduler = BlockingScheduler(timezone="America/New_York")

# 每月最后一天 18:00 ET 抓取（State Dept 通常月底发布）
@scheduler.scheduled_job("cron", day="last", hour=18, minute=0)
def monthly_scrape():
    logging.info("开始每月定时抓取...")
    try:
        scrape_latest()
        logging.info("抓取成功")
    except Exception as e:
        logging.error(f"抓取失败: {e}")


if __name__ == "__main__":
    logging.info("定时任务启动，等待每月末触发...")
    scheduler.start()
