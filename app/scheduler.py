"""Scheduled tasks for daily scraping and data updates."""
import asyncio
import threading
from datetime import datetime, time, date
from typing import Optional
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.competitor_service import competitor_service


class Scheduler:
    """Simple scheduler for daily tasks."""

    def __init__(self):
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.last_competitor_scrape: Optional[datetime] = None
        self.last_snkrdunk_fetch: Optional[datetime] = None
        self.last_stock_date_clear: Optional[datetime] = None
        self._stock_date_clear_date: Optional[date] = None  # track date to avoid double-runs
    
    def start(self):
        """Start the scheduler in a background thread."""
        if self.is_running:
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("[OK] Scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("[OK] Scheduler stopped")
    
    def _run(self):
        """Main scheduler loop."""
        while self.is_running:
            try:
                now = datetime.now()
                today = now.date()

                # 00:01 — clear expired stock dates
                if now.hour == 0 and now.minute == 1 and self._stock_date_clear_date != today:
                    self._run_stock_date_clear()
                    self._stock_date_clear_date = today

                # 02:00 — competitor scrape + other daily tasks
                if now.hour == 2 and now.minute < 5:
                    self._run_daily_tasks()
                    # Sleep for 1 hour to avoid running multiple times
                    threading.Event().wait(3600)
                else:
                    # Check every minute so we don't miss the 00:01 window
                    threading.Event().wait(60)
            except Exception as e:
                print(f"Scheduler error: {e}")
                threading.Event().wait(60)
    
    def _run_stock_date_clear(self):
        """Clear expired stock_date metafields on Shopify (runs at 00:01)."""
        print(f"[{datetime.now()}] Clearing expired stock dates...")
        try:
            from app.routers.stock_dates import clear_expired_stock_dates
            import asyncio
            result = asyncio.run(clear_expired_stock_dates())
            self.last_stock_date_clear = datetime.now()
            print(f"[OK] Stock date clear: {result['cleared_count']} cleared, {len(result['errors'])} errors")
        except Exception as e:
            print(f"[ERROR] Stock date clear failed: {e}")

    def _run_daily_tasks(self):
        """Run all daily tasks."""
        print(f"[{datetime.now()}] Running daily tasks...")
        try:
            # Get database session
            db = next(get_db())
            
            # Scrape competitor data
            try:
                result = competitor_service.scrape_all_competitors(db)
                self.last_competitor_scrape = datetime.now()
                print(f"[OK] Competitor scrape completed: {result}")
            except Exception as e:
                print(f"[ERROR] Competitor scrape failed: {e}")
            finally:
                db.close()
            
        except Exception as e:
            print(f"Daily tasks error: {e}")
    
    def trigger_competitor_scrape(self) -> dict:
        """Trigger competitor scraping immediately."""
        try:
            db = next(get_db())
            result = competitor_service.scrape_all_competitors(db)
            self.last_competitor_scrape = datetime.now()
            db.close()
            return {
                "status": "success",
                "message": "Competitor scraping started",
                "last_run": self.last_competitor_scrape.isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "last_run": self.last_competitor_scrape.isoformat() if self.last_competitor_scrape else None
            }
    
    def get_status(self) -> dict:
        """Get scheduler status."""
        return {
            "is_running": self.is_running,
            "last_competitor_scrape": self.last_competitor_scrape.isoformat() if self.last_competitor_scrape else None,
            "last_snkrdunk_fetch": self.last_snkrdunk_fetch.isoformat() if self.last_snkrdunk_fetch else None,
            "last_stock_date_clear": self.last_stock_date_clear.isoformat() if self.last_stock_date_clear else None,
        }


# Global scheduler instance
scheduler = Scheduler()
