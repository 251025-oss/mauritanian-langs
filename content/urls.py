from django.urls import path

from .views import CheckAnswerView, RandomExerciseView

app_name = "content"

urlpatterns = [
    path("exercises/random/", RandomExerciseView.as_view(), name="exercise-random"),
    path("exercises/check/", CheckAnswerView.as_view(), name="exercise-check"),
]