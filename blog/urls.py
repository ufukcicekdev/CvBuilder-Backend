from django.urls import path
# BlogPostCreateView'ı import etmeyi unutmayın!
from .views import BlogListView, BlogDetailView, BlogPostCreateView 


app_name = 'blog'

urlpatterns = [
    # Mevcut URL'leriniz
    path('create/', BlogPostCreateView.as_view(), name='blog-create'),

    path('', BlogListView.as_view(), name='blog-list'),
    path('<slug:slug>/', BlogDetailView.as_view(), name='blog-detail'),
    
    # YENİ URL: Blog gönderisi oluşturmak için kullanılacak.
]
