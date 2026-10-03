import re
import unicodedata
from datetime import datetime, timedelta, date


# ---------------------------------------------------------------------------
# Nombres saisis par l'utilisateur (formulaires ET fichiers Excel)
# ---------------------------------------------------------------------------
def parse_float(raw, default=None):
    """Convertit une valeur saisie (ou lue dans Excel) en nombre.
    Accepte : 50 / 50.5 / "50,5" / "2 500" / "2 500 Ar" / "1.234,5".
    Retourne `default` si la valeur est vide ou invalide (au lieu de planter)."""
    if raw is None:
        return default
    if isinstance(raw, bool):
        return default
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if s == "":
        return default
    # Retire unités / espaces (y compris espaces insécables d'Excel)
    s = re.sub(r"(?i)\s*(ar|mga|ariary)\s*$", "", s)
    s = s.replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    if "," in s and "." in s:
        # "1.234,5" (format FR) ou "1,234.5" (format EN)
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return default


def clean_text(raw):
    """Texte propre depuis une cellule Excel (qui peut contenir un nombre,
    une date, None...). Évite les plantages du type 'int has no strip'."""
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    return str(raw).strip()


# ---------------------------------------------------------------------------
# Heure locale Madagascar (UTC+3, pas d'heure d'été)
# Les dates sont stockées en UTC dans la base ; on les AFFICHE en heure locale.
# ---------------------------------------------------------------------------
LOCAL_OFFSET = timedelta(hours=3)


def now_local():
    return datetime.utcnow() + LOCAL_OFFSET


def to_local(dt):
    if dt is None:
        return None
    return dt + LOCAL_OFFSET


def local_to_utc(dt):
    return dt - LOCAL_OFFSET


def local_today_start_utc(days_ago=0):
    """Minuit (heure de Madagascar) il y a `days_ago` jours, exprimé en UTC —
    pour que « Aujourd'hui » commence bien à 00h00 locale et non à 03h00."""
    n = now_local()
    midnight_local = datetime(n.year, n.month, n.day) - timedelta(days=days_ago)
    return local_to_utc(midnight_local)


def parse_date_any(raw):
    """Lit une date depuis Excel/CSV/formulaire : objet date Excel, JJ/MM/AAAA,
    JJ-MM-AAAA, AAAA-MM-JJ, JJ/MM/AA. Retourne un datetime ou None si invalide."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, date):
        return datetime(raw.year, raw.month, raw.day)
    if isinstance(raw, (int, float)):
        # Date Excel envoyée comme nombre (ex : 46288)
        try:
            return datetime(1899, 12, 30) + timedelta(days=float(raw))
        except (OverflowError, ValueError):
            return None
    s = str(raw).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d.%m.%Y",
                "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Codes courts des ingrédients (ex : Poulet → PLT, Yaourt → YRT)
# ---------------------------------------------------------------------------
_SMALL_WORDS = {"de", "du", "des", "la", "le", "les", "au", "aux", "et", "en", "a", "d", "l", "sy", "ny"}
_VOWELS = set("AEIOUY")


def _strip_accents(s):
    s = s.replace("œ", "oe").replace("Œ", "OE").replace("æ", "ae").replace("Æ", "AE")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalize_code(raw):
    """Code saisi à la main : majuscules, lettres/chiffres uniquement, 6 max."""
    s = _strip_accents(clean_text(raw)).upper()
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s[:6]


def _word_code(word, length):
    """Première lettre + consonnes suivantes ; complété par les voyelles si besoin,
    en gardant l'ordre des lettres dans le mot."""
    letters = [c for c in word if c.isalpha()]
    if not letters:
        return ""
    chosen = [0]
    for i in range(1, len(letters)):
        if len(chosen) >= length:
            break
        if letters[i] not in _VOWELS and letters[i] != letters[chosen[-1]]:
            chosen.append(i)
    i = 1
    while len(chosen) < length and i < len(letters):
        if i not in chosen:
            chosen.append(i)
        i += 1
    chosen.sort()
    return "".join(letters[i] for i in chosen)[:length]


def suggest_code(name):
    """Code de 3 lettres à partir du nom :
    Poulet → PLT · Yaourt → YRT · Huile → HUL · Pomme de terre → PMT ·
    Sauce tomate oignon → STO."""
    s = _strip_accents(clean_text(name)).upper()
    words = [w for w in re.split(r"[^A-Z0-9]+", s) if w and w.lower() not in _SMALL_WORDS]
    if not words:
        return "ING"
    if len(words) >= 3:
        code = "".join(w[0] for w in words[:3])
    elif len(words) == 2:
        code = _word_code(words[0], 2) + words[1][0]
    else:
        code = _word_code(words[0], 3)
    return (code or "ING").ljust(3, "X")[:3]


def unique_code(base, taken):
    """Rend le code unique en ajoutant un chiffre : PLT, PLT2, PLT3...
    `taken` = ensemble des codes déjà utilisés (en majuscules)."""
    base = normalize_code(base) or "ING"
    if base not in taken:
        return base
    n = 2
    while f"{base[:5]}{n}" in taken:
        n += 1
    return f"{base[:5]}{n}"
