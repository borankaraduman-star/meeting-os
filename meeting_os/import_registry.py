"""Duplicate detection for imported audio files.

The cloud import path records only ``original_name`` for a meeting. After a successful import the desktop
app calls ``register_import_digest`` (see desktop.py), which adds ``original_digest`` (SHA-256 of the file the
user picked) and ``original_size`` (bytes) to that meeting's metadata. ``find_duplicate`` matches primarily by
digest; meetings that carry a size but no digest fall back to ``original_name`` + ``original_size``.
Meetings that have only ``original_name`` (imports made before this module existed, or CLI imports) are never
reported: a bare file name is too weak a signal to call something a duplicate.
"""
import hashlib
from pathlib import Path


def digest_path(path, chunk=1<<20):
    """SHA-256 hex digest of a file, streamed so large recordings do not load into memory."""
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(chunk), b''): h.update(block)
    return h.hexdigest()


def find_duplicate(store, digest, name=None, size=None):
    """Most recent existing meeting imported from the same file, or None."""
    from .recovery import metadata
    for row in store.meetings():  # ordered newest first
        meta=metadata(row)
        same_digest=bool(digest) and meta.get('original_digest')==digest
        same_file=name is not None and size is not None and not meta.get('original_digest') and meta.get('original_name')==name and meta.get('original_size')==size
        if same_digest or same_file:
            return {'meeting':row['id'],'title':row['title'],'model':meta.get('model'),'status':row['status']}
    return None
