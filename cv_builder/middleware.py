import re
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

class WebhookCsrfExemptMiddleware(MiddlewareMixin):
    """
    Middleware to exempt certain URLs from CSRF protection.
    Useful for webhook endpoints from third-party services like Paddle.
    """
    def __init__(self, get_response=None):
        self.get_response = get_response
        self.exempt_urls = []
        
        # Compile the exempt URL patterns from settings
        exempt_urls = getattr(settings, 'CSRF_EXEMPT_URLS', [])
        for pattern in exempt_urls:
            self.exempt_urls.append(re.compile(pattern))
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Check if the requested path matches any exempt URLs.
        If so, set the csrf_processing_done attribute to True.
        """
        path = request.path_info.lstrip('/')
        
        # Check if the requested path matches any exempt URLs
        for exempt_url in self.exempt_urls:
            if exempt_url.match(path):
                # Mark the request as exempt from CSRF validation
                request.csrf_processing_done = True
                print(f"CSRF exempt for path: {path}")
                break
        
        return None 