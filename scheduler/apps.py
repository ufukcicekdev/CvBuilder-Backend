from django.apps import AppConfig
from django.conf import settings
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import sys


class SchedulerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "scheduler"

    def ready(self):
        # Prevent scheduler from running twice in development
        if settings.DEBUG and (len(sys.argv) > 1 and sys.argv[1] == 'runserver'):
            return
            
        from scheduler.tasks import (
            send_cv_completion_reminder,
            send_trial_ending_notification,
            send_trial_ended_notification
        )
        
        scheduler = BackgroundScheduler()
        
        # CV completion reminder - runs every 2 days at 10:00 AM
        scheduler.add_job(
            send_cv_completion_reminder,
            trigger=CronTrigger(
                day_of_week='0,2,4,6',  # Run on Sun, Tue, Thu, Sat
                hour=10,
                minute=0
            ),
            id="cv_completion_reminder",
            max_instances=1,
            replace_existing=True,
        )
        
        # Trial ending notification - runs every 2 days at 11:00 AM
        scheduler.add_job(
            send_trial_ending_notification,
            trigger=CronTrigger(
                day_of_week='0,2,4,6',  # Run on Sun, Tue, Thu, Sat
                hour=11,
                minute=0
            ),
            id="trial_ending_notification",
            max_instances=1,
            replace_existing=True,
        )
        
        # Trial ended notification - runs every 2 days at 12:00 PM
        scheduler.add_job(
            send_trial_ended_notification,
            trigger=CronTrigger(
                day_of_week='0,2,4,6',  # Run on Sun, Tue, Thu, Sat
                hour=12,
                minute=0
            ),
            id="trial_ended_notification",
            max_instances=1,
            replace_existing=True,
        )
        
        try:
            scheduler.start()
        except Exception as e:
            print(f"Scheduler error: {e}")

