from hashlib import md5
from base64 import urlsafe_b64encode
from posixpath import split, splitext

_HASH_LEN = 6
_B64_LEN = 8


def _hashed(s: str) -> str:
    return urlsafe_b64encode(md5(s.encode('utf-8')).digest()[:_HASH_LEN])[:_B64_LEN].decode('ascii')


def truncate_name(name: str, maxlen: int = 63) -> str:
    name = name.replace("\\", "/").strip("/")
    if len(name) <= maxlen:
        return name
    path, basename = split(name)
    max_path_len = maxlen - (len(basename) + _B64_LEN + 4)
    if max_path_len <= 0:
        name, extension = splitext(name)
        return _hashed(name) + extension
    path_split = -max_path_len
    path_discard, path_keep = path[:path_split], path[path_split:]
    if "/" in path_keep:
        extra_discard, final_keep = path_keep.split("/", maxsplit=1)
        final_keep += "/"
    else:
        extra_discard, final_keep = path_keep, ""
    final_discard = path_discard + extra_discard
    return f"...{_hashed(final_discard)}/{final_keep}{basename}"
