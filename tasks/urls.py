from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('complete/<int:pk>/', views.complete_task, name='complete_task'),
    path('delete/<int:pk>/', views.delete_task, name='delete_task'),
    path('restore/<int:pk>/', views.restore_task, name='restore_task'),
]
