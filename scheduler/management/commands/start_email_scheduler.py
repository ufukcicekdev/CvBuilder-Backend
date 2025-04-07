from django.core.management.base import BaseCommand
from scheduler.tasks import Command as SchedulerCommand

class Command(BaseCommand):
    help = 'Start the email scheduler'

    def handle(self, *args, **options):
        scheduler = SchedulerCommand()
        scheduler.handle(*args, **options) 