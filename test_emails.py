import os
import django

# Django ayarlarını yükle
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cv_builder.settings')
django.setup()

from users.models import User
from scheduler.tasks import (
    send_cv_completion_reminder,
    send_trial_ending_notification,
    send_trial_ended_notification
)

def test_all_notifications():
    """
    Test all email notifications for user with id=1
    """
    try:
        # Find user with id=1
        user = User.objects.get(id=1)
        print(f"\nTest user found:")
        print(f"ID: {user.id}")
        print(f"Email: {user.email}")
        print(f"Name: {user.get_full_name() or 'Not specified'}")
        
        print("\n1. Testing CV completion reminder...")
        send_cv_completion_reminder()
        print("✓ CV completion reminder sent")
        
        print("\n2. Testing trial ending notification...")
        send_trial_ending_notification()
        print("✓ Trial ending notification sent")
        
        print("\n3. Testing trial ended notification...")
        send_trial_ended_notification()
        print("✓ Trial ended notification sent")
        
        print("\n✓ All notifications sent successfully!")
        
    except User.DoesNotExist:
        print(f"✗ Error: User with ID=1 not found!")
    except Exception as e:
        print(f"✗ Email sending failed: {str(e)}")

if __name__ == "__main__":
    test_all_notifications() 