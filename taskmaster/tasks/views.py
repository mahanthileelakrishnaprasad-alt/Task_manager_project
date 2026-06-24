from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .models import Task


def home(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        note = request.POST.get('note', '').strip()
        if title:
            Task.objects.create(title=title, note=note)
        return redirect('home')

    active_tasks = Task.objects.filter(completed=False)
    treasure_tasks = Task.objects.filter(completed=True).order_by('-completed_at')
    return render(request, 'tasks/home.html', {
        'active_tasks': active_tasks,
        'treasure_tasks': treasure_tasks,
    })


def complete_task(request, pk):
    if request.method == 'POST':
        task = get_object_or_404(Task, pk=pk)
        task.completed = True
        task.completed_at = timezone.now()
        task.save()
    return redirect('home')


def delete_task(request, pk):
    if request.method == 'POST':
        task = get_object_or_404(Task, pk=pk)
        task.delete()
    return redirect('home')


def restore_task(request, pk):
    if request.method == 'POST':
        task = get_object_or_404(Task, pk=pk)
        task.completed = False
        task.completed_at = None
        task.save()
    return redirect('home')
