"""Copie MasterPhrase (table brute) vers Item + Translation (tables normalisées).

Fichier : content/management/commands/import_items.py
Lancer  : python manage.py import_items --language snk --limit 50
Sans danger de le relancer : une ligne déjà copiée (même master_id) est ignorée.
MasterPhrase n'est JAMAIS modifiée ni supprimée.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from content.cleaning import prepare_row
from content.models import Course, DataSource, Item, Language, MasterPhrase, Theme, Translation

# code Django, nom, écriture, sens de lecture
LANGS = {
    "ar": ("Arabe", "arabic", "rtl"),
    "fr": ("Français", "latin", "ltr"),
    "mey": ("Hassaniya", "arabic", "rtl"),
    "snk": ("Soninké", "latin", "ltr"),
}
# (langue de départ, langue apprise)
COURSES = [("fr", "snk"), ("fr", "mey"), ("ar", "mey"), ("ar", "snk")]


class Command(BaseCommand):
    help = "Copie MasterPhrase vers Item/Translation (hassaniya et soninké)."

    def add_arguments(self, parser):
        parser.add_argument("--language", choices=["mey", "snk", "all"], default="all")
        parser.add_argument("--limit", type=int, default=0, help="0 = tout")

    def handle(self, *args, **options):
        langs = self._ensure_languages_and_courses()
        codes = ["snk", "mey"] if options["language"] == "all" else [options["language"]]
        for code in codes:
            self._import_language(code, langs, options["limit"])

    def _ensure_languages_and_courses(self):
        langs = {}
        for code, (name, script, direction) in LANGS.items():
            langs[code], _ = Language.objects.get_or_create(
                code=code, defaults={"name": name, "script": script, "direction": direction})
        for src, dst in COURSES:
            Course.objects.get_or_create(
                prompt_language=langs[src], target_language=langs[dst],
                defaults={"title": f"{langs[dst].name} depuis {langs[src].name}", "is_active": False})
        return langs

    @transaction.atomic
    def _import_language(self, code, langs, limit):
        qs = MasterPhrase.objects.filter(language_code=code).order_by("id")
        if limit:
            qs = qs[:limit]
        done = set(Item.objects.filter(master_ref__in=[m.master_id for m in qs])
                   .values_list("master_ref", flat=True))
        seen, skipped, created_items, created_trans, review = set(), {}, 0, 0, 0
        for m in qs:
            if m.master_id in done:
                skipped["déjà importée"] = skipped.get("déjà importée", 0) + 1
                continue
            data, reason = prepare_row({
                "text_native": m.text_native, "text_arabic": m.text_arabic,
                "text_french": m.text_french, "level": m.level, "category": m.category})
            if data is None:
                skipped[reason] = skipped.get(reason, 0) + 1
                continue
            if data["dup_key"] in seen:
                skipped["doublon exact"] = skipped.get("doublon exact", 0) + 1
                continue
            seen.add(data["dup_key"])

            theme = None
            if data["theme"]:
                theme, _ = Theme.objects.get_or_create(name=data["theme"])
            source = None
            if m.source_name:
                source, _ = DataSource.objects.get_or_create(name=m.source_name[:255], url=m.source_url)

            item = Item.objects.create(
                master_ref=m.master_id, theme=theme, unit_type=data["unit_type"],
                difficulty=data["difficulty"], needs_review=data["needs_review"])
            created_items += 1
            review += data["needs_review"]
            for lang_code, text in ((code, data["native"]), ("ar", data["arabic"]), ("fr", data["french"])):
                if text:
                    # save() est appelé ici : le hash est donc bien calculé.
                    Translation(item=item, language=langs[lang_code], text=text,
                                data_source=source).save()
                    created_trans += 1
        self.stdout.write(self.style.SUCCESS(
            f"[{code}] items créés: {created_items} | traductions: {created_trans} | "
            f"à relire (needs_review): {review} | ignorées: {skipped}"))