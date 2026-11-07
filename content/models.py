from django.db import models


class LanguageCode(models.TextChoices):
    HASSANIYA = "mey", "Hassaniya"
    PULAAR = "fuc", "Pulaar"
    SONINKE = "snk", "Soninke"
    WOLOF = "wol", "Wolof"

class Level(models.TextChoices):
    WORD = "word", "Word"
    PHRASE = "phrase", "Phrase"
    SENTENCE = "sentence", "Sentence"
    PARAGRAPH = "paragraph", "Paragraph"

class MasterPhrase(models.Model):
    master_id = models.CharField(max_length=64, unique=True)
    language_code = models.CharField(max_length=3, choices=LanguageCode.choices)

    text_native = models.TextField()
    text_arabic = models.TextField(blank=True, default="")
    text_french = models.TextField(blank=True, default="")
    text_english = models.TextField(blank=True, default="")

    category = models.CharField(max_length=100, blank=True, default="")
    level = models.CharField(max_length=20, choices=Level.choices, blank=True, default="")

    source_name = models.CharField(max_length=255, blank=True, default="")
    source_url = models.URLField(max_length=1000, blank=True, default="")

    is_lesson_ready = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "content_master_phrase"
        indexes = [
            models.Index(fields=["language_code", "level"], name="mp_lang_level_idx"),
            models.Index(fields=["language_code", "is_lesson_ready"], name="mp_lang_ready_idx"),
        ]

    def __str__(self):
        return f"[{self.language_code}] {self.text_native[:40]}"