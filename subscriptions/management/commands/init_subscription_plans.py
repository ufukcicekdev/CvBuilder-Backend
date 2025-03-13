from django.core.management.base import BaseCommand
from django.db import transaction
from subscriptions.models import SubscriptionPlan

class Command(BaseCommand):
    help = 'Initialize subscription plans'

    def handle(self, *args, **options):
        self.stdout.write('Initializing subscription plans...')
        
        # Define the plans
        plans = [
            {
                'plan_id': 'premium',
                'name': 'Premium',
                'description': 'All the features you need for professional CV creation',
                'price_monthly': 2,
                'price_yearly': 20,
                'plan_type': 'premium',
                'currency': 'USD',
                'features': {
                    'feature.basicCvTemplates': True,
                    'feature.videoCV': True,
                    'feature.aiAssistant': True,
                    'feature.unlimitedCvs': True,
                }
            }
        ]
        
        # Create or update the plans
        with transaction.atomic():
            for plan_data in plans:
                plan, created = SubscriptionPlan.objects.update_or_create(
                    plan_id=plan_data['plan_id'],
                    defaults={
                        'name': plan_data['name'],
                        'description': plan_data['description'],
                        'price_monthly': plan_data['price_monthly'],
                        'price_yearly': plan_data['price_yearly'],
                        'plan_type': plan_data['plan_type'],
                        'currency': plan_data['currency'],
                        'features': plan_data['features'],
                        'is_active': True
                    }
                )
                
                if created:
                    self.stdout.write(self.style.SUCCESS(f'Created plan: {plan.name}'))
                else:
                    self.stdout.write(self.style.SUCCESS(f'Updated plan: {plan.name}'))
        
        self.stdout.write(self.style.SUCCESS('Subscription plans initialized successfully')) 