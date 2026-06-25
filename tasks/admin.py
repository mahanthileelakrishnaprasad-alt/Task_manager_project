from django.contrib import admin
from .models import (
    Task, UploadedFile, RoutineTask, RoutineLog, Transaction,
    TransactionCategory, UserProfile, TextNote,
)

admin.site.register(Task)
admin.site.register(UploadedFile)
admin.site.register(RoutineTask)
admin.site.register(RoutineLog)
admin.site.register(Transaction)
admin.site.register(TransactionCategory)
admin.site.register(UserProfile)
admin.site.register(TextNote)
