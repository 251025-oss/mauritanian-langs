import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from content.models import LanguageCode, MasterPhrase

REQUIRED_COLUMNS = {
    "master_id", "language_code", "text_native", "text_arabic", "text_french",
    "text_english", "category", "level", "source_name", "source_url",
}
LESSON_FILE_CANDIDATES = ("app_ready.csv", "master_lessons.csv")


class Command(BaseCommand):
    help = (
        "Replace all MasterPhrase rows with the contents of master_cleaned.csv, "
        "flagging rows whose master_id appears in the lesson file as is_lesson_ready=True. "
        "Everything runs in a single transaction."
    )

    def add_arguments(self, parser):
        default_master = Path(settings.BASE_DIR) / "data" / "processed" / "master_cleaned.csv"
        parser.add_argument("--master", default=str(default_master), help="Path to master_cleaned.csv")
        parser.add_argument("--lessons", default=None,
                            help="Path to app_ready.csv or master_lessons.csv (auto-detected if omitted)")
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--dry-run", action="store_true",
                            help="Run everything, then roll back the transaction")

    # ---------- helpers ----------
    @staticmethod
    def _clean(value):
        return (value or "").strip()

    def _resolve_lessons_path(self, explicit, folder: Path) -> Path:
        if explicit:
            path = Path(explicit)
            if not path.exists():
                raise CommandError(f"Lesson file not found: {path}")
            return path
        for name in LESSON_FILE_CANDIDATES:
            candidate = folder / name
            if candidate.exists():
                return candidate
        raise CommandError(f"No lesson file found in {folder} (looked for {LESSON_FILE_CANDIDATES}).")

    def _load_lesson_ids(self, path: Path) -> set:
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if "master_id" not in (reader.fieldnames or []):
                raise CommandError(f"'master_id' column missing in {path}")
            return {self._clean(r["master_id"]) for r in reader if self._clean(r["master_id"])}

    def _build_phrases(self, master_path: Path, lesson_ids: set, stats: dict) -> list:
        valid_languages = set(LanguageCode.values)
        phrases, seen = [], set()

        with master_path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise CommandError(f"Missing columns in {master_path}: {sorted(missing)}")

            for row in reader:
                master_id = self._clean(row["master_id"])
                language = self._clean(row["language_code"])
                native = self._clean(row["text_native"])

                if not master_id or not native:
                    stats["skipped_empty"] += 1
                    continue
                if language not in valid_languages:
                    stats["skipped_language"] += 1
                    continue
                if master_id in seen:
                    stats["skipped_duplicate"] += 1
                    continue
                seen.add(master_id)

                is_ready = master_id in lesson_ids
                stats["lesson_ready"] += is_ready

                phrases.append(MasterPhrase(
                    master_id=master_id,
                    language_code=language,
                    text_native=native,
                    text_arabic=self._clean(row["text_arabic"]),
                    text_french=self._clean(row["text_french"]),
                    text_english=self._clean(row["text_english"]),
                    category=self._clean(row["category"]),
                    level=self._clean(row["level"]),
                    source_name=self._clean(row["source_name"]),
                    source_url=self._clean(row["source_url"]),
                    is_lesson_ready=is_ready,
                ))

        stats["lesson_ids_not_in_master"] = len(lesson_ids - seen)
        return phrases

    # ---------- main ----------
    def handle(self, *args, **opts):
        master_path = Path(opts["master"])
        if not master_path.exists():
            raise CommandError(f"Master file not found: {master_path}")

        lessons_path = self._resolve_lessons_path(opts["lessons"], master_path.parent)
        self.stdout.write(f"Master : {master_path}\nLessons: {lessons_path}")

        stats = {"skipped_empty": 0, "skipped_language": 0, "skipped_duplicate": 0,
                 "lesson_ready": 0, "lesson_ids_not_in_master": 0}

        # Parse + validate everything BEFORE touching the database.
        lesson_ids = self._load_lesson_ids(lessons_path)
        phrases = self._build_phrases(master_path, lesson_ids, stats)
        if not phrases:
            raise CommandError("No valid rows parsed; aborting so existing data is preserved.")

        # Single atomic swap: any failure rolls back and leaves old data intact.
        with transaction.atomic():
            deleted, _ = MasterPhrase.objects.all().delete()
            MasterPhrase.objects.bulk_create(phrases, batch_size=opts["batch_size"])
            if opts["dry_run"]:
                transaction.set_rollback(True)

        prefix = "[DRY RUN – rolled back] " if opts["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Deleted {deleted} old rows, inserted {len(phrases)} "
            f"({stats['lesson_ready']} lesson-ready)."
        ))
        if stats["lesson_ids_not_in_master"]:
            self.stdout.write(self.style.WARNING(
                f"{stats['lesson_ids_not_in_master']} IDs in the lesson file were not found in master."
            ))
        for key in ("skipped_empty", "skipped_language", "skipped_duplicate"):
            if stats[key]:
                self.stdout.write(self.style.WARNING(f"{key}: {stats[key]}"))