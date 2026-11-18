"""Règles de nettoyage SANS Django (testables seules).

Fichier : content/cleaning.py
Utilisé par : content/management/commands/import_items.py
"""
import re

_PAREN = re.compile(r"\s*\([^)]*\)")          # (u, nu)  (tunsini)  ...
_DIGITS = re.compile(r"\d+")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# Catégories trop vagues pour faire un thème de leçon.
VAGUE_CATEGORIES = {"", "Culture", "Lexicon", "Conversational", "Stories", "others"}
VALID_LEVELS = {"word", "phrase", "sentence", "paragraph"}


def clean_gloss(text):
    """Retire les notes de grammaire entre parenthèses d'une définition de dictionnaire.
    'Accompagner (tunsini)' -> 'Accompagner'. Ne touche ni aux virgules ni aux barres '/'."""
    text = _PAREN.sub("", text or "")
    return re.sub(r"\s+", " ", text).strip(" ;,")


def digits_of(text):
    """Les nombres présents dans un texte (chiffres arabes ou orientaux), triés."""
    return sorted(_DIGITS.findall((text or "").translate(_ARABIC_DIGITS)))


def prepare_row(row):
    """Transforme une ligne de MasterPhrase (dict) en ce qu'il faut créer.
    Retourne (None, raison) si la ligne est ignorée, sinon (dict, None)."""
    native = clean_gloss(row.get("text_native", ""))
    arabic = (row.get("text_arabic") or "").strip()
    french = clean_gloss(row.get("text_french", ""))
    if not native:
        return None, "pas de texte natif"
    if not arabic and not french:
        return None, "ni arabe ni français"
    level = row.get("level", "")
    if level == "paragraph":
        return None, "texte long (paragraphe)"
    n_words = len(native.split())
    if level not in VALID_LEVELS:
        level = "word" if n_words <= 1 else "phrase" if n_words <= 4 else "sentence"
    category = (row.get("category") or "").strip()
    return {
        "native": native, "arabic": arabic, "french": french,
        "unit_type": level,
        "difficulty": 1 if n_words <= 1 else 2 if n_words <= 4 else 3 if n_words <= 10 else 4,
        "theme": None if category in VAGUE_CATEGORIES else category,
        # arabe et français présents mais avec des nombres différents : suspect
        "needs_review": bool(arabic and french and digits_of(arabic) != digits_of(french)),
        # empreinte pour repérer les doublons exacts d'une même langue
        "dup_key": (native.casefold(), arabic, french.casefold()),
    }, None