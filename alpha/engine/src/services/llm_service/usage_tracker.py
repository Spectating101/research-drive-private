# src/services/llm_service/usage_tracker.py

import json
import os
import time
from datetime import datetime, timedelta
import sqlite3
from pathlib import Path

class UsageTracker:
    """Tracks usage of various LLM services to avoid exceeding free limits"""
    
    def __init__(self, db_path=None):
        """Initialize usage tracker with optional custom database path"""
        # Set up database
        default_db_path = Path.home() / ".nocturnal_archive" / "usage_tracker.db"
        self.db_path = Path(db_path) if db_path else default_db_path
        self.db_path.parent.mkdir(exist_ok=True, parents=True)
        
        # Service limits (daily/monthly)
        self.service_limits = {
            "mistral": {"daily": 5000, "monthly": 1000000000},  # ~1 billion tokens/month
            "cerebras": {"daily": 14400, "monthly": None},  # ~14,400 requests/day
            "cohere": {"daily": None, "monthly": 1000},  # 1,000 calls/month
            "github_models": {"daily": 50, "monthly": None},  # ~50 requests/day
            "openrouter": {"daily": 50, "monthly": None}  # 50 requests/day
        }
        
        # Initialize database
        self._init_db()
    
    def _init_db(self):
        """Initialize the SQLite database for tracking usage"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Create usage tracking table if it doesn't exist
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_usage (
            service TEXT NOT NULL,
            date TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (service, date)
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def can_use(self, service):
        """Check if a service can be used based on usage limits"""
        if service not in self.service_limits:
            return False  # Unknown service
        
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")
        
        # Get daily and monthly usage
        daily_usage = self._get_usage(service, today)
        
        # Check daily limit if applicable
        daily_limit = self.service_limits[service]["daily"]
        if daily_limit and daily_usage >= daily_limit:
            return False
        
        # Check monthly limit if applicable
        monthly_limit = self.service_limits[service]["monthly"]
        if monthly_limit:
            # Sum up all days in current month
            monthly_usage = self._get_monthly_usage(service, month)
            if monthly_usage >= monthly_limit:
                return False
        
        return True
    
    def record_usage(self, service, count=1):
        """Record usage of a service"""
        if service not in self.service_limits:
            return  # Unknown service
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Update database
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Insert or update usage count
        cursor.execute('''
        INSERT INTO api_usage (service, date, count)
        VALUES (?, ?, ?)
        ON CONFLICT(service, date) DO UPDATE SET
            count = count + ?
        ''', (service, today, count, count))
        
        conn.commit()
        conn.close()
    
    def _get_usage(self, service, date):
        """Get usage count for a service on a specific date"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT count FROM api_usage
        WHERE service = ? AND date = ?
        ''', (service, date))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 0
    
    def _get_monthly_usage(self, service, month_prefix):
        """Get total usage for a service in a specific month"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT SUM(count) FROM api_usage
        WHERE service = ? AND date LIKE ?
        ''', (service, f"{month_prefix}%"))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result and result[0] is not None else 0
    
    def get_usage_summary(self):
        """Get summary of current usage across all services"""
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")
        
        summary = {}
        
        for service in self.service_limits:
            daily_usage = self._get_usage(service, today)
            monthly_usage = self._get_monthly_usage(service, month)
            
            daily_limit = self.service_limits[service]["daily"]
            monthly_limit = self.service_limits[service]["monthly"]
            
            summary[service] = {
                "daily": {
                    "usage": daily_usage,
                    "limit": daily_limit,
                    "percent": (daily_usage / daily_limit * 100) if daily_limit else None
                },
                "monthly": {
                    "usage": monthly_usage,
                    "limit": monthly_limit,
                    "percent": (monthly_usage / monthly_limit * 100) if monthly_limit else None
                }
            }
        
        return summary