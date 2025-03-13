import os
import logging
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cv_builder.settings')
django.setup()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from django.contrib.auth import get_user_model
from subscriptions.models import SubscriptionPlan
from subscriptions.iyzico_utils import create_subscription

User = get_user_model()

def test_create_subscription():
    # Get the first user
    user = User.objects.first()
    if not user:
        logger.error("No user found in the database")
        return
    
    logger.info(f"Testing with user: {user.email}")
    
    # Get the Premium plan
    try:
        plan = SubscriptionPlan.objects.get(plan_id='premium', is_active=True)
        logger.info(f"Using plan: {plan.name} (ID: {plan.plan_id})")
    except SubscriptionPlan.DoesNotExist:
        logger.error("Premium plan not found or not active")
        return
    
    # Test card token
    card_token = "test_card_token_" + str(user.id)
    
    # Try to create subscription
    try:
        subscription_ref = create_subscription(user, plan, 'monthly', card_token)
        logger.info(f"Subscription created successfully: {subscription_ref}")
    except Exception as e:
        logger.error(f"Error creating subscription: {str(e)}")

if __name__ == "__main__":
    test_create_subscription() 