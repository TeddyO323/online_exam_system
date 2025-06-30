from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from examinerpanel.models import Examination
from django.shortcuts import render, get_object_or_404, redirect
from core.models import Subject, CustomUser  # ← correct Subject model
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
from core.models import Question, Option, MatchingPair, TrueFalseAnswer
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db import transaction, models
from core.decorators import role_required
from django.db.models import Count, Q

@role_required('EXAMINER')
def examiner_login(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)

        if user is not None and user.role == 'EXAMINER':
            login(request, user)
            return redirect('examiner_dashboard')
        else:
            messages.error(request, "Invalid credentials or not an examiner.")
    return render(request, 'examinerpanel/login.html')

@role_required('EXAMINER')
def examiner_questions(request):
    questions = Question.objects.select_related('subject', 'created_by').order_by('-created_at')

    # Apply filters
    subject_id = request.GET.get('subject')
    qtype = request.GET.get('qtype')
    created_by_me = request.GET.get('mine') == '1'

    if subject_id:
        questions = questions.filter(subject_id=subject_id)

    if qtype:
        questions = questions.filter(question_type=qtype)

    if created_by_me:
        questions = questions.filter(created_by=request.user)

    # Stats
    stats = Question.objects.aggregate(
        total=Count('id'),
        mcq=Count('id', filter=Q(question_type='MCQ')),
        tf=Count('id', filter=Q(question_type='TRUE_FALSE')),
        essay=Count('id', filter=Q(question_type='ESSAY')),
    )

    # Pagination
    paginator = Paginator(questions, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    subjects = Subject.objects.all()

    return render(request, 'examinerpanel/questions/index.html', {
        'questions': page_obj,
        'page_obj': page_obj,
        'stats': stats,
        'subjects': subjects,
    })

@role_required('EXAMINER')
def examiner_exams(request):
    exams = Examination.objects.filter(examiner=request.user).order_by('-created_at')  # Optional: filter by logged-in examiner
    return render(request, 'examinerpanel/exams/index.html', {'exams': exams})

@login_required

@role_required('EXAMINER')
def examiner_questions(request):
    questions_queryset = Question.objects.select_related('subject', 'created_by').order_by('-created_at')

    # Pagination
    paginator = Paginator(questions_queryset, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Question Stats
    stats = Question.objects.aggregate(
        total=Count('id'),
        mcq=Count('id', filter=Q(question_type='MCQ')),
        tf=Count('id', filter=Q(question_type='TRUE_FALSE')),
        essay=Count('id', filter=Q(question_type='ESSAY')),
    )

    return render(request, 'examinerpanel/questions/index.html', {
        'questions': page_obj,
        'page_obj': page_obj,
        'stats': stats,
    })


@role_required('EXAMINER')
def question_create(request):
    available_exams = Examination.objects.filter(examiner=request.user)
    subjects = Subject.objects.all()

    if request.method == 'POST':
        return handle_question_form(request)

    return render(request, 'examinerpanel/Questions/form.html', {
        'question': None,
        'subjects': subjects,
        'available_exams': available_exams,
    })


@role_required('EXAMINER')
def question_edit(request, pk):
    question = get_object_or_404(Question, pk=pk)

    if question.created_by != request.user:
        messages.error(request, "You don't have permission to edit this question.")
        return redirect('examiner_questions')

    available_exams = Examination.objects.filter(examiner=request.user)
    subjects = Subject.objects.all()

    if request.method == 'POST':
        return handle_question_form(request, question)

    return render(request, 'examinerpanel/Questions/form.html', {
        'question': question,
        'subjects': subjects,
        'available_exams': available_exams,
    })

# ✅ Shared Create/Edit Logic
@transaction.atomic
def handle_question_form(request, question=None):
    if not request.user.is_authenticated or request.user.role != 'EXAMINER':
        messages.error(request, "You must be logged in as an examiner.")
        return redirect('examiner_login')

    data = request.POST
    files = request.FILES
    is_new = question is None

    if is_new:
        question = Question(created_by=request.user)

    # Basic fields
    question.text = data.get('text')
    question.question_type = data.get('question_type', '').upper()
    question.marks = int(data.get('marks', 1))
    question.image = files.get('image') if 'image' in files else question.image

    # Exam or Subject assignment logic
    exam_id = data.get('exam_id')
    unassign_exam = data.get('unassign_exam') == '1'

    if not is_new and question.examination and unassign_exam:
        question.examination = None  # unassign exam
        question.subject = None      # subject must be chosen manually

    if exam_id:
        exam = Examination.objects.filter(id=exam_id, examiner=request.user).first()
        if exam:
            question.examination = exam
            question.subject = exam.subject
        else:
            messages.error(request, "Invalid exam selected.")
            return redirect(request.path)
    elif not question.examination:
        subject_id = data.get('subject_id')
        if subject_id:
            question.subject_id = subject_id
        else:
            messages.error(request, "Please select a subject or exam.")
            return redirect(request.path)

    if not question.text or not question.question_type:
        messages.error(request, "Please fill all required fields.")
        return redirect(request.path)

    question.save()

    # If editing, delete old related records
    if not is_new:
        Option.objects.filter(question=question).delete()
        TrueFalseAnswer.objects.filter(question=question).delete()
        MatchingPair.objects.filter(question=question).delete()

    # MCQ
    if question.question_type == 'MCQ':
        correct = data.get('correct_option')
        for key in data:
            if key.startswith('option_'):
                text = data.get(key)
                if text:
                    opt = Option.objects.create(question=question, text=text)
                    if correct and key.endswith(correct):
                        opt.is_correct = True
                        opt.save()

    # True/False
    elif question.question_type == 'TRUE_FALSE':
        answer = data.get('true_false_answer')
        if answer in ['true', 'false']:
            TrueFalseAnswer.objects.create(
                question=question,
                is_true=(answer == 'true')
            )

    # Essay
    elif question.question_type == 'ESSAY':
        question.essay_instructions = data.get('essay_guidelines', '')
        question.save()

    # Matching
    elif question.question_type == 'MATCHING':
        index = 1
        while True:
            left = data.get(f'match_left_{index}')
            right = data.get(f'match_right_{index}')
            if not left or not right:
                break
            MatchingPair.objects.create(question=question, left_text=left, right_text=right)
            index += 1

    messages.success(request, f"Question {'created' if is_new else 'updated'} successfully.")
    return redirect('examiner_questions')

@role_required('EXAMINER')
def examiner_settings(request):
    return render(request, 'examinerpanel/settings/index.html')

@role_required('EXAMINER')
def examiner_analytics(request):
    return render(request, 'examinerpanel/analytics/index.html')

@role_required('EXAMINER')
def examiner_students(request):
    return render(request, 'examinerpanel/students/index.html')

from django.shortcuts import render, redirect, get_object_or_404
from .forms import ExaminationForm
from .models import Examination
from django.contrib.auth.decorators import login_required

from .forms import ExaminationForm
from .models import Examination

@login_required
def examiner_exam_create(request, exam_id=None):
    exam = None
    if exam_id:
        exam = get_object_or_404(Examination, id=exam_id, examiner=request.user)

    if request.method == "POST":
        form = ExaminationForm(request.POST, instance=exam)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.examiner = request.user
            exam.save()
            return redirect('examiner_exams')  # or wherever your exam list is
    else:
        form = ExaminationForm(instance=exam)

    return render(request, 'examinerpanel/exams/form.html', {'form': form, 'exam': exam})

@role_required('EXAMINER')
def examiner_exam_edit(request, exam_id):
    exam = get_object_or_404(Examination, id=exam_id)
    return render(request, 'examinerpanel/exams/form.html', {'exam': exam})
    # Remove this line from examiner_exam_form:
    # print("Subjects found:", subjects.count())

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils.timezone import now
from core.models import Subject, CustomUser
from .models import Examination

@login_required
def examiner_exam_form(request, exam_id=None):
    if not request.user.is_authenticated or request.user.role != 'EXAMINER':
        messages.error(request, "You must be logged in as an examiner.")
        return redirect('examiner_login')

    exam = get_object_or_404(Examination, id=exam_id) if exam_id else None

    if request.method == "POST":
        data = request.POST
        errors = []

        # Extract fields
        exam_name = data.get('exam_name', '').strip()
        subject_id = data.get('subject')
        description = data.get('description', '')
        instructions = data.get('instructions', '')
        tags = data.get('tags', '')
        exam_date = data.get('exam_date')
        start_time = data.get('start_time')
        end_time = data.get('end_time') or None
        expiry_date = data.get('expiry_date') or None
        timezone = data.get('timezone', 'UTC')
        selection_mode = data.get('selection_mode', 'random')

        try:
            duration_minutes = int(data.get('duration_minutes'))
            if duration_minutes <= 0:
                raise ValueError
        except (TypeError, ValueError):
            duration_minutes = None
            errors.append("Duration (minutes) is required and must be a positive number.")

        try:
            total_marks = int(data.get('total_marks', 0))
            passing_marks = int(data.get('passing_marks', 0))
            number_of_questions = int(data.get('number_of_questions', 0))
            max_attempts = int(data.get('max_attempts', 1))
        except ValueError:
            errors.append("Numeric fields must contain valid numbers.")

        # Booleans
        allow_negative_marking = 'allow_negative_marking' in data
        shuffle_questions = 'shuffle_questions' in data
        shuffle_options = 'shuffle_options' in data
        allow_resume = 'allow_resume' in data
        allow_skip = 'allow_skip' in data
        allow_flagging = 'allow_flagging' in data
        visible_to_students = 'visible_to_students' in data
        instant_publish = 'instant_publish' in data

        access_type = data.get('access_type', 'all')
        status = data.get('status', 'draft')

        # Subject Validation
        subject = None
        if not subject_id:
            errors.append("Subject is required.")
        else:
            try:
                subject = Subject.objects.get(id=int(subject_id))
                print("DEBUG: subject instance type =", type(subject))
                print("DEBUG: expected FK type =", Examination._meta.get_field("subject").remote_field.model)

            except (Subject.DoesNotExist, ValueError, TypeError):
                errors.append("Selected subject does not exist.")
                subject = None  # Ensure subject is None if not found

        if not exam_name:
            errors.append("Exam name is required.")

        # If there are errors, show form again
        if errors or subject is None:
            for error in errors:
                messages.error(request, error)

            subjects = Subject.objects.all()
            context = {
                'exam': exam,
                'subjects': subjects,
                'form_data': data,
            }
            return render(request, 'examinerpanel/exams/form.html', context)
        print("DEBUG: request.user =", request.user, "ID =", request.user.id)
        print("DEBUG: subject =", subject, "ID =", subject.id if subject else None)

        # Save or Update
        if exam:
            exam.exam_name = exam_name
            exam.subject = subject
            exam.description = description
            exam.instructions = instructions
            exam.tags = tags
            exam.exam_date = exam_date
            exam.start_time = start_time
            exam.end_time = end_time
            exam.expiry_date = expiry_date
            exam.duration_minutes = duration_minutes
            exam.timezone = timezone
            exam.total_marks = total_marks
            exam.passing_marks = passing_marks
            exam.number_of_questions = number_of_questions
            exam.selection_mode = selection_mode
            exam.allow_negative_marking = allow_negative_marking
            exam.shuffle_questions = shuffle_questions
            exam.shuffle_options = shuffle_options
            exam.access_type = access_type
            exam.max_attempts = max_attempts
            exam.allow_resume = allow_resume
            exam.allow_skip = allow_skip
            exam.allow_flagging = allow_flagging
            exam.status = status
            exam.visible_to_students = visible_to_students
            exam.instant_publish = instant_publish
            exam.updated_at = now()
            exam.save()
            messages.success(request, "Exam updated successfully.")
        else:
            Examination.objects.create(
                examiner=request.user,
                exam_name=exam_name,
                subject=subject,
                description=description,
                instructions=instructions,
                tags=tags,
                exam_date=exam_date,
                start_time=start_time,
                end_time=end_time,
                expiry_date=expiry_date,
                duration_minutes=duration_minutes,
                timezone=timezone,
                total_marks=total_marks,
                passing_marks=passing_marks,
                number_of_questions=number_of_questions,
                selection_mode=selection_mode,
                allow_negative_marking=allow_negative_marking,
                shuffle_questions=shuffle_questions,
                shuffle_options=shuffle_options,
                access_type=access_type,
                max_attempts=max_attempts,
                allow_resume=allow_resume,
                allow_skip=allow_skip,
                allow_flagging=allow_flagging,
                status=status,
                visible_to_students=visible_to_students,
                instant_publish=instant_publish,
                created_at=now(),
                updated_at=now()
            )
            messages.success(request, "New exam created successfully.")

        return redirect('examiner_exams')

    # GET Request
    subjects = Subject.objects.all()
    context = {
        'exam': exam,
        'subjects': subjects,
    }
    return render(request, 'examinerpanel/exams/form.html', context)

@role_required('EXAMINER')
def examiner_exam_view(request, exam_id):
    exam = get_object_or_404(Examination, id=exam_id, examiner=request.user)

    if request.method == 'POST':
        question_text = request.POST.get('question_text')
        question_type = request.POST.get('question_type')
        marks = int(request.POST.get('marks', 1))

        if not question_text or not question_type:
            messages.error(request, "Please fill all required fields.")
            return redirect('examiner_exam_view', exam_id=exam.id)

        try:
            with transaction.atomic():
                question = Question.objects.create(
                    examination=exam,
                    subject=exam.subject,
                    text=question_text,
                    question_type=question_type.upper(),
                    marks=marks,
                    image=request.FILES.get('image'),  # Optional
                    created_by=request.user,
                    )

                # Handle MCQ
                if question_type == 'mcq':
                    correct_option = request.POST.get('correct_option')
                    for key in request.POST:
                        if key.startswith('option_'):
                            text = request.POST.get(key)
                            if text:
                                opt = Option.objects.create(question=question, text=text)
                                if correct_option and key.endswith(correct_option):
                                    opt.is_correct = True
                                    opt.save()

                # Handle True/False
                elif question_type == 'true_false':
                    tf_value = request.POST.get('true_false_answer')
                    if tf_value:
                        TrueFalseAnswer.objects.create(
                            question=question,
                            is_true=tf_value.lower() == 'true'
                        )

                # Handle Essay
                elif question_type == 'essay':
                    guidelines = request.POST.get('essay_guidelines', '')
                    question.essay_instructions = guidelines
                    question.save()

                # Handle Matching
                elif question_type == 'matching':
                    index = 1
                    while True:
                        left = request.POST.get(f'match_left_{index}')
                        right = request.POST.get(f'match_right_{index}')
                        if left and right:
                            MatchingPair.objects.create(
                                question=question,
                                left_text=left,
                                right_text=right
                            )
                            index += 1
                        else:
                            break

                messages.success(request, "Question added successfully.")
                return redirect('examiner_exam_view', exam_id=exam.id)

        except Exception as e:
            messages.error(request, f"Error saving question: {str(e)}")
            return redirect('examiner_exam_view', exam_id=exam.id)

    # Fetch all questions and paginate them
    questions_queryset = Question.objects.filter(examination=exam).order_by('-created_at')
    paginator = Paginator(questions_queryset, 5)
    page_number = request.GET.get('page')
    questions = paginator.get_page(page_number)

    total_marks = questions_queryset.aggregate(models.Sum('marks'))['marks__sum'] or 0

    return render(request, 'examinerpanel/exams/view.html', {
        'exam': exam,
        'questions': questions,
        'total_marks': total_marks,
    })
@login_required
def examiner_exam_delete(request, exam_id):
    exam = get_object_or_404(Examination, id=exam_id, examiner=request.user)
    exam.delete()
    messages.success(request, "Exam deleted successfully.")
    return redirect('examiner_exams')


# ✅ ADD THIS FUNCTION BELOW
@login_required
def examiner_dashboard(request):
    return render(request, 'examinerpanel/dashboard/index.html', {
        'examiner': request.user
    })

