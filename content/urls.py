from django.urls import path

from .api_courses import AnswerView, CourseListView, CourseQuestionView
from .views import CheckAnswerView, RandomExerciseView

app_name = "content"

urlpatterns = [
    # ANCIENNES routes (lisent MasterPhrase) : gardées le temps de la transition
    path("exercises/random/", RandomExerciseView.as_view(), name="exercise-random"),
    path("exercises/check/", CheckAnswerView.as_view(), name="exercise-check"),
    # NOUVELLES routes (Course / Item / Translation)
    path("courses/", CourseListView.as_view(), name="course-list"),
    path("courses/<int:course_id>/question/", CourseQuestionView.as_view(), name="course-question"),
    path("answer/", AnswerView.as_view(), name="answer"),
]