"""
Sends due email reminders for one-off Tasks and recurring daily RoutineTasks.
Uses Resend API (HTTPS) instead of SMTP — works on Render's free tier which
blocks outbound SMTP (port 587).

Usage:
    python manage.py send_reminders
"""
import urllib.request
import urllib.error
import json
import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date

from tasks.models import Task, RoutineTask, RoutineLog, UserProfile

RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
FROM_EMAIL = 'PersonalHub <onboarding@resend.dev>'


def _send_via_resend(to_email, subject, body):
    """Send an email via Resend API over HTTPS. Raises on failure."""
    payload = json.dumps({
        'from': FROM_EMAIL,
        'to': [to_email],
        'subject': subject,
        'text': body,
    }).encode('utf-8')

    req = urllib.request.Request(
        'https://api.resend.com/emails',
        data=payload,
        headers={
            'Authorization': f'Bearer {RESEND_API_KEY}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


class Command(BaseCommand):
    help = "Send due email reminders for tasks and daily routines via Resend API."

    def handle(self, *args, **options):
        if not RESEND_API_KEY:
            self.stdout.write(self.style.WARNING(
                "RESEND_API_KEY not configured — skipping. "
                "Set this env var on Render to enable reminders."
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
                task.reminder_sent = True
                task.save(update_fields=['reminder_sent'])
                continue
            try:
                _send_via_resend(
                    to_email=email,
                    subject=f"⏰ Reminder: {task.title}",
                    body=self._task_body(task),
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
                _send_via_resend(
                    to_email=email,
                    subject=f"⏰ Daily routine reminder: {routine.title}",
                    body=self._routine_body(routine),
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
