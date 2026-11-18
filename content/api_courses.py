"""Nouvelle API basée sur Course / Item / Translation.

Fichier : content/api_courses.py   (NOUVEAU fichier, views.py n'est pas modifié)
Routes  : voir content/urls.py

  GET  /api/v1/courses/                      -> liste des cours
  GET  /api/v1/courses/<id>/question/        -> une question (QCM, 4 options)
  POST /api/v1/answer/                       -> {"question_id": "...", "selected_id": 123}
"""
import random
import uuid

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (Attempt, Course, Item, ReviewCard, Translation,
                     translation_key)

NUM_DISTRACTORS = 3
SESSION_KEY = "pending_questions"
MAX_PENDING = 20          # on garde au plus 20 questions non répondues par session
VALID_UNIT_TYPES = {"word", "phrase", "sentence"}
POOL = 60                 # nombre de candidats tirés avant filtrage


def _first(item, language_id):
    return (item.translations.filter(language_id=language_id)
            .exclude(status=Translation.Status.FLAGGED).order_by("id").first())


class CourseListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        data = [{
            "id": c.id, "title": c.title, "is_active": c.is_active,
            "prompt_language": c.prompt_language.code,
            "target_language": c.target_language.code,
        } for c in Course.objects.select_related("prompt_language", "target_language")]
        return Response(data)


class CourseQuestionView(APIView):
    """Question : texte dans la langue de départ, options dans la langue apprise."""
    permission_classes = [AllowAny]

    def get(self, request, course_id):
        try:
            course = Course.objects.select_related("prompt_language", "target_language").get(pk=course_id)
        except Course.DoesNotExist:
            return Response({"detail": "Cours inconnu."}, status=status.HTTP_404_NOT_FOUND)
        # Pendant le développement, un cours inactif reste testable avec ?dev=1.
        if not course.is_active and request.query_params.get("dev") != "1":
            return Response({"detail": "Ce cours n'est pas encore actif."},
                            status=status.HTTP_404_NOT_FOUND)

        p_id, t_id = course.prompt_language_id, course.target_language_id
        unit_type = request.query_params.get("unit_type", "word")
        if unit_type not in VALID_UNIT_TYPES:
            return Response({"detail": f"unit_type invalide. Choisir parmi {sorted(VALID_UNIT_TYPES)}."},
                            status=status.HTTP_400_BAD_REQUEST)
        items = (Item.objects.filter(needs_review=False, unit_type=unit_type)
                 .filter(translations__language_id=p_id)
                 .filter(translations__language_id=t_id)
                 .distinct())
        item = items.order_by("?").first()
        if item is None:
            return Response({"detail": "Aucun contenu pour ce cours."},
                            status=status.HTTP_404_NOT_FOUND)

        prompt = _first(item, p_id)
        answer = _first(item, t_id)
        if prompt is None or answer is None:
            return Response({"detail": "Contenu incomplet, réessayez."},
                            status=status.HTTP_404_NOT_FOUND)

        # Tous les textes valides de CET item dans la langue apprise (variantes).
        own_keys = {translation_key(t.text) for t in item.translations.filter(language_id=t_id)}
        prompt_key = translation_key(prompt.text)
        tol = max(1, round(answer.word_count * 0.3))

        candidates = (Translation.objects
                      .filter(language_id=t_id, item__unit_type=item.unit_type,
                              item__needs_review=False,
                              word_count__gte=answer.word_count - tol,
                              word_count__lte=answer.word_count + tol)
                      .exclude(status=Translation.Status.FLAGGED)
                      .exclude(item=item)
                      .order_by("?")[:POOL])

        distractors, used = [], set(own_keys)
        for cand in candidates:
            key = translation_key(cand.text)
            if key in used:
                continue
            # jamais un item dont le texte de départ est identique à la question
            same_prompt = cand.item.translations.filter(language_id=p_id).exists() and any(
                translation_key(t.text) == prompt_key
                for t in cand.item.translations.filter(language_id=p_id))
            if same_prompt:
                continue
            used.add(key)
            distractors.append(cand)
            if len(distractors) == NUM_DISTRACTORS:
                break
        if len(distractors) < NUM_DISTRACTORS:
            return Response({"detail": "Pas assez de contenu distinct pour construire la question."},
                            status=status.HTTP_404_NOT_FOUND)

        options = [answer, *distractors]
        random.shuffle(options)

        token = uuid.uuid4().hex
        pending = request.session.get(SESSION_KEY, {})
        if len(pending) >= MAX_PENDING:
            pending.pop(next(iter(pending)))
        pending[token] = {
            "options": [o.id for o in options],
            "correct": list(item.translations.filter(language_id=t_id).values_list("id", flat=True)),
            "answer_id": answer.id,
        }
        request.session[SESSION_KEY] = pending

        return Response({
            "question_id": token,
            "course_id": course.id,
            "prompt": prompt.text,
            "prompt_language": course.prompt_language.code,
            "target_language": course.target_language.code,
            "unit_type": item.unit_type,
            "options": [{"id": o.id, "text": o.text} for o in options],
        })


class AnswerView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = str(request.data.get("question_id", ""))
        try:
            selected_id = int(request.data.get("selected_id"))
        except (TypeError, ValueError):
            return Response({"detail": "selected_id invalide."}, status=status.HTTP_400_BAD_REQUEST)

        pending = request.session.get(SESSION_KEY, {})
        q = pending.pop(token, None)          # une question = une seule réponse
        request.session[SESSION_KEY] = pending
        if q is None:
            return Response({"detail": "Question inconnue ou déjà répondue."},
                            status=status.HTTP_404_NOT_FOUND)
        if selected_id not in q["options"]:
            return Response({"detail": "Cette option n'a pas été proposée."},
                            status=status.HTTP_400_BAD_REQUEST)

        is_correct = selected_id in q["correct"]
        answer = Translation.objects.get(pk=q["answer_id"])
        selected = Translation.objects.get(pk=selected_id)

        if request.user.is_authenticated:
            Attempt.objects.create(user=request.user, translation=answer,
                                   answer=selected.text, is_correct=is_correct)
            card, _ = ReviewCard.objects.get_or_create(user=request.user, translation=answer)
            card.review(is_correct)

        return Response({
            "correct": is_correct,
            "correct_answer": {"id": answer.id, "text": answer.text},
        })