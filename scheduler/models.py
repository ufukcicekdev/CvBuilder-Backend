from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class EmailLog(models.Model):
    EMAIL_TYPES = [
        ('cv_reminder', 'CV Completion Reminder'),
        ('trial_ending', 'Trial Ending Notification'),
        ('trial_ended', 'Trial Ended Notification'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email_type = models.CharField(max_length=20, choices=EMAIL_TYPES)
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.BooleanField(default=True)  # True if sent successfully
    error_message = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['-sent_at']
        
    def __str__(self):
        return f"{self.email_type} - {self.user.email} - {self.sent_at.strftime('%Y-%m-%d %H:%M')}"
