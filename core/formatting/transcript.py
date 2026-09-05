import re

LANGUAGE_NAMES = {
    "af": "Afrikaans", "am": "Amharic", "ar": "Arabic", "as": "Assamese", "az": "Azerbaijani",
    "ba": "Bashkir", "be": "Belarusian", "bg": "Bulgarian", "bn": "Bengali", "bo": "Tibetan",
    "br": "Breton", "bs": "Bosnian", "ca": "Catalan", "cs": "Czech", "cy": "Welsh", "da": "Danish",
    "de": "German", "el": "Greek", "en": "English", "es": "Spanish", "et": "Estonian", "eu": "Basque",
    "fa": "Persian", "fi": "Finnish", "fo": "Faroese", "fr": "French", "gl": "Galician", "gu": "Gujarati",
    "ha": "Hausa", "haw": "Hawaiian", "he": "Hebrew", "hi": "Hindi", "hr": "Croatian", "ht": "Haitian Creole",
    "hu": "Hungarian", "hy": "Armenian", "id": "Indonesian", "is": "Icelandic", "it": "Italian", "ja": "Japanese",
    "jw": "Javanese", "ka": "Georgian", "kk": "Kazakh", "km": "Khmer", "kn": "Kannada", "ko": "Korean",
    "la": "Latin", "lb": "Luxembourgish", "ln": "Lingala", "lo": "Lao", "lt": "Lithuanian", "lv": "Latvian",
    "mg": "Malagasy", "mi": "Maori", "mk": "Macedonian", "ml": "Malayalam", "mn": "Mongolian", "mr": "Marathi",
    "ms": "Malay", "mt": "Maltese", "my": "Myanmar", "ne": "Nepali", "nl": "Dutch", "nn": "Nynorsk",
    "no": "Norwegian", "oc": "Occitan", "pa": "Punjabi", "pl": "Polish", "ps": "Pashto", "pt": "Portuguese",
    "ro": "Romanian", "ru": "Russian", "sa": "Sanskrit", "sd": "Sindhi", "si": "Sinhala", "sk": "Slovak",
    "sl": "Slovenian", "sn": "Shona", "so": "Somali", "sq": "Albanian", "sr": "Serbian", "su": "Sundanese",
    "sv": "Swedish", "sw": "Swahili", "ta": "Tamil", "te": "Telugu", "tg": "Tajik", "th": "Thai",
    "tk": "Turkmen", "tl": "Tagalog", "tr": "Turkish", "tt": "Tatar", "uk": "Ukrainian", "ur": "Urdu",
    "uz": "Uzbek", "vi": "Vietnamese", "yi": "Yiddish", "yo": "Yoruba", "zh": "Chinese",
}


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([،,.!?؟:;])", r"\1", text)
    text = re.sub(r"([.!?؟])(?=\S)", r"\1 ", text)
    return text.strip()


def clean_transcript(segments):
    """Build readable paragraphs without dropping any emitted segment text."""
    paragraphs = []
    current = []
    word_count = 0

    def flush():
        nonlocal current, word_count
        if current:
            value = _tidy(" ".join(current))
            if value:
                paragraphs.append(value)
        current = []
        word_count = 0

    for segment in segments:
        text = _tidy(segment.get("text", ""))
        if not text:
            continue

        speaker_break = bool(re.match(r"^>+\s*", text))
        text = re.sub(r"^>+\s*", "", text).strip()
        if not text:
            continue

        if speaker_break and current:
            flush()

        current.append(text)
        word_count += len(text.split())

        # Prefer natural sentence ends, but also prevent one giant paragraph
        # when auto-captions contain little or no punctuation.
        if word_count >= 24 and re.search(r"[.!?؟]$", text):
            flush()
        elif word_count >= 60:
            flush()

    flush()
    return "\n\n".join(paragraphs).strip()


def timestamped_transcript(segments):
    def ts(x):
        x = int(max(0, x))
        return f"{x // 3600:02d}:{(x % 3600) // 60:02d}:{x % 60:02d}"

    return "\n\n".join(
        f"{ts(s['start'])} – {ts(s['end'])}\n{_tidy(s['text'])}"
        for s in segments
        if s.get("text", "").strip()
    )


def language_label(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code or "Unknown")


def format_caption_text(text: str):
    text = _tidy(text)
    return "\n\n".join(
        p.strip() for p in re.split(r"(?<=[.!?؟])\s+", text) if p.strip()
    )
