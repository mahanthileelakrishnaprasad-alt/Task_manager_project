"""
Sends due email reminders for one-off Tasks and recurring daily RoutineTasks.

Intended to be run on a schedule (e.g. a Render Cron Job hitting this command
every 5 minutes), since Render's free web service does not run background
jobs on its own. Safe to run as often as you like — already-sent reminders
are skipped via the `reminder_sent` flag.

Usage:
    python manage.py send_reminders
"""
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import datetime, date

from tasks.models import Task, RoutineTask, RoutineLog, UserProfile


class Command(BaseCommand):
    help = "Send due email reminders for tasks and daily routines."

    def handle(self, *args, **options):
        if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
            self.stdout.write(self.style.WARNING(
                "EMAIL_HOST_USER / EMAIL_HOST_PASSWORD not configured — skipping. "
                "Set these env vars (a Gmail address + App Password) to enable reminders."
            ))
            return

        now = timezone.now()
        sent_count = 0

        # ── One-off task reminders ───────────────────────────────────────
        due_tasks = Task.objects.filter(
            completed=False,
            reminder_sent=False,
            reminder_at__isnull=False,
            reminder_at__lte=now,
        ).select_related('user')

        for task in due_tasks:
            email = self._email_for(task.user)
            if not email:
                # No reminder email on file for this user — mark sent so we
                # don't retry forever, but skip actually sending.
                task.reminder_sent = True
                task.save(update_fields=['reminder_sent'])
                continue
            try:
                send_mail(
                    subject=f"⏰ Reminder: {task.title}",
                    message=self._task_body(task),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                task.reminder_sent = True
                task.save(update_fields=['reminder_sent'])
                sent_count += 1
                self.stdout.write(f"Sent task reminder: '{task.title}' -> {email}")
            except Exception as e:
                self.stderr.write(f"Failed to send task reminder {task.pk}: {e}")

        # ── Daily routine reminders ──────────────────────────────────────
        today = date.today()
        current_time = now.time()

        due_routines = RoutineTask.objects.filter(
            is_active=True,
            reminder_time__isnull=False,
            reminder_time__lte=current_time,
        ).select_related('user')

        for routine in due_routines:
            log, _ = RoutineLog.objects.get_or_create(
                routine_task=routine, date=today, defaults={'user': routine.user}
            )
            if log.completed or log.reminder_sent:
                continue
            email = self._email_for(routine.user)
            if not email:
                log.reminder_sent = True
                log.save(update_fields=['reminder_sent'])
                continue
            try:
                send_mail(
                    subject=f"⏰ Daily routine reminder: {routine.title}",
                    message=self._routine_body(routine),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                log.reminder_sent = True
                log.save(update_fields=['reminder_sent'])
                sent_count += 1
                self.stdout.write(f"Sent routine reminder: '{routine.title}' -> {email}")
            except Exception as e:
                self.stderr.write(f"Failed to send routine reminder {routine.pk}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Done. {sent_count} reminder(s) sent."))

    def _email_for(self, user):
        profile = getattr(user, 'profile', None)
        if profile and profile.reminder_email:
            return profile.reminder_email
        return ''

    def _task_body(self, task):
        body = f'Your task "{task.title}" is due now.'
        if task.note:
            body += f"\n\nNote: {task.note}"
        body += "\n\n— PersonalHub"
        return body

    def _routine_body(self, routine):
        return (
            f'Time for your daily routine: "{routine.title}".\n\n'
            f"Open PersonalHub to tick it off once you've done it.\n\n— PersonalHub"
        )
