from django.urls import path
from . import views

urlpatterns = [
    # account status
    path('pending/', views.pending_approval_view, name='pending_approval'),
    # profile (reminder email)
    path('profile/', views.profile_view, name='profile'),
    # users (superuser only)
    path('users/', views.users_view, name='users'),
    # tasks
    path('task/complete/<int:pk>/', views.complete_task, name='complete_task'),
    path('task/edit/<int:pk>/', views.edit_task, name='edit_task'),
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
    path('transactions/calc/', views.calc_amount, name='calc_amount'),
    # Free external cron webhook (cron-job.org pings this every 5 minutes)
    path('cron/send-reminders/', views.cron_send_reminders, name='cron_send_reminders'),
    # ... existing paths ...
    path('health/', views.health_check, name='health_check'),

]

