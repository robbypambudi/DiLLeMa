import re

import nltk
from loguru import logger
from nltk import sent_tokenize, word_tokenize

# Download required NLTK resources
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')


class DocumentCleaner:
    def __init__(self, preserve_context=True):
        """
        Initialize document cleaner optimized for Indonesian RAG systems

        Args:
            preserve_context: If True, preserves important contextual information
        """
        self.preserve_context = preserve_context

        # Indonesian stopwords yang aman untuk dihapus (tidak menghilangkan konteks penting)
        # Mengurangi daftar stopwords untuk preservasi konteks
        self.safe_stopwords = {
            'adalah', 'akan', 'atau', 'belum', 'bisa', 'dapat', 'harus',
            'juga', 'karena', 'ketika', 'maka', 'namun', 'saat', 'sangat',
            'saya', 'sebagai', 'sebuah', 'sudah', 'telah', 'tersebut',
            'tetapi', 'tidak', 'untuk', 'yang', 'yaitu'
        }

        # Stopwords berbahaya yang TIDAK boleh dihapus untuk konteks KP
        self.important_contextual_words = {
            'di', 'ke', 'dari', 'dengan', 'pada', 'dalam', 'melalui', 'via',
            'kepada', 'oleh', 'setelah', 'sebelum', 'sampai', 'hingga'
        }

        logger.info('ImprovedDocumentCleaner initialized for Indonesian RAG system.')

    def normalize_unicode(self, text: str) -> str:
        """Normalize Unicode characters while preserving Indonesian characters"""
        # Preserve common Indonesian characters
        text = text.replace('–', '-').replace('—', '-')  # Normalize dashes
        text = text.replace('"', '"').replace('"', '"')  # Normalize quotes
        text = text.replace(''', "'").replace(''', "'")  # Normalize apostrophes

        # Only normalize problematic Unicode, not all
        text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)  # Remove zero-width chars
        return text

    def remove_headers_footers(self, text: str) -> str:
        """Conservative header and footer removal"""
        lines = text.split('\n')

        # Only remove obvious headers/footers, not content
        header_patterns = [
            r'^\s*page\s+\d+\s*$',
            r'^\s*\d+\s*$',  # Just page numbers
            r'^\s*confidential\s*$',
            r'^\s*draft\s*$'
        ]

        footer_patterns = [
            r'^\s*copyright.*$',
            r'^\s*all rights reserved.*$',
            r'^\s*-\s*\d+\s*-\s*$'
        ]

        cleaned_lines = []
        for line in lines:
            is_header_footer = any(
                re.match(pattern, line.strip(), re.IGNORECASE)
                for pattern in header_patterns + footer_patterns
            )

            if not is_header_footer and line.strip():
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def preserve_important_patterns(self, text: str) -> str:
        """Preserve patterns important for KP domain"""
        # Preserve email patterns
        text = re.sub(r'(\w+)\s*\.\s*(\w+)\s*@\s*(\w+)\s*\.\s*(\w+)\s*\.\s*(\w+)',
                      r'\1.\2@\3.\4.\5', text)

        # Preserve phone numbers
        text = re.sub(r'(\+?\s*\d{2,3})\s*(\d{3,4})\s*-?\s*(\d{4,5})\s*-?\s*(\d{4})',
                      r'\1 \2-\3-\4', text)

        # Preserve academic codes (like course codes)
        text = re.sub(r'([A-Z]+)\s*(\d+)', r'\1\2', text)

        return text

    def clean_special_characters(self, text: str) -> str:
        """Conservative special character cleaning"""
        # Only remove truly problematic characters
        # Keep: . , ! ? : ; - ( ) [ ] / @
        problematic_chars = ['*', '\\', '|', '#', '$', '%', '^', '&', '~', '`']

        for char in problematic_chars:
            text = text.replace(char, ' ')

        # Clean up multiple spaces but preserve structure
        text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces/tabs to single space
        text = re.sub(r'\n\s*\n', '\n\n', text)  # Multiple newlines to double newline

        return text.strip()

    def normalize_indonesian_text(self, text: str) -> str:
        """Normalize Indonesian text patterns"""
        # Standardize common Indonesian abbreviations
        abbreviations = {
            r'\bdr\b': 'doktor',
            r'\bprof\b': 'profesor',
            r'\bkp\b': 'kerja praktik',
            r'\bmhs\b': 'mahasiswa',
            r'\bdgn\b': 'dengan',
            r'\butk\b': 'untuk',
            r'\byg\b': 'yang',
            r'\btsb\b': 'tersebut',
            r'\bdll\b': 'dan lain lain'
        }

        for abbrev, full_form in abbreviations.items():
            text = re.sub(abbrev, full_form, text, flags=re.IGNORECASE)

        return text

    def smart_stopword_removal(self, text: str) -> str:
        """Smart stopword removal that preserves context"""
        if not self.preserve_context:
            return text

        sentences = sent_tokenize(text)
        cleaned_sentences = []

        for sentence in sentences:
            words = word_tokenize(sentence.lower())

            # Only remove safe stopwords, keep contextual ones
            filtered_words = []
            for i, word in enumerate(words):
                # Always keep important contextual words
                if word in self.important_contextual_words:
                    filtered_words.append(word)
                # Remove safe stopwords only if they don't break context
                elif word in self.safe_stopwords:
                    # Keep if it's part of important phrase
                    if i > 0 and i < len(words) - 1:
                        prev_word = words[i - 1]
                        next_word = words[i + 1]
                        # Keep if surrounded by important words
                        if (prev_word not in self.safe_stopwords or
                                next_word not in self.safe_stopwords):
                            filtered_words.append(word)
                else:
                    filtered_words.append(word)

            if filtered_words:
                cleaned_sentences.append(' '.join(filtered_words))

        return ' '.join(cleaned_sentences)

    def minimal_clean(self, text: str) -> str:
        """Minimal cleaning that preserves semantic meaning"""
        # Step 1: Basic normalization
        text = self.normalize_unicode(text)
        text = self.preserve_important_patterns(text)

        # Step 2: Conservative structure cleaning
        text = self.remove_headers_footers(text)
        text = self.clean_special_characters(text)

        # Step 3: Text normalization
        text = self.normalize_indonesian_text(text)

        # Step 4: Final cleanup
        text = re.sub(r'\s+', ' ', text)  # Normalize spaces
        text = text.strip()

        return text

    def standard_clean(self, text: str) -> str:
        """Standard cleaning with smart preprocessing"""
        # Start with minimal clean
        text = self.minimal_clean(text)

        # Add smart stopword removal
        text = self.smart_stopword_removal(text)

        return text

    def aggressive_clean(self, text: str) -> str:
        """Aggressive cleaning (use with caution for RAG)"""
        text = self.standard_clean(text)

        # Additional aggressive steps
        aggressive_stopwords = {
            'ini', 'itu', 'disini', 'disitu', 'begitu', 'begini',
            'demikian', 'seperti', 'misalnya', 'contoh', 'yaitu'
        }

        words = text.split()
        words = [word for word in words if word.lower() not in aggressive_stopwords]

        return ' '.join(words)

    def clean_document(self, text: str, level: str = "standard") -> str:
        """
        Main cleaning pipeline with different levels

        Args:
            text: Input text to clean
            level: "minimal", "standard", or "aggressive"

        Returns:
            Cleaned text
        """
        if level == "minimal":
            return self.minimal_clean(text)
        elif level == "standard":
            return self.standard_clean(text)
        elif level == "aggressive":
            return self.aggressive_clean(text)
        else:
            raise ValueError("Level must be 'minimal', 'standard', or 'aggressive'")
