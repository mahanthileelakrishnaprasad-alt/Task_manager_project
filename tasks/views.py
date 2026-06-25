from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, Http404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Sum, Q
from django.contrib import messages
from datetime import date, timedelta
import os

from .models import Task, UploadedFile, RoutineTask, RoutineLog, Transaction, TransactionCategory


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
            login(request, user)
            messages.success(request, f'Welcome, {user.username}!')
            return redirect('dashboard')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')
    else:
        form = UserCreationForm()
    return render(request, 'tasks/register.html', {'form': form})


# ── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        note = request.POST.get('note', '').strip()
        if title:
            Task.objects.create(user=request.user, title=title, note=note)
        return redirect('dashboard')

    active_tasks = Task.objects.filter(user=request.user, completed=False)
    treasure_tasks = Task.objects.filter(user=request.user, completed=True).order_by('-completed_at')
    return render(request, 'tasks/dashboard.html', {
        'active_tasks': active_tasks,
        'treasure_tasks': treasure_tasks,
    })


# ── Tasks ─────────────────────────────────────────────────────────────────────

@login_required
def complete_task(request, pk):
    if request.method == 'POST':
        task = get_object_or_404(Task, pk=pk, user=request.user)
        task.completed = True
        task.completed_at = timezone.now()
        task.save()
    return redirect('dashboard')


@login_required
def delete_task(request, pk):
    if request.method == 'POST':
        task = get_object_or_404(Task, pk=pk, user=request.user)
        task.delete()
    return redirect('dashboard')


@login_required
def restore_task(request, pk):
    if request.method == 'POST':
        task = get_object_or_404(Task, pk=pk, user=request.user)
        task.completed = False
        task.completed_at = None
        task.save()
    return redirect('dashboard')


@login_required
def delete_all_treasure(request):
    if request.method == 'POST':
        Task.objects.filter(user=request.user, completed=True).delete()
    return redirect('dashboard')


# ── Files ─────────────────────────────────────────────────────────────────────

@login_required
def files_view(request):
    if request.method == 'POST':
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
        return redirect('files')

    files = UploadedFile.objects.filter(user=request.user)
    return render(request, 'tasks/files.html', {'files': files})


@login_required
def delete_file(request, pk):
    if request.method == 'POST':
        f = get_object_or_404(UploadedFile, pk=pk, user=request.user)
        if f.file and os.path.exists(f.file.path):
            os.remove(f.file.path)
        f.delete()
    return redirect('files')


@login_required
def download_file(request, pk):
    f = get_object_or_404(UploadedFile, pk=pk, user=request.user)
    if not f.file or not os.path.exists(f.file.path):
        raise Http404("File not found on server.")
    return FileResponse(
        open(f.file.path, 'rb'),
        as_attachment=True,
        filename=f.name,
    )


# ── Daily Routine ─────────────────────────────────────────────────────────────

def _ensure_today_logs(user):
    today = date.today()
    active_routines = RoutineTask.objects.filter(user=user, is_active=True)
    for rt in active_routines:
        RoutineLog.objects.get_or_create(routine_task=rt, date=today, defaults={'user': user})


@login_required
def routine_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            title = request.POST.get('title', '').strip()
            if title:
                rt = RoutineTask.objects.create(user=request.user, title=title)
                today = date.today()
                RoutineLog.objects.get_or_create(routine_task=rt, date=today, defaults={'user': request.user})

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

@login_required
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

        elif action == 'add_category':
            name = request.POST.get('category_name', '').strip()
            if name:
                TransactionCategory.objects.get_or_create(user=request.user, name=name)

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
