from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from cvs.models import CV
from users.models import User
from django.db.models import Q
from users.utils import send_email_via_smtp2go
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from .models import EmailLog

User = get_user_model()

def log_email(user, email_type, success=True, error_message=None):
    EmailLog.objects.create(
        user=user,
        email_type=email_type,
        status=success,
        error_message=error_message
    )

def send_cv_completion_reminder():
    """
    Send email reminders to users whose CVs are incomplete (step < 6)
    """
    incomplete_cvs = CV.objects.filter(current_step__lt=6, user__is_active=True).select_related('user')
    
    for cv in incomplete_cvs:
        user = cv.user
        try:
            subject = 'Complete Your Professional CV Journey'
            html_message = f"""
            <html>
            <head>
                <style>
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        font-family: Arial, sans-serif;
                    }}
                    .header {{
                        background-color: #2196F3;
                        color: white;
                        padding: 30px;
                        text-align: center;
                        border-radius: 5px 5px 0 0;
                    }}
                    .content {{
                        background-color: #ffffff;
                        padding: 30px;
                        border: 1px solid #e0e0e0;
                        border-radius: 0 0 5px 5px;
                    }}
                    .progress-box {{
                        background-color: #f5f5f5;
                        padding: 20px;
                        border-radius: 5px;
                        margin: 20px 0;
                        border-left: 4px solid #2196F3;
                    }}
                    .cta-button {{
                        display: inline-block;
                        background-color: #2196F3;
                        color: white;
                        padding: 15px 30px;
                        text-decoration: none;
                        border-radius: 5px;
                        margin: 20px 0;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 30px;
                        color: #666;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Your CV Journey Awaits</h1>
                    </div>
                    <div class="content">
                        <p>Hello {user.get_full_name() or user.email},</p>
                        
                        <div class="progress-box">
                            <h3 style="margin-top: 0;">Your Progress Update</h3>
                            <p>Your CV "{cv.title}" is on its way to completion!</p>
                            <p>Current Progress: <strong>{cv.current_step}/6 steps completed</strong></p>
                            <p>Just a few more steps to create your perfect professional CV.</p>
                        </div>
                        
                        <p>A complete CV significantly increases your chances of landing your dream job. Take a few minutes to:</p>
                        <ul>
                            <li>Add your professional experience</li>
                            <li>Highlight your key skills</li>
                            <li>Showcase your achievements</li>
                        </ul>
                        
                        <center>
                            <a href="{settings.FRONTEND_URL}/dashboard" class="cta-button">
                                Continue Building Your CV
                            </a>
                        </center>
                        
                        <div class="footer">
                            <p>Best regards,<br>
                            CV Builder Team</p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            text_message = f"""
            Your CV Journey Awaits
            =====================

            Hello {user.get_full_name() or user.email},

            YOUR PROGRESS UPDATE
            -------------------
            Your CV "{cv.title}" is on its way to completion!
            Current Progress: {cv.current_step}/6 steps completed
            Just a few more steps to create your perfect professional CV.

            A complete CV significantly increases your chances of landing your dream job. Take a few minutes to:
            * Add your professional experience
            * Highlight your key skills
            * Showcase your achievements

            Continue building your CV here: {settings.FRONTEND_URL}/dashboard

            Best regards,
            CV Builder Team
            """
            
            send_email_via_smtp2go(
                to_list=user.email,
                subject=subject,
                html_body=html_message,
                text_body=text_message
            )
            log_email(user, 'cv_reminder')
        except Exception as e:
            log_email(user, 'cv_reminder', False, str(e))

def send_trial_ending_notification():
    """
    Send email notifications to users whose trial period is ending in 3 days
    """
    three_days_from_now = timezone.now() + timedelta(days=3)
    trial_users = User.objects.filter(
        Q(date_joined__lte=three_days_from_now) &
        Q(date_joined__gt=timezone.now() - timedelta(days=14)) &  # Trial period is 14 days
        Q(is_active=True)
    )
    
    for user in trial_users:
        try:
            subject = "Don't Miss Out - Your Premium Features Await"
            html_message = f"""
            <html>
            <head>
                <style>
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        font-family: Arial, sans-serif;
                    }}
                    .header {{
                        background-color: #FFA000;
                        color: white;
                        padding: 30px;
                        text-align: center;
                        border-radius: 5px 5px 0 0;
                    }}
                    .content {{
                        background-color: #ffffff;
                        padding: 30px;
                        border: 1px solid #e0e0e0;
                        border-radius: 0 0 5px 5px;
                    }}
                    .feature-box {{
                        background-color: #fff8e1;
                        padding: 20px;
                        border-radius: 5px;
                        margin: 20px 0;
                        border-left: 4px solid #FFA000;
                    }}
                    .cta-button {{
                        display: inline-block;
                        background-color: #FFA000;
                        color: white;
                        padding: 15px 30px;
                        text-decoration: none;
                        border-radius: 5px;
                        margin: 20px 0;
                    }}
                    .features-grid {{
                        display: grid;
                        grid-template-columns: repeat(2, 1fr);
                        gap: 20px;
                        margin: 20px 0;
                    }}
                    .feature-item {{
                        padding: 15px;
                        background-color: #f5f5f5;
                        border-radius: 5px;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 30px;
                        color: #666;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Unlock Premium Features</h1>
                    </div>
                    <div class="content">
                        <p>Hello {user.get_full_name() or user.email},</p>
                        
                        <div class="feature-box">
                            <h3 style="margin-top: 0;">Your Trial Period Update</h3>
                            <p>Your trial period will end in 3 days. Don't lose access to our premium features!</p>
                        </div>
                        
                        <h3>Premium Benefits Include:</h3>
                        <div class="features-grid">
                            <div class="feature-item">
                                ✨ Advanced CV Templates
                            </div>
                            <div class="feature-item">
                                📊 Analytics & Insights
                            </div>
                            <div class="feature-item">
                                🎨 Custom Branding
                            </div>
                            <div class="feature-item">
                                📱 Multi-Platform Access
                            </div>
                            <div class="feature-item">
                                🔄 Unlimited Updates
                            </div>
                            <div class="feature-item">
                                💼 Portfolio Features
                            </div>
                        </div>
                        
                        <center>
                            <a href="{settings.FRONTEND_URL}/pricing" class="cta-button">
                                Upgrade to Premium
                            </a>
                        </center>
                        
                        <div class="footer">
                            <p>Best regards,<br>
                            CV Builder Team</p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            text_message = f"""
            Unlock Premium Features
            =====================

            Hello {user.get_full_name() or user.email},

            YOUR TRIAL PERIOD UPDATE
            ----------------------
            Your trial period will end in 3 days. Don't lose access to our premium features!

            Premium Benefits Include:
            * Advanced CV Templates
            * Analytics & Insights
            * Custom Branding
            * Multi-Platform Access
            * Unlimited Updates
            * Portfolio Features

            Upgrade to Premium now: {settings.FRONTEND_URL}/pricing

            Best regards,
            CV Builder Team
            """
            
            send_email_via_smtp2go(
                to_list=user.email,
                subject=subject,
                html_body=html_message,
                text_body=text_message
            )
            log_email(user, 'trial_ending')
        except Exception as e:
            log_email(user, 'trial_ending', False, str(e))

def send_trial_ended_notification():
    """
    Send email notifications to users whose trial period has ended
    """
    trial_ended_users = User.objects.filter(
        date_joined__lte=timezone.now() - timedelta(days=14)  # Trial period is 14 days
    )
    
    for user in trial_ended_users:
        try:
            subject = 'Upgrade to Premium - Continue Your CV Journey'
            html_message = f"""
            <html>
            <head>
                <style>
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        font-family: Arial, sans-serif;
                    }}
                    .header {{
                        background: linear-gradient(135deg, #FF5722, #FF9800);
                        color: white;
                        padding: 30px;
                        text-align: center;
                        border-radius: 5px 5px 0 0;
                    }}
                    .content {{
                        background-color: #ffffff;
                        padding: 30px;
                        border: 1px solid #e0e0e0;
                        border-radius: 0 0 5px 5px;
                    }}
                    .offer-box {{
                        background-color: #ffebee;
                        padding: 20px;
                        border-radius: 5px;
                        margin: 20px 0;
                        border-left: 4px solid #FF5722;
                        text-align: center;
                    }}
                    .cta-button {{
                        display: inline-block;
                        background: linear-gradient(135deg, #FF5722, #FF9800);
                        color: white;
                        padding: 15px 30px;
                        text-decoration: none;
                        border-radius: 5px;
                        margin: 20px 0;
                        font-weight: bold;
                    }}
                    .premium-features {{
                        margin: 30px 0;
                    }}
                    .feature {{
                        display: flex;
                        align-items: center;
                        margin: 15px 0;
                        padding: 10px;
                        background-color: #f5f5f5;
                        border-radius: 5px;
                    }}
                    .feature-icon {{
                        margin-right: 15px;
                        font-size: 24px;
                    }}
                    .testimonial {{
                        font-style: italic;
                        margin: 20px 0;
                        padding: 20px;
                        background-color: #f5f5f5;
                        border-radius: 5px;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 30px;
                        color: #666;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Upgrade to Premium</h1>
                    </div>
                    <div class="content">
                        <p>Hello {user.get_full_name() or user.email},</p>
                        
                        <div class="offer-box">
                            <h2 style="color: #FF5722; margin-top: 0;">Continue Your CV Journey</h2>
                            <p style="font-size: 18px;">Your trial period has ended. Upgrade to Premium to access all features!</p>
                        </div>
                        
                        <div class="premium-features">
                            <h3>Why Choose Premium?</h3>
                            
                            <div class="feature">
                                <span class="feature-icon">🎯</span>
                                <div>
                                    <strong>Stand Out from the Crowd</strong>
                                    <p>Access exclusive premium templates designed by HR experts</p>
                                </div>
                            </div>
                            
                            <div class="feature">
                                <span class="feature-icon">🚀</span>
                                <div>
                                    <strong>Boost Your Career</strong>
                                    <p>Get insights and analytics to improve your CV's performance</p>
                                </div>
                            </div>
                            
                            <div class="feature">
                                <span class="feature-icon">🎨</span>
                                <div>
                                    <strong>Personal Branding</strong>
                                    <p>Customize colors, fonts, and layouts to match your style</p>
                                </div>
                            </div>
                        </div>
                        
                        <div class="testimonial">
                            "CV Builder helped me land my dream job at a top tech company. The premium features made my CV stand out from other applicants!"
                            <br>- Sarah M., Software Engineer
                        </div>
                        
                        <center>
                            <a href="{settings.FRONTEND_URL}/pricing" class="cta-button">
                                UPGRADE TO PREMIUM
                            </a>
                        </center>
                        
                        <div class="footer">
                            <p>Best regards,<br>
                            CV Builder Team</p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            text_message = f"""
            Upgrade to Premium - Continue Your CV Journey
            ==========================================

            Hello {user.get_full_name() or user.email},

            CONTINUE YOUR CV JOURNEY
            ----------------------
            Your trial period has ended. Upgrade to Premium to access all features!

            Why Choose Premium?

            🎯 Stand Out from the Crowd
            - Access exclusive premium templates designed by HR experts

            🚀 Boost Your Career
            - Get insights and analytics to improve your CV's performance

            🎨 Personal Branding
            - Customize colors, fonts, and layouts to match your style

            "CV Builder helped me land my dream job at a top tech company. The premium features made my CV stand out from other applicants!"
            - Sarah M., Software Engineer

            Upgrade to Premium now: {settings.FRONTEND_URL}/pricing

            Best regards,
            CV Builder Team
            """
            
            send_email_via_smtp2go(
                to_list=user.email,
                subject=subject,
                html_body=html_message,
                text_body=text_message
            )
            log_email(user, 'trial_ended')
        except Exception as e:
            log_email(user, 'trial_ended', False, str(e))
