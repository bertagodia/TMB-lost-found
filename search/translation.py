"""Offline Argos Translate integration for the WP4 interface and searches."""
from typing import Literal

Language = Literal['ca', 'es', 'en']


def translate_texts(texts, source_language, target_language):
    if source_language not in {'ca', 'es', 'en'} or target_language not in {'ca', 'es', 'en'}:
        raise ValueError('Els idiomes han de ser ca, es o en.')
    if not isinstance(texts, list) or not 1 <= len(texts) <= 100:
        raise ValueError('Cal enviar entre 1 i 100 textos.')
    if any(not isinstance(text, str) or not text.strip() or len(text) > 1000 for text in texts):
        raise ValueError('Cada text ha de tenir entre 1 i 1000 caràcters.')
    if sum(map(len, texts)) > 12000:
        raise ValueError('La petició de traducció supera els 12000 caràcters.')
    if source_language == target_language:
        return texts.copy()

    try:
        from argostranslate import translate
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            'Falta Argos Translate. Instal·la les dependències amb '
            'python -m pip install -r backend/requirements.txt.'
        ) from exc

    languages = {language.code: language for language in translate.get_installed_languages()}
    if source_language not in languages or target_language not in languages:
        raise RuntimeError(
            'Falten models Argos Translate. Consulta la secció d’idiomes de SETUP.md '
            'per instal·lar català-anglès i castellà-anglès.'
        )
    try:
        results = [translate.translate(text, source_language, target_language) for text in texts]
    except ValueError as exc:
        raise RuntimeError(
            f'No hi ha cap ruta Argos instal·lada de {source_language} a {target_language}. '
            'Instal·la els models d’idioma indicats a SETUP.md.'
        ) from exc
    if any(not isinstance(result, str) or not result.strip() for result in results):
        raise RuntimeError('Argos Translate no ha retornat una traducció per a cada text.')
    return results
