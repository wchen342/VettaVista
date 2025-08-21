import logging
import os
import platform
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import platformdirs
from lingua import LanguageDetectorBuilder

from vettavista_backend.config import APP_NAME, VERSION
from vettavista_backend.modules.business.utils.base import LanguageDetector

logger = logging.getLogger(__name__)

is_linux = platform.system() == 'Linux'

if is_linux:
    import fasttext
    from fasttext.FastText import _FastText

    # Monkey patch the predict method
    logger.info("Monkey patching fasttext _FastText.predict to fix NumPy array copy issue...")
    original_predict = _FastText.predict

    def patched_predict(self, text, k=1, threshold=0.0, on_unicode_error="strict"):
        def check(entry):
            if entry.find("\n") != -1:
                raise ValueError("predict processes one line at a time (remove '\\n')")
            entry += "\n"
            return entry

        if type(text) == list:
            # Handle list case unchanged
            text = [check(entry) for entry in text]
            return self.f.multilinePredict(text, k, threshold, on_unicode_error)
        else:
            # Handle single text case with fixed numpy array creation
            text = check(text)
            predictions = self.f.predict(text, k, threshold, on_unicode_error)
            if predictions:
                probs, labels = zip(*predictions)
            else:
                probs, labels = ([], ())

            return labels, np.asarray(probs)  # Use asarray instead of array(copy=False)

    _FastText.predict = patched_predict
    logger.info("Successfully patched _FastText.predict")


class HybridLanguageDetector(LanguageDetector):
    """
    Lingua is used for all OSes.
    Fasttext is only used on Linux to avoid compilation problems.
    """
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Only initialize once
        if not HybridLanguageDetector._initialized:
            if is_linux:
                # Initialize fasttext model
                config_dir = Path(platformdirs.user_data_dir(APP_NAME, appauthor=False, version=VERSION))
                model_dir = config_dir / "models"
                model_path = model_dir / "lid.176.ftz"
                if not model_dir.exists():
                    os.makedirs(model_dir, exist_ok=True)
                if not model_path.exists():
                    # Download model if not exists
                    import wget
                    logger.info("Downloading fasttext language detection model...")
                    wget.download("https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz",
                                  str(model_path))
                self.lang_model = fasttext.load_model(str(model_path))

            # Initialize Lingua detector
            logger.info("Initializing Lingua language detector...")
            self.lingua_detector = LanguageDetectorBuilder.from_all_languages().build()

            HybridLanguageDetector._initialized = True

    def _clean_fasttext_lang(self, lang: str) -> str:
        """Clean fasttext language code to full name"""
        # Remove __label__ prefix and get base language code
        lang = lang.replace('__label__', '')
        if '-' in lang:
            lang = lang.split('-')[0]  # Take base language code for zh-cn, zh-tw etc
            
        # Map common ISO codes to full names matching Lingua's format
        iso_to_name = {
            'en': 'ENGLISH',
            'de': 'GERMAN',
            'fr': 'FRENCH',
            'es': 'SPANISH',
            'pt': 'PORTUGUESE',
            'it': 'ITALIAN',
            'nl': 'DUTCH',
            'pl': 'POLISH',
            'da': 'DANISH',
            'fi': 'FINNISH',
            'sv': 'SWEDISH',
            'no': 'NORWEGIAN',
            'ja': 'JAPANESE',
            'zh': 'CHINESE',
            'ru': 'RUSSIAN',
            'ko': 'KOREAN',
            'ar': 'ARABIC',
            'hi': 'HINDI',
            'tr': 'TURKISH',
            'cs': 'CZECH',
            'hu': 'HUNGARIAN',
            'el': 'GREEK',
            'he': 'HEBREW',
            'th': 'THAI',
            'vi': 'VIETNAMESE',
            'id': 'INDONESIAN',
            'ms': 'MALAY',
            'ro': 'ROMANIAN',
            'sk': 'SLOVAK',
            'uk': 'UKRAINIAN',
            'bg': 'BULGARIAN',
            'hr': 'CROATIAN',
            'lt': 'LITHUANIAN',
            'lv': 'LATVIAN',
            'et': 'ESTONIAN',
            'sl': 'SLOVENIAN'
        }
        
        result = iso_to_name.get(lang.lower())
        if result is None:
            logger.warning(f"Unknown language code from fasttext: {lang}")
            return 'UNKNOWN'  # Instead of returning the uppercase version
        return result

    def detect_language(self, text: str, k: int = 3) -> Tuple[Optional[str], float]:
        """Use Lingua and (optionally) fasttext for more accurate language detection"""
        # Clean text: remove newlines and extra spaces
        text = ' '.join(text.split())
        if not text:
            return None, 0.0

        try:
            if is_linux:
                # Get top-k predictions from fasttext
                predictions = self.lang_model.predict(text, k=k)
                fasttext_predictions = [
                    (self._clean_fasttext_lang(lang), float(score))
                    for lang, score in zip(predictions[0], predictions[1])
                ]

                logger.info("Fasttext top predictions:")
                for lang, score in fasttext_predictions:
                    logger.info(f"  {lang}: {score:.3f}")

            # Get top-k predictions from Lingua
            lingua_results = self.lingua_detector.compute_language_confidence_values(text)
            # Convert Lingua results to list of tuples, using full language names
            lingua_predictions = [
                (str(result.language).split('.')[-1], float(result.value))  # Take part after the dot
                for result in lingua_results
            ][:k]

            logger.info("Lingua top predictions:")
            for lang, score in lingua_predictions:
                logger.info(f"  {lang}: {score:.3f}")

            # Decision logic
            # Check if top predictions from both models agree
            if is_linux:
                if fasttext_predictions[0][0] == lingua_predictions[0][0]:
                    best_lang = fasttext_predictions[0][0]
                    # Use the higher confidence score
                    confidence = max(fasttext_predictions[0][1], lingua_predictions[0][1])
                    logger.info(f"Models agree on top prediction: {best_lang} ({confidence:.3f})")
                    return best_lang, confidence

                # If they disagree, look for any agreement in top-k predictions
                agreements = []
                for ft_lang, ft_score in fasttext_predictions:
                    for lingua_lang, lingua_score in lingua_predictions:
                        if ft_lang == lingua_lang:
                            agreements.append((ft_lang, max(ft_score, lingua_score)))
            
                if agreements:
                    # Sort by confidence score and take the highest one
                    best_agreement = max(agreements, key=lambda x: x[1])
                    logger.info(f"Found multiple agreements, using highest confidence: {best_agreement[0]} ({best_agreement[1]:.3f})")
                    return best_agreement

            # If no agreement, use Lingua's top prediction
            best_lang, confidence = lingua_predictions[0]
            logger.info(f"No agreement found, using Lingua: {best_lang} ({confidence:.3f})")
            return best_lang, confidence

        except Exception as e:
            logger.warning(f"Language detection failed: {str(e)}")
            return 'ENGLISH', 0.0  # Default to English
