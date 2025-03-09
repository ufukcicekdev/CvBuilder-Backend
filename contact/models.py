from django.db import models
from django.utils.translation import gettext_lazy as _

class Contact(models.Model):
    STATUS_CHOICES = [
        ('new', _('New')),
        ('in_progress', _('In Progress')),
        ('resolved', _('Resolved')),
        ('closed', _('Closed')),
    ]

    SUBJECT_CHOICES = [
        ('general', _('General Inquiry')),
        ('technical', _('Technical Support')),
        ('billing', _('Billing Question')),
        ('feedback', _('Feedback')),
        ('other', _('Other')),
    ]

    name = models.CharField(_('Name'), max_length=100)
    email = models.EmailField(_('Email'))
    subject = models.CharField(_('Subject'), max_length=20, choices=SUBJECT_CHOICES)
    message = models.TextField(_('Message'))
    status = models.CharField(_('Status'), max_length=20, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    admin_notes = models.TextField(_('Admin Notes'), blank=True, null=True)
    ip_address = models.GenericIPAddressField(_('IP Address'), blank=True, null=True)
    user_agent = models.TextField(_('User Agent'), blank=True, null=True)

    class Meta:
        verbose_name = _('Contact Message')
        verbose_name_plural = _('Contact Messages')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.subject} ({self.created_at.strftime('%Y-%m-%d')})" 