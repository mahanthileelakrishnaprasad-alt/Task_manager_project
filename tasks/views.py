from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, Http404, JsonResponse
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Sum, Q
from django.contrib import messages
from datetime import date, timedelta
import os

from .models import (
    Task, UploadedFile, RoutineTask, RoutineLog, Transaction,
    TransactionCategory, UserProfile, TextNote,
)

# Aiven free-tier MySQL storage cap, in bytes. Used only to show a usage bar
# on the Users page — Aiven may change this, so treat it as an estimate.
DB_QUOTA_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB


def _is_approved(user):
    """Superusers are always approved. Users without a profile (pre-existing
    accounts created before this feature existed) are treated as approved."""
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    if profile is None:
        return True
    return profile.is_approved


def approved_required(view_func):
    """Like @login_required, but also blocks users pending admin approval,
    sending them to the waiting-room page instead."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if not _is_approved(request.user):
            return redirect('pending_approval')
        return view_func(request, *args, **kwargs)
    return wrapper


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    return render(request, 'tasks/login.html', {'form': form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(user=user, is_approved=False)
            messages.success(request, 'Registration submitted, waiting for admin approval.')
            return redirect('login')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')
    else:
        form = UserCreationForm()
    return render(request, 'tasks/register.html', {'form': form})


# ── Dashboard ─────────────────────────────────────────────────────────────────

@approved_required
def dashboard(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        note = request.POST.get('note', '').strip()
        reminder_at = request.POST.get('reminder_at', '').strip()
        if title:
            Task.objects.create(
                user=request.user, title=title, note=note,
                reminder_at=reminder_at or None,
            )
        return redirect('dashboard')

    active_tasks = Task.objects.filter(user=request.user, completed=False)
    treasure_tasks = Task.objects.filter(user=request.user, completed=True).order_by('-completed_at')
    return render(request, 'tasks/dashboard.html', {
        'active_tasks': active_tasks,
        'treasure_tasks': treasure_tasks,
    })


@login_required
def pending_approval_view(request):
    if _is_approved(request.user):
        return redirect('dashboard')
    return render(request, 'tasks/pending_approval.html')


# ── User Management (superuser only) ──────────────────────────────────────────

def superuser_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, "You don't have permission to view that page.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def _estimate_user_bytes(user):
    """Rough estimate of how much DB storage a user's data is using.
    Text/number columns are estimated by character length; uploaded file
    sizes are added from the stored `size` field. This is an approximation
    for display purposes only, not an exact MySQL storage measurement."""
    total = 0

    for t in Task.objects.filter(user=user).only('title', 'note'):
        total += len(t.title or '') + len(t.note or '') + 64  # +overhead/row

    for f in UploadedFile.objects.filter(user=user).only('name', 'size'):
        total += (f.size or 0) + len(f.name or '') + 64

    for rt in RoutineTask.objects.filter(user=user).only('title'):
        total += len(rt.title or '') + 48

    log_count = RoutineLog.objects.filter(user=user).count()
    total += log_count * 48

    for tx in Transaction.objects.filter(user=user).only('title', 'note'):
        total += len(tx.title or '') + len(tx.note or '') + 80

    for n in TextNote.objects.filter(user=user).only('heading', 'body'):
        total += len(n.heading or '') + len(n.body or '') + 64

    return total


def _format_bytes(n):
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


@superuser_required
def users_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        pk = request.POST.get('pk')
        target = get_object_or_404(User, pk=pk)

        if target.is_superuser and action in ('reject', 'deactivate'):
            messages.error(request, "You can't deactivate or reject a superuser.")
            return redirect('users')

        if action == 'approve':
            profile, _ = UserProfile.objects.get_or_create(user=target)
            profile.is_approved = True
            profile.approved_at = timezone.now()
            profile.save()
            target.is_active = True
            target.save()
            messages.success(request, f'{target.username} approved.')

        elif action == 'reject':
            username = target.username
            target.delete()
            messages.success(request, f'{username} rejected and removed.')

        elif action == 'deactivate':
            target.is_active = False
            target.save()
            messages.success(request, f'{target.username} deactivated.')

        elif action == 'activate':
            target.is_active = True
            target.save()
            # Reactivating someone also counts as (re)approving them.
            profile, _ = UserProfile.objects.get_or_create(user=target)
            if not profile.is_approved:
                profile.is_approved = True
                profile.approved_at = timezone.now()
                profile.save()
            messages.success(request, f'{target.username} reactivated.')

        return redirect('users')

    all_users = User.objects.all().order_by('-date_joined').select_related('profile')
    pending_users = [u for u in all_users if not u.is_superuser and hasattr(u, 'profile') and not u.profile.is_approved]
    approved_users = [u for u in all_users if u not in pending_users]

    usage_by_user = {}
    total_bytes = 0
    for u in all_users:
        b = _estimate_user_bytes(u)
        usage_by_user[u.pk] = {
            'bytes': b,
            'display': _format_bytes(b),
            'pct_of_quota': round((b / DB_QUOTA_BYTES) * 100, 3),
        }
        total_bytes += b

    return render(request, 'tasks/users.html', {
        'pending_users': pending_users,
        'approved_users': approved_users,
        'usage_by_user': usage_by_user,
        'total_usage_display': _format_bytes(total_bytes),
        'total_usage_pct': round((total_bytes / DB_QUOTA_BYTES) * 100, 2),
        'quota_display': _format_bytes(DB_QUOTA_BYTES),
    })


# ── Tasks ─────────────────────────────────────────────────────────────────────

@approved_required
def complete_task(request, pk):
    if request.method == 'POST':
        task = get_object_or_404(Task, pk=pk, user=request.user)
        task.completed = True
        task.completed_at = timezone.now()
        task.save()
    return redirect('dashboard')


@approved_required
def edit_task(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        note = request.POST.get('note', '').strip()
        reminder_at = request.POST.get('reminder_at', '').strip()
        if title:
            task.title = title
            task.note = note
            task.reminder_at = reminder_at or None
            task.reminder_sent = False  # any edit re-arms the reminder
            task.save()
            messages.success(request, 'Task updated.')
        return redirect('dashboard')
    return redirect('dashboard')


@approved_required
def delete_task(request, pk):
    if request.method == 'POST':
        task = get_object_or_404(Task, pk=pk, user=request.user)
        task.delete()
    return redirect('dashboard')


@approved_required
def restore_task(request, pk):
    if request.method == 'POST':
        task = get_object_or_404(Task, pk=pk, user=request.user)
        task.completed = False
        task.completed_at = None
        task.save()
    return redirect('dashboard')


@approved_required
def delete_all_treasure(request):
    if request.method == 'POST':
        Task.objects.filter(user=request.user, completed=True).delete()
    return redirect('dashboard')


# ── Files ─────────────────────────────────────────────────────────────────────

@approved_required
def files_view(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'upload')

        if action == 'upload':
            uploaded = request.FILES.get('file')
            if uploaded:
                ext = os.path.splitext(uploaded.name)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']:
                    ftype = 'image'
                elif ext == '.pdf':
                    ftype = 'pdf'
                elif ext in ['.txt', '.md', '.csv']:
                    ftype = 'text'
                else:
                    ftype = 'other'
                UploadedFile.objects.create(
                    user=request.user,
                    name=uploaded.name,
                    file=uploaded,
                    file_type=ftype,
                    size=uploaded.size,
                )

        elif action == 'add_note':
            heading = request.POST.get('heading', '').strip()
            body = request.POST.get('body', '').strip()
            if heading:
                TextNote.objects.create(user=request.user, heading=heading, body=body)

        elif action == 'edit_note':
            note_pk = request.POST.get('note_pk')
            note = get_object_or_404(TextNote, pk=note_pk, user=request.user)
            heading = request.POST.get('heading', '').strip()
            body = request.POST.get('body', '').strip()
            if heading:
                note.heading = heading
                note.body = body
                note.save()
                messages.success(request, 'Note updated.')

        elif action == 'delete_note':
            note_pk = request.POST.get('note_pk')
            note = get_object_or_404(TextNote, pk=note_pk, user=request.user)
            note.delete()

        return redirect('files')

    files = UploadedFile.objects.filter(user=request.user)
    notes = TextNote.objects.filter(user=request.user)
    return render(request, 'tasks/files.html', {'files': files, 'notes': notes})


@approved_required
def delete_file(request, pk):
    if request.method == 'POST':
        f = get_object_or_404(UploadedFile, pk=pk, user=request.user)
        # Delete from whichever storage backend is active (local disk or
        # Cloudinary) via the field's own storage API rather than assuming
        # a local filesystem path — local-disk os.path checks break once
        # DEFAULT_FILE_STORAGE points at Cloudinary.
        if f.file:
            try:
                f.file.delete(save=False)
            except Exception:
                pass
        f.delete()
    return redirect('files')


@approved_required
def download_file(request, pk):
    f = get_object_or_404(UploadedFile, pk=pk, user=request.user)
    if not f.file:
        raise Http404("File not found.")
    try:
        file_handle = f.file.open('rb')
    except Exception:
        raise Http404(
            "This file is missing from storage. If it was uploaded before "
            "Cloudinary storage was enabled, it was lost during a redeploy "
            "and needs to be re-uploaded."
        )
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=f.name,
    )


# ── Daily Routine ─────────────────────────────────────────────────────────────

def _ensure_today_logs(user):
    today = date.today()
    active_routines = RoutineTask.objects.filter(user=user, is_active=True)
    for rt in active_routines:
        RoutineLog.objects.get_or_create(routine_task=rt, date=today, defaults={'user': user})


@approved_required
def routine_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            title = request.POST.get('title', '').strip()
            reminder_time = request.POST.get('reminder_time', '').strip()
            if title:
                rt = RoutineTask.objects.create(
                    user=request.user, title=title,
                    reminder_time=reminder_time or None,
                )
                today = date.today()
                RoutineLog.objects.get_or_create(routine_task=rt, date=today, defaults={'user': request.user})

        elif action == 'edit_routine':
            pk = request.POST.get('pk')
            rt = get_object_or_404(RoutineTask, pk=pk, user=request.user)
            title = request.POST.get('title', '').strip()
            reminder_time = request.POST.get('reminder_time', '').strip()
            if title:
                rt.title = title
                rt.reminder_time = reminder_time or None
                rt.save()
                # Re-arm today's reminder so an edited time can still fire.
                RoutineLog.objects.filter(routine_task=rt, date=date.today()).update(reminder_sent=False)
                messages.success(request, 'Routine updated.')

        elif action == 'delete_routine':
            pk = request.POST.get('pk')
            rt = get_object_or_404(RoutineTask, pk=pk, user=request.user)
            rt.delete()

        elif action == 'toggle':
            log_pk = request.POST.get('log_pk')
            log = get_object_or_404(RoutineLog, pk=log_pk, user=request.user)
            log.completed = not log.completed
            log.completed_at = timezone.now() if log.completed else None
            log.save()

        elif action == 'delete_history':
            RoutineLog.objects.filter(user=request.user).exclude(date=date.today()).delete()

        return redirect('routine')

    _ensure_today_logs(request.user)

    today = date.today()
    today_logs = RoutineLog.objects.filter(user=request.user, date=today).select_related('routine_task')

    # percentages
    total_today = today_logs.count()
    done_today = today_logs.filter(completed=True).count()
    today_pct = int((done_today / total_today * 100) if total_today else 0)

    week_start = today - timedelta(days=today.weekday())
    week_logs = RoutineLog.objects.filter(user=request.user, date__gte=week_start, date__lte=today)
    total_week = week_logs.count()
    done_week = week_logs.filter(completed=True).count()
    week_pct = int((done_week / total_week * 100) if total_week else 0)

    month_start = today.replace(day=1)
    month_logs = RoutineLog.objects.filter(user=request.user, date__gte=month_start, date__lte=today)
    total_month = month_logs.count()
    done_month = month_logs.filter(completed=True).count()
    month_pct = int((done_month / total_month * 100) if total_month else 0)

    return render(request, 'tasks/routine.html', {
        'today_logs': today_logs,
        'today_pct': today_pct,
        'week_pct': week_pct,
        'month_pct': month_pct,
        'done_today': done_today,
        'total_today': total_today,
    })


# ── Transactions ──────────────────────────────────────────────────────────────

def _apply_calc(current_amount, operator, operand):
    """Apply a +-*/ operation to the current amount field. Returns the
    resulting float, or the original amount if the operand is invalid or
    would divide by zero."""
    try:
        current_amount = float(current_amount or 0)
        operand = float(operand)
    except (TypeError, ValueError):
        return current_amount
    if operator == 'add':
        return current_amount + operand
    if operator == 'sub':
        return current_amount - operand
    if operator == 'mul':
        return current_amount * operand
    if operator == 'div':
        if operand == 0:
            return current_amount
        return current_amount / operand
    return current_amount


@approved_required
def transactions_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            title = request.POST.get('title', '').strip()
            amount = request.POST.get('amount', '0').strip()
            ttype = request.POST.get('transaction_type', 'expense')
            note = request.POST.get('note', '').strip()
            category_choice = request.POST.get('category', '').strip()
            new_category_name = request.POST.get('new_category', '').strip()

            category = None
            if category_choice == '__new__' and new_category_name:
                category, _ = TransactionCategory.objects.get_or_create(
                    user=request.user, name=new_category_name
                )
            elif category_choice and category_choice != '__new__':
                category = TransactionCategory.objects.filter(
                    pk=category_choice, user=request.user
                ).first()

            try:
                amount = float(amount)
                if title and amount > 0:
                    Transaction.objects.create(
                        user=request.user, title=title,
                        amount=amount, transaction_type=ttype, note=note,
                        category=category,
                    )
            except ValueError:
                pass

        elif action == 'edit':
            pk = request.POST.get('pk')
            t = get_object_or_404(Transaction, pk=pk, user=request.user)
            title = request.POST.get('title', '').strip()
            amount = request.POST.get('amount', '0').strip()
            ttype = request.POST.get('transaction_type', 'expense')
            note = request.POST.get('note', '').strip()
            category_choice = request.POST.get('category', '').strip()
            new_category_name = request.POST.get('new_category', '').strip()

            category = None
            if category_choice == '__new__' and new_category_name:
                category, _ = TransactionCategory.objects.get_or_create(
                    user=request.user, name=new_category_name
                )
            elif category_choice and category_choice != '__new__':
                category = TransactionCategory.objects.filter(
                    pk=category_choice, user=request.user
                ).first()

            try:
                amount = float(amount)
                if title and amount > 0:
                    t.title = title
                    t.amount = amount
                    t.transaction_type = ttype
                    t.note = note
                    t.category = category
                    t.save()
                    messages.success(request, 'Transaction updated.')
            except ValueError:
                pass

        elif action == 'add_category':
            name = request.POST.get('category_name', '').strip()
            if name:
                TransactionCategory.objects.get_or_create(user=request.user, name=name)

        elif action == 'edit_category':
            cat_pk = request.POST.get('category_pk')
            cat = get_object_or_404(TransactionCategory, pk=cat_pk, user=request.user)
            new_name = request.POST.get('category_name', '').strip()
            if new_name:
                cat.name = new_name
                cat.save()
                messages.success(request, 'Category updated.')

        elif action == 'delete':
            pk = request.POST.get('pk')
            t = get_object_or_404(Transaction, pk=pk, user=request.user)
            t.delete()

        elif action == 'delete_all':
            Transaction.objects.filter(user=request.user).delete()

        elif action == 'delete_category':
            cat_pk = request.POST.get('category_pk')
            cat = get_object_or_404(TransactionCategory, pk=cat_pk, user=request.user)
            cat.delete()  # transactions in this category become Uncategorized (SET_NULL)

        elif action == 'delete_by_category':
            cat_pk = request.POST.get('category_pk')
            if cat_pk == '__none__':
                Transaction.objects.filter(user=request.user, category__isnull=True).delete()
            else:
                Transaction.objects.filter(user=request.user, category__pk=cat_pk).delete()

        return redirect('transactions')

    categories = TransactionCategory.objects.filter(user=request.user)

    # category filter (?category=<pk> or ?category=none)
    selected_category = request.GET.get('category', '').strip()
    txns = Transaction.objects.filter(user=request.user)
    if selected_category == 'none':
        txns = txns.filter(category__isnull=True)
    elif selected_category:
        txns = txns.filter(category__pk=selected_category)

    total_income = txns.filter(transaction_type='income').aggregate(s=Sum('amount'))['s'] or 0
    total_expense = txns.filter(transaction_type='expense').aggregate(s=Sum('amount'))['s'] or 0
    balance = total_income - total_expense

    return render(request, 'tasks/transactions.html', {
        'transactions': txns,
        'categories': categories,
        'selected_category': selected_category,
        'total_income': total_income,
        'total_expense': total_expense,
        'balance': balance,
    })


@approved_required
def calc_amount(request):
    """AJAX endpoint backing the +-*/ amount calculator buttons. Takes the
    current amount plus an operator and operand, returns the result so the
    form field can be updated without a page reload."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    current = request.POST.get('current', '0')
    operator = request.POST.get('operator', '')
    operand = request.POST.get('operand', '0')
    result = _apply_calc(current, operator, operand)
    return JsonResponse({'result': round(result, 2)})


# ── Profile (reminder email) ──────────────────────────────────────────────────

@approved_required
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        email = request.POST.get('reminder_email', '').strip()
        profile.reminder_email = email
        profile.save()
        messages.success(request, 'Reminder email saved.')
        return redirect('profile')
    return render(request, 'tasks/profile.html', {'profile': profile})


# ── Cron webhook (for cron-job.org free external scheduler) ──────────────────

import hmac
import hashlib
from django.views.decorators.csrf import csrf_exempt
from django.core import management
from io import StringIO

CRON_SECRET = os.environ.get('CRON_SECRET', '')


def _check_cron_secret(request):
    """Return True if the request supplies the correct cron secret.
    Accepts it either as ?key=<secret> in the query string OR as an
    X-Cron-Key header, whichever cron-job.org is configured to send."""
    secret = CRON_SECRET
    if not secret:
        return False  # No secret configured — deny all
    provided = request.GET.get('key', '') or request.headers.get('X-Cron-Key', '')
    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(provided, secret)


@csrf_exempt
def cron_send_reminders(request):
    """HTTP endpoint that runs the send_reminders management command.
    Hit this from cron-job.org (or any free scheduler) every 5 minutes.
    Protect it with CRON_SECRET env var so only your scheduler can trigger it.

    URL: /cron/send-reminders/?key=<CRON_SECRET>
    """
    if not _check_cron_secret(request):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    out = StringIO()
    err = StringIO()
    try:
        management.call_command('send_reminders', stdout=out, stderr=err)
    except Exception as e:
        return JsonResponse({'error': str(e), 'log': err.getvalue()}, status=500)

    return JsonResponse({
        'ok': True,
        'log': out.getvalue(),
        'warnings': err.getvalue(),
    })
