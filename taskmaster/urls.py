from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.contrib.auth import views as auth_views
from tasks import views as task_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', task_views.dashboard, name='dashboard'),
    path('login/', task_views.login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register/', task_views.register_view, name='register'),
    path('', include('tasks.urls')),
]

# Serve uploaded media files (images/pdfs/etc the user uploads).
# NOTE: this works for local dev AND for quick testing on Render's free tier,
# but on Render the disk is ephemeral — files vanish on every redeploy/restart.
# For permanent storage on Render, use a Persistent Disk or S3-compatible storage.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
