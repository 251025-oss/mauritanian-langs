from rest_framework import serializers


class ExerciseOptionSerializer(serializers.Serializer):
    id = serializers.CharField(source="master_id")
    text = serializers.CharField(source="text_native")


class ExerciseQuestionSerializer(serializers.Serializer):
    question_id = serializers.CharField()
    language_code = serializers.CharField()
    prompt = serializers.CharField()
    prompt_language = serializers.CharField(default="ar")
    level = serializers.CharField(allow_blank=True)
    category = serializers.CharField(allow_blank=True)
    options = ExerciseOptionSerializer(many=True)


class CheckAnswerRequestSerializer(serializers.Serializer):
    question_id = serializers.CharField(max_length=64)
    selected_id = serializers.CharField(max_length=64)