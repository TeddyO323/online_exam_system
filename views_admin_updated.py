import logging
from datetime import datetime
import random

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q, Count, F, Sum
from django.forms import modelformset_factory, inlineformset_factory
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.timezone import make_aware
from core.decorators import role_required


from .forms import ExamForm, QuestionForm, OptionForm, MatchingPairForm
from adminpanel.models import Exam
from core.models import (
    Question, Option, MatchingPair, TrueFalseAnswer, Subject, CustomUser
)
from examinerpanel.models import Examination
from studentpanel.models import ExamEnrollment  # if not already imported

# import examenrollents

# Admin panel views for exam portal
@role_required('ADMIN')
def admin_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None and user.role == 'ADMIN':
            login(request, user)
            return redirect('admin_dashboard')
        else:
            context = {'error': 'Invalid credentials or not an admin.'}
            return render(request, 'adminpanel/login.html', context)

    return render(request, 'adminpanel/login.html')


@login_required
def create_exam(request):
    # ✅ Check if the user is actually an admin
    if not hasattr(request.user, 'role') or request.user.role != 'ADMIN':
        messages.error(request, "Only admins can create exams.")
        return redirect('home')  # or any fallback route for non-admins

    if request.method == 'POST':
        form = ExamForm(request.POST)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.admin = request.user
            if not hasattr(exam, 'total_marks') or exam.total_marks is None:
                exam.total_marks = 0
            exam.save()
            messages.success(request, "Exam created successfully.")
            return redirect('admin_exams')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ExamForm()
    
    print("Exam creator:", request.user.username, request.user.role)

    return render(request, 'exams/new.html', {'form': form})
from django.db.models import Count, Q

@role_required('ADMIN')
def exams_index(request):
    today = timezone.localdate()

    all_exams = Exam.objects.annotate(
        approved_enrollments=Count('enrollments', filter=Q(enrollments__status='enrolled'), distinct=True),
        pending_enrollments=Count('enrollments', filter=Q(enrollments__status='pending'), distinct=True)
    ).order_by('-exam_date')

    paginator = Paginator(all_exams, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    scheduled_exams = all_exams.filter(expiry_date__gte=today)
    completed_exams = all_exams.filter(expiry_date__lt=today)

    context = {
        'page_obj': page_obj,
        'all_exams_count': all_exams.count(),
        'scheduled_exams': scheduled_exams,
        'completed_exams': completed_exams,
    }
    return render(request, 'exams/index.html', context)

# Admin panel dashboard view
@login_required
def admin_dashboard(request):
    return render(request, 'dashboard/index.html')


@role_required('ADMIN')
def admin_logout(request):
    logout(request)
    return redirect('login')
# Admin panel views for exams, questions, and students

# Admin panel view to create a new exam
@role_required('ADMIN')
def exams_create(request):
    return render(request, 'exams/new.html')

# Admin panel views for questions and students

@role_required('ADMIN')
def questions(request):
    type_filter = request.GET.get('type')
    subject_filter = request.GET.get('subject')

    # Always get sorting params
    sort = request.GET.get('sort', 'created')
    order = request.GET.get('order', 'desc')

    # Default sort field map
    sort_map = {
        'question': 'text',
        'type': 'question_type',
        'subject': 'subject__name',
        'marks': 'marks',
        'created': 'created_at',
    }

    sort_field = sort_map.get(sort, 'created_at')
    if order == 'desc':
        sort_field = f'-{sort_field}'

    queryset = Question.objects.select_related('subject').order_by(sort_field)

    if type_filter:
        queryset = queryset.filter(question_type=type_filter)
    if subject_filter:
        queryset = queryset.filter(subject__id=subject_filter)

    paginator = Paginator(queryset, 7)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    question_counts = Question.objects.values('question_type').annotate(count=Count('id'))
    stats = {
        'total': Question.objects.count(),
        'MCQ': 0,
        'TRUE_FALSE': 0,
        'ESSAY': 0,
        'MATCHING': 0,
    }
    for entry in question_counts:
        if entry['question_type'] in stats:
            stats[entry['question_type']] = entry['count']

    return render(request, 'questions/index.html', {
        'stats': stats,
        'page_obj': page_obj,
        'questions': page_obj.object_list,
        'subjects': Subject.objects.all(),
        'sort': sort,
        'order': order,
        'type_filter': type_filter,
        'subject_filter': subject_filter,
    })


# Admin panel view to create a new question


@role_required('ADMIN')
def questions_create(request):
    exams = Exam.objects.all()
    subjects = Subject.objects.all()

    if request.method == 'POST':
        try:
            # Extract form data
            question_type = request.POST.get('question_type')
            text = request.POST.get('text')
            marks = request.POST.get('marks')
            image = request.FILES.get('image')
            exam_id = request.POST.get('exam_id') or None

            # Determine subject: from exam if selected, else from subject dropdown
            subject_id = None
            subject = None

            if exam_id:
                try:
                    exam = Exam.objects.get(id=int(exam_id))
                    subject = exam.subject
                except (Exam.DoesNotExist, ValueError, TypeError):
                    subject = None
            else:
                subject_id = request.POST.get('subject')
                if subject_id:
                    try:
                        subject = Subject.objects.get(id=int(subject_id))
                    except (Subject.DoesNotExist, ValueError, TypeError):
                        subject = None

            # Basic validation
            missing_fields = []
            if not question_type:
                missing_fields.append("Question Type")
            if not text:
                missing_fields.append("Question Text")
            if not marks:
                missing_fields.append("Marks")
            if not subject:
                missing_fields.append("Subject")

            if missing_fields:
                messages.error(request, f"Missing required fields: {', '.join(missing_fields)}")
                return render(request, 'questions/new.html', {
                    'subjects': subjects,
                    'exams': exams,
                    'form_data': request.POST,
                })

            # Save the main Question
            question = Question.objects.create(
                question_type=question_type,
                text=text,
                subject=subject,
                marks=marks,
                image=image,
                exam_id=exam_id
            )

            # Save related data based on question type
            if question_type == 'MCQ':
                for i in range(1, 6):
                    option_text = request.POST.get(f'option_{i}')
                    is_correct = request.POST.get(f'is_correct_{i}') == 'on'
                    if option_text:
                        Option.objects.create(
                            question=question,
                            text=option_text,
                            is_correct=is_correct
                        )

            elif question_type == 'TRUE_FALSE':
                is_true_value = request.POST.get('true_false_answer')  # e.g. from radio input
                if is_true_value in ['True', 'False']:
                    TrueFalseAnswer.objects.create(
                        question=question,
                        is_true=(is_true_value == 'True')
        )
                else:
                    messages.error(request, "Please select a valid True/False answer.")
                    return render(request, 'questions/new.html', {
                        'subjects': subjects,
                        'exams': exams,
                        'form_data': request.POST,
                    })

            elif question_type == 'MATCHING':
                for i in range(1, 6):
                    left = request.POST.get(f'left_{i}')
                    right = request.POST.get(f'right_{i}')
                    if left and right:
                        MatchingPair.objects.create(
                            question=question,
                            left_text=left,
                            right_text=right
                        )

            # No extra logic needed for essay questions currently

            messages.success(request, "Question created successfully.")
            return redirect('admin_questions')

        except Exception as e:
            import traceback
            traceback.print_exc()
            messages.error(request, f"Something went wrong: {str(e)}")
            return redirect('questions_create')

    return render(request, 'questions/new.html', {
        'subjects': subjects,
        'exams': exams
    })


@role_required('ADMIN')
def edit_question(request, pk):
    question = get_object_or_404(Question, pk=pk)

    OptionFormSet = inlineformset_factory(
        Question,
        Option,
        form=OptionForm,
        fields=('text', 'is_correct'),
        extra=1,
        can_delete=True
    )

    MatchingPairFormSet = inlineformset_factory(
        Question,
        MatchingPair,
        form=MatchingPairForm,
        fields=('left_text', 'right_text'),
        extra=1,
        can_delete=True
    )

    if request.method == 'POST':
        form = QuestionForm(request.POST, request.FILES, instance=question)
        formset = OptionFormSet(request.POST, instance=question)
        pair_formset = MatchingPairFormSet(request.POST, instance=question)

        if form.is_valid():
            form.save()

            question_type = form.cleaned_data['question_type']

            if question_type == 'MCQ':
                if formset.is_valid():
                    formset.save()
                    messages.success(request, "MCQ question updated successfully.")
                    return redirect('admin_questions')
                else:
                    messages.error(request, "Please correct the MCQ options errors.")

            elif question_type == 'MATCHING':
                if pair_formset.is_valid():
                    pair_formset.save()
                    messages.success(request, "Matching question updated successfully.")
                    return redirect('admin_questions')
                else:
                    messages.error(request, "Please correct the matching pairs errors.")

            elif question_type == 'TRUE_FALSE':
                # Save any TRUE_FALSE-specific logic here if needed
                messages.success(request, "True/False question updated successfully.")
                return redirect('admin_questions')

            elif question_type == 'ESSAY':
                # No extra formsets needed for essay questions
                messages.success(request, "Essay question updated successfully.")
                return redirect('admin_questions')

            else:
                messages.warning(request, "Unsupported question type.")

        else:
            messages.error(request, "Please correct the form errors.")
    else:
        form = QuestionForm(instance=question)
        formset = OptionFormSet(instance=question)
        pair_formset = MatchingPairFormSet(instance=question)

    return render(request, 'questions/edit.html', {
        'form': form,
        'formset': formset,
        'pair_formset': pair_formset,
        'question': question,
    })

@role_required('ADMIN')
def delete_question(request, pk):
    question = get_object_or_404(Question, pk=pk)
    if request.method == 'POST':
        question.delete()
        return redirect('admin_questions')
    return render(request, 'questions/delete_confirm.html', {'question': question})

# Admin panel view for students
@role_required('ADMIN')
def users(request):
    role = request.GET.get('role')
    status = request.GET.get('status')
    search_query = request.GET.get('search')

    users_qs = CustomUser.objects.all().order_by('-date_joined')

    if role:
        users_qs = users_qs.filter(role__iexact=role.upper())
    if status == 'active':
        users_qs = users_qs.filter(is_active=True)
    elif status == 'suspended':
        users_qs = users_qs.filter(is_active=False)
    if search_query:
        users_qs = users_qs.filter(
            Q(full_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(username__icontains=search_query)
        )

    paginator = Paginator(users_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'selected_role': role,
        'selected_status': status,
        'search_query': search_query,
    }

    # 👇 Detect AJAX and return only partial
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        html = render_to_string('users/_user_table.html', context, request=request)
        return HttpResponse(html)

    # Regular full page render
    return render(request, 'users/index.html', context)

# Admin panel view to view student
@role_required('ADMIN')
def view_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)

    if user.role == 'STUDENT':
        template_name = 'users/view_student.html'
    elif user.role == 'EXAMINER':
        template_name = 'users/view_examiner.html'
    elif user.role == 'ADMIN':
        template_name = 'users/view_admin.html'
    else:
        template_name = 'users/view_generic.html'  # Fallback

    context = {'user': user}
    return render(request, template_name, context)

# Admin panel view to suspend a user
@role_required('ADMIN')
def suspend_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    if request.method == 'POST':
        user.is_active = False
        user.save()
        messages.success(request, f"{user.username} has been suspended successfully.")
        return redirect('admin_users')
    
    return render(request, 'users/suspend_confirm.html', {'user': user})

@role_required('ADMIN')
def unsuspend_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    if request.method == 'POST':
        user.is_active = True
        user.save()
        messages.success(request, f"{user.username} has been reactivated.")
        return redirect('admin_users')
    return render(request, 'users/unsuspend_confirm.html', {'user': user})

# Admin panel view to delete a user
@role_required('ADMIN')
def delete_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    if request.method == 'POST':
        user.delete()
        messages.success(request, f"{user.username} has been deleted successfully.")
        return redirect('admin_users')
    
    return render(request, 'users/delete_confirm.html', {'user': user})


# Admin panel analytics view
@role_required('ADMIN')
def analytics(request):
    return render(request, 'analytics/index.html')

# Admin panel settings view
@role_required('ADMIN')
def admin_settings(request):
    return render(request, 'settings/index.html')




@role_required('ADMIN')
def view_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    OptionFormSet = modelformset_factory(Option, form=OptionForm, extra=2, min_num=2, validate_min=True)
    prefix = 'option'

    if request.method == 'POST':
        question_form = QuestionForm(request.POST, request.FILES)
        option_formset = OptionFormSet(request.POST, queryset=Option.objects.none(), prefix=prefix)

        if question_form.is_valid():
            question = question_form.save(commit=False)
            question.exam = exam
            question.subject = exam.subject
            question_type = question.question_type

            # ✅ MCQ
            if question_type == 'MCQ':
                correct_option_index = request.POST.get('correct-option')
                if not correct_option_index:
                    messages.error(request, "Please select the correct option.")
                    return redirect('view_exam', exam_id=exam.id)

                if option_formset.is_valid():
                    question.save()
                    for i, form in enumerate(option_formset.forms):
                        option = form.save(commit=False)
                        option.question = question
                        option.is_correct = (str(i) == correct_option_index)
                        option.save()
                    messages.success(request, "MCQ question and options added successfully.")
                else:
                    messages.error(request, "Please provide at least 2 valid options for the MCQ.")
                    return redirect('view_exam', exam_id=exam.id)

            # ✅ TRUE/FALSE
            elif question_type == 'TRUE_FALSE':
                correct_option_index = request.POST.get('correct-option')
                if correct_option_index not in ['0', '1']:
                    messages.error(request, "Please select either True or False as the correct answer.")
                    return redirect('view_exam', exam_id=exam.id)

                question.save()
                TrueFalseAnswer.objects.create(
                    question=question,
                    is_true=(correct_option_index == '0')
                )
                messages.success(request, "True/False question added successfully.")

            # ✅ MATCHING
            elif question_type == 'MATCHING':
                left_items = request.POST.getlist('match-left[]')
                right_items = request.POST.getlist('match-right[]')

                if len(left_items) >= 2 and len(left_items) == len(right_items):
                    question.save()
                    for left, right in zip(left_items, right_items):
                        MatchingPair.objects.create(
                            question=question,
                            left_text=left.strip(),
                            right_text=right.strip()
                        )
                    messages.success(request, "Matching question added successfully.")
                else:
                    messages.error(request, "Please provide at least 2 valid matching pairs.")
                    return redirect('view_exam', exam_id=exam.id)

            # ✅ ESSAY or other types
            else:
                question.save()
                messages.success(request, "Question added successfully.")

            return redirect('view_exam', exam_id=exam.id)

        else:
            messages.error(request, f"There were errors in the form: {question_form.errors.as_text()}")

    else:
        question_form = QuestionForm()
        option_formset = OptionFormSet(queryset=Option.objects.none(), prefix=prefix)

    questions = Question.objects.filter(exam=exam)
    exam_datetime = datetime.combine(exam.exam_date, exam.start_time).isoformat()
    total_marks = questions.aggregate(Sum('marks'))['marks__sum'] or 0
    enrollments = ExamEnrollment.objects.select_related('student').filter(exam=exam).order_by('-enrolled_at')
    for enrollment in enrollments:
        enrollment.is_active = enrollment.status == 'enrolled'
        enrollment.student.full_name = f"{enrollment.student.first_name} {enrollment.student.last_name}"

    context = {
        'exam': exam,
        'question_form': question_form,
        'option_formset': option_formset,
        'questions': questions,
        'exam_datetime': exam_datetime,
        'total_marks': total_marks,
        'enrollments': enrollments,
    }

    return render(request, 'exams/view.html', context)

from django.views.decorators.http import require_POST
from studentpanel.models import ExamEnrollment

@require_POST
def approve_enrollment(request, enrollment_id):
    enrollment = get_object_or_404(ExamEnrollment, id=enrollment_id)
    if enrollment.status == 'pending':
        enrollment.status = 'enrolled'
        enrollment.save()
        messages.success(request, f"{enrollment.student.username} has been approved for {enrollment.exam.exam_name}.")
    else:
        messages.warning(request, "This enrollment is not pending.")

    return redirect('view_exam', exam_id=enrollment.exam.id)


@require_POST
def reject_enrollment(request, enrollment_id):
    enrollment = get_object_or_404(ExamEnrollment, id=enrollment_id)
    if enrollment.status == 'pending':
        enrollment.status = 'rejected'
        enrollment.save()
        messages.success(request, f"{enrollment.student.username} has been rejected from {enrollment.exam.exam_name}.")
    else:
        messages.warning(request, "This enrollment is not pending.")

    return redirect('view_exam', exam_id=enrollment.exam.id)


@role_required('ADMIN')
def edit_exam(request, exam_id):
    exam = Exam.objects.get(id=exam_id)
    if request.method == 'POST':
        form = ExamForm(request.POST, instance=exam)
        if form.is_valid():
            form.save()
            messages.success(request, "Exam updated successfully.")
            return redirect('admin_exams')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ExamForm(instance=exam)
    return render(request, 'exams/edit.html', {'form': form, 'exam': exam})

@role_required('ADMIN')
def clone_exam(request, exam_id):
    exam = Exam.objects.get(id=exam_id)
    if request.method == 'POST':
        form = ExamForm(request.POST)
        if form.is_valid():
            new_exam = form.save(commit=False)
            new_exam.admin = request.user
            new_exam.save()
            messages.success(request, "Exam cloned successfully.")
            return redirect('admin_exams')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ExamForm(instance=exam)
    return render(request, 'exams/clone.html', {'form': form, 'exam': exam})

@role_required('ADMIN')
def delete_exam(request, exam_id):
    exam = Exam.objects.get(id=exam_id)
    if request.method == 'POST':
        exam.delete()
        messages.success(request, "Exam deleted successfully.")
        return redirect('admin_exams')
    return render(request, 'exams/delete.html', {'exam': exam})



@role_required('ADMIN')
def exam_detail(request, exam_id):
    exam = Exam.objects.get(id=exam_id)

    # Combine exam_date and start_time into one datetime object
    start_datetime = datetime.combine(exam.exam_date, exam.start_time)

    # Make timezone-aware (recommended if USE_TZ = True in settings)
    start_datetime = make_aware(start_datetime)

    # Convert to UNIX timestamp in milliseconds
    start_timestamp = int(start_datetime.timestamp() * 1000)

    return render(request, 'exam_detail.html', {
        'exam': exam,
        'start_timestamp': start_timestamp,
    })


from core.models import CustomUser



