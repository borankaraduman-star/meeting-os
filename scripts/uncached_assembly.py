"""Opt-in retry experiment: uncached WAV descriptors during private assembly.

The caller must run assembly serially in its retry worker. No production default
is changed; model and later pipeline file opens retain their normal behavior.
"""
import errno
import fcntl
import functools
import inspect
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


def install_uncached_assembly():
    from meeting_os import audio
    from meeting_os.recovery_audio import MAX_CHUNKS, MAX_JOURNAL_BYTES, MAX_LINE_BYTES

    original_assembly = audio.assemble_capture
    counts = {'source_fds': 0, 'destination_fds': 0}
    flag = getattr(fcntl, 'F_NOCACHE', 48)

    def counted(kind):
        counts[kind] += 1
        if counts[kind] == 1:
            try:
                print(json.dumps({'uncached_assembly_applied': dict(counts)}), file=sys.stderr, flush=True)
            except OSError:
                pass

    @functools.wraps(original_assembly)
    def assemble(directory):
        if Path(directory).is_symlink():
            raise ValueError('Retry snapshot cannot be a symlink')
        root = Path(directory).resolve(strict=True)
        if (root.parent != Path(tempfile.gettempdir()).resolve(strict=True)
                or re.fullmatch(r'meeting-os-retry-[0-9a-f]{32}-[a-zA-Z0-9_-]{6,64}', root.name) is None):
            raise ValueError('Expected private retry snapshot')
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            root_info = os.fstat(root_fd)
            if root_info.st_uid != os.getuid() or stat.S_IMODE(root_info.st_mode) != 0o700:
                raise ValueError('Retry snapshot is not private')
            try:
                os.stat('capture-native.jsonl', dir_fd=root_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError('Expected copied retry journal only')
            # Fresh retry snapshots contain only the bounded copied journal.
            journal_fd = os.open('events.jsonl', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
            with os.fdopen(journal_fd, 'rb') as journal:
                info = os.fstat(journal.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_JOURNAL_BYTES:
                    raise ValueError('Invalid retry journal')
                raw = journal.read(MAX_JOURNAL_BYTES + 1)
            if len(raw) > MAX_JOURNAL_BYTES:
                raise ValueError('Retry journal limit')
            sources = {}
            destinations = set()
            for line in raw.splitlines():
                if len(line) > MAX_LINE_BYTES:
                    raise ValueError('Retry journal line limit')
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError('Invalid retry event')
                if event.get('event') != 'chunk':
                    continue
                source = event.get('source')
                path = Path(event['path'])
                if (source not in ('mic', 'system') or not path.is_absolute()
                        or path.parent.resolve(strict=True) != root or re.fullmatch(r'[0-9]{6}\.wav', path.name) is None):
                    raise ValueError('Unexpected retry WAV')
                info = os.stat(path.name, dir_fd=root_fd, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
                    raise ValueError('Invalid retry WAV')
                sources[path.name] = (info.st_dev, info.st_ino)
                # Assembly writes `<source>-full.wav.tmp` and renames it into place only when it is whole.
                destinations.add(source+'-full.wav');destinations.add(source+'-full.wav.tmp')
                if len(sources) > MAX_CHUNKS:
                    raise ValueError('Retry chunk limit')

            original_soundfile = audio.sf.SoundFile
            signature = inspect.signature(original_soundfile)

            @functools.wraps(original_soundfile)
            def uncached_soundfile(file, *args, **kwargs):
                # Bind the real signature: sf.read passes all parameters through
                # closefd positionally, including subtype, endian and format.
                bound = signature.bind(file, *args, **kwargs)
                bound.apply_defaults()
                if not isinstance(file, (str, os.PathLike)):
                    raise ValueError('Expected path-owned retry WAV')
                path = Path(file)
                if not path.is_absolute() or path.parent != root:
                    raise ValueError('WAV outside private retry snapshot')
                current = root.stat()
                if (current.st_dev, current.st_ino) != (root_info.st_dev, root_info.st_ino):
                    raise ValueError('Retry snapshot changed')
                mode = bound.arguments['mode']
                if bound.arguments['format'] not in (None, 'WAV'):
                    raise ValueError('Expected WAV format')
                if mode == 'r' and path.name in sources:
                    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                    kind = 'source_fds'
                elif mode == 'w' and path.name in destinations:
                    # Only create fresh assembled outputs; never truncate an
                    # existing inode that could alias a source or external file.
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                    kind = 'destination_fds'
                    bound.arguments['format'] = 'WAV'
                else:
                    raise ValueError('Unsupported retry WAV open')
                fd = os.open(path.name, flags, 0o600, dir_fd=root_fd)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise ValueError('Invalid retry WAV descriptor')
                    if mode == 'r' and (info.st_dev, info.st_ino) != sources[path.name]:
                        raise ValueError('Retry WAV changed')
                    fcntl.fcntl(fd, flag, 1)
                    counted(kind)
                    bound.arguments['file'] = fd
                    bound.arguments['closefd'] = True
                    return original_soundfile(*bound.args, **bound.kwargs)
                except BaseException:
                    try:
                        os.close(fd)
                    except OSError as exc:
                        if exc.errno != errno.EBADF:
                            raise
                    raise

            audio.sf.SoundFile = uncached_soundfile
            try:
                return original_assembly(root)
            finally:
                audio.sf.SoundFile = original_soundfile
        finally:
            os.close(root_fd)

    audio.assemble_capture = assemble
    return counts
