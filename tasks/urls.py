from django.urls import path
from . import views

urlpatterns = [
    # tasks
    path('task/complete/<int:pk>/', views.complete_task, name='complete_task'),
    path('task/delete/<int:pk>/', views.delete_task, name='delete_task'),
    path('task/restore/<int:pk>/', views.restore_task, name='restore_task'),
    path('task/delete-all-treasure/', views.delete_all_treasure, name='delete_all_treasure'),
    # files
    path('files/', views.files_view, name='files'),
    path('files/delete/<int:pk>/', views.delete_file, name='delete_file'),
    path('files/download/<int:pk>/', views.download_file, name='download_file'),
    # routine
    path('routine/', views.routine_view, name='routine'),
    # transactions
    path('transactions/', views.transactions_view, name='transactions'),
]
