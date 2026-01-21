import re
from typing import Dict, Iterator, Optional


class RegexHashMap:
    """Regex-keyed map with caching, modeled after HeidelTime's RegexHashMap."""

    def __init__(self) -> None:
        self._container: Dict[str, str] = {}
        self._cache: Dict[str, str] = {}

    def clear(self) -> None:
        self._container.clear()
        self._cache.clear()

    def put(self, key: str, value: str) -> None:
        self._container[key] = value

    def contains_key(self, key: str) -> bool:
        if key in self._cache:
            return True
        if key in self._container:
            return True
        for pattern in self._container.keys():
            if re.fullmatch(pattern, key):
                return True
        return False

    def get(self, key: Optional[str]) -> Optional[str]:
        if key is None:
            return None
        if key in self._cache:
            return self._cache[key]
        if key in self._container:
            return self._container[key]
        for pattern, value in self._container.items():
            if re.fullmatch(pattern, key):
                self._cache[key] = value
                return value
        return None

    def keys(self) -> Iterator[str]:
        for key in self._container.keys():
            yield key
        for key in self._cache.keys():
            if key not in self._container:
                yield key

