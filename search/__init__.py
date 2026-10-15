"""Punto de entrada del componente de búsqueda, sin conexión a base de datos."""
from .engine import SearchEngine
from .models import Candidate, FoundObject, SearchQuery, SearchResult

__all__ = ['SearchEngine', 'FoundObject', 'SearchQuery', 'Candidate', 'SearchResult']
