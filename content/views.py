import random

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LanguageCode, MasterPhrase
from .serializers import (
    CheckAnswerRequestSerializer,
    ExerciseQuestionSerializer,
)

NUM_DISTRACTORS = 3
DEFAULT_LANGUAGE = LanguageCode.HASSANIYA.value


def lesson_queryset(language_code: str):
    """Lesson-ready rows with an Arabic prompt and a native text."""
    return (
        MasterPhrase.objects
        .filter(language_code=language_code, is_lesson_ready=True)
        .exclude(text_arabic="")
        .exclude(text_native="")
    )


class RandomExerciseView(APIView):
    """GET /api/v1/exercises/random/?language_code=mey"""
    permission_classes = [AllowAny]

    def get(self, request):
        language_code = request.query_params.get("language_code", DEFAULT_LANGUAGE)
        if language_code not in LanguageCode.values:
            return Response(
                {"detail": f"Invalid language_code. Choose one of {LanguageCode.values}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = lesson_queryset(language_code)
        target = qs.order_by("?").first()
        if target is None:
            return Response(
                {"detail": "No lesson-ready content for this language."},
                status=status.HTTP_404_NOT_FOUND,
            )

        base_candidates = (
            qs.exclude(pk=target.pk)
              .exclude(text_native=target.text_native)
              .exclude(text_arabic=target.text_arabic)
        )
        # Prefer the same unit type (word/phrase/sentence); fall back to any if too few.
        candidates = list(
            base_candidates.filter(level=target.level).order_by("?")[:NUM_DISTRACTORS * 4]
        )
        if len(candidates) < NUM_DISTRACTORS * 2:
            candidates += list(
                base_candidates.exclude(level=target.level).order_by("?")[:NUM_DISTRACTORS * 4]
            )

        distractors, seen_texts = [], {target.text_native}
        for candidate in candidates:
            if candidate.text_native in seen_texts:
                continue
            seen_texts.add(candidate.text_native)
            distractors.append(candidate)
            if len(distractors) == NUM_DISTRACTORS:
                break

        if len(distractors) < NUM_DISTRACTORS:
            return Response(
                {"detail": "Not enough distinct content to build an exercise."},
                status=status.HTTP_404_NOT_FOUND,
            )

        options = [target, *distractors]
        random.shuffle(options)

        payload = {
            "question_id": target.master_id,
            "language_code": target.language_code,
            "prompt": target.text_arabic,
            "prompt_language": "ar",
            "level": target.level,
            "category": target.category,
            "options": options,
        }
        return Response(ExerciseQuestionSerializer(payload).data)


class CheckAnswerView(APIView):
    """POST /api/v1/exercises/check/  {"question_id": "...", "selected_id": "..."}"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CheckAnswerRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question_id = serializer.validated_data["question_id"]
        selected_id = serializer.validated_data["selected_id"]

        try:
            target = MasterPhrase.objects.get(master_id=question_id)
        except MasterPhrase.DoesNotExist:
            return Response({"detail": "Unknown question_id."}, status=status.HTTP_404_NOT_FOUND)

        is_correct = selected_id == question_id
        if not is_correct:
            # Tolerate a different row that carries the exact same native text.
            is_correct = MasterPhrase.objects.filter(
                master_id=selected_id,
                language_code=target.language_code,
                text_native=target.text_native,
            ).exists()

        return Response({
            "correct": is_correct,
            "question_id": question_id,
            "selected_id": selected_id,
            "correct_answer": {"id": target.master_id, "text": target.text_native},
            "translations": {
                "arabic": target.text_arabic,
                "french": target.text_french,
                "english": target.text_english,
            },
        })