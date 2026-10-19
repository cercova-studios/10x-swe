"""Explicit host shares and cold, journaled directory recovery. No guest code runs here."""
import contextlib
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tarfile
import tempfile
import uuid


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
            temporary.replace(path)
            sync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sync_file(path):
    with Path(path).open('rb') as stream:
        os.fsync(stream.fileno())


def identity(path):
    info = Path(path).lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('Mount root must remain a directory: ' + str(path))
    return [info.st_dev, info.st_ino]


def overlaps(left, right):
    return left.is_relative_to(right) or right.is_relative_to(left)


def xattrs(path):
    if hasattr(os, 'listxattr'):
        return {name: hashlib.sha256(os.getxattr(path, name, follow_symlinks=False)).hexdigest()
                for name in sorted(os.listxattr(path, follow_symlinks=False))}
    # CPython exposes xattrs on Linux only. Darwin's native API keeps host metadata intact.
    libc = ctypes.CDLL(None, use_errno=True)
    def read(name, *args):
        function = getattr(libc, name)
        function.restype = ctypes.c_ssize_t
        def call(buffer, length):
            result = function(os.fsencode(path), *args, buffer, ctypes.c_size_t(length),
                              *([ctypes.c_uint32(0)] if name == 'getxattr' else []), ctypes.c_int(1))
            if result < 0:
                code = ctypes.get_errno()
                raise OSError(code, os.strerror(code), str(path))
            return result
        size = call(None, 0)
        buffer = ctypes.create_string_buffer(size)
        return buffer.raw[:call(buffer, size)]
    return {os.fsdecode(name): hashlib.sha256(read('getxattr', name)).hexdigest()
            for name in sorted(read('listxattr').split(b'\0')) if name}


def lease_root():
    return Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')).expanduser().resolve() / '10x-swe/mount-leases'


@contextlib.contextmanager
def leases(owner, mounts=None):
    """Serialize admission across playground state directories in this user state namespace."""
    root = lease_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        file = root / 'leases.json'
        rows = json.loads(file.read_text()) if file.exists() else []
        others = [row for row in rows if row['owner'] != str(owner)]
        if mounts is not None:
            for mount in mounts:
                for row in others:
                    if (mount['mode'] == 'rw' or row['mode'] == 'rw') and overlaps(Path(mount['path']), Path(row['path'])):
                        raise ValueError('Host mount already leased by ' + row['owner'] + ': ' + mount['path'])
            write_json(file, others + [dict(mount, owner=str(owner)) for mount in mounts])
        yield
        if mounts is None:
            write_json(file, others)


def tree(path):
    """Fingerprint without following links; reject aliases that escape the writable grant."""
    root = Path(path)
    entries = {}
    inodes = {}
    pending = [root]
    while pending:
        item = pending.pop()
        info = item.lstat()
        relative = item.relative_to(root).as_posix()
        if (info.st_uid != os.getuid() or info.st_gid not in {*os.getgroups(), os.getgid()}
                or info.st_mode & (stat.S_ISUID | stat.S_ISGID)):
            raise ValueError('Writable mount contains foreign ownership or privileged modes: ' + str(item))
        entry = {'mode': stat.S_IMODE(info.st_mode), 'gid': info.st_gid}
        if stat.S_ISDIR(info.st_mode):
            entry['type'] = 'directory'
            pending.extend(sorted(item.iterdir(), reverse=True))
        elif stat.S_ISREG(info.st_mode):
            entry.update(type='file', sha256=sha256(item), bytes=info.st_size)
            key = (info.st_dev, info.st_ino)
            inodes.setdefault(key, []).append((relative, info.st_nlink))
        elif stat.S_ISLNK(info.st_mode):
            entry.update(type='symlink', target=os.readlink(item))
            try:
                contained = item.resolve().is_relative_to(root.resolve())
            except (OSError, RuntimeError):
                contained = False
            if Path(entry['target']).is_absolute() or not contained:
                raise ValueError('Writable symlink escapes mount: ' + str(item))
        else:
            raise ValueError('Writable mount contains a special file: ' + str(item))
        entry['xattrs'] = xattrs(item)
        entries[relative] = entry
    for links in inodes.values():
        if len(links) != links[0][1]:
            raise ValueError('Writable hardlink points outside mount: ' + links[0][0])
        if len(links) > 1:
            names = sorted(name for name, _ in links)
            for name in names:
                entries[name]['hardlinks'] = names
    return entries


def declarations(read_only, writable, directory, repository):
    mounts = []
    protected = [directory.parent.resolve(), lease_root()]
    for mode, paths in (('ro', read_only), ('rw', writable)):
        for value in paths:
            selected = value.expanduser().absolute()
            path = selected.resolve(strict=True)
            if selected.is_symlink() or not path.is_dir() or path in (Path('/'), Path.home().resolve()):
                raise ValueError('Select a real project, dataset or skills directory: ' + str(value))
            if ':' in str(path) or any(ord(c) < 32 or ord(c) == 127 for c in str(path)):
                raise ValueError('Mount paths cannot contain colons or control characters')
            if any(overlaps(path, p) for p in protected):
                raise ValueError('Host mount must be separate from playground control state: ' + str(path))
            if mode == 'rw' and overlaps(path, repository.resolve()):
                raise ValueError('Do not expose the host playground launcher as writable; copy it with --workspace')
            if any(overlaps(path, Path(m['path'])) for m in mounts):
                raise ValueError('Host mount roots must not overlap: ' + str(path))
            if mode == 'rw':
                tree(path)
            mounts.append({'path': str(path), 'mode': mode, 'identity': identity(path)})
    return mounts


def validate(mounts, *, contents=True):
    for mount in mounts:
        path = Path(mount['path'])
        if path.resolve() != path or identity(path) != mount['identity']:
            raise ValueError('Host mount identity changed; refusing access: ' + str(path))
        if contents and mount['mode'] == 'rw':
            tree(path)


def snapshot(mounts, folder):
    """Host writers must be paused. All guest writers must already be stopped."""
    validate(mounts)
    results = []
    for index, mount in enumerate(mounts):
        record = dict(mount)
        if mount['mode'] == 'rw':
            path = Path(mount['path'])
            before = tree(path)
            archive = folder / ('mount-' + str(index) + '.tar')
            subprocess.run(['tar', '--acls', '--xattrs', '-cf', str(archive), '-C', str(path), '.'], check=True,
                           stdin=subprocess.DEVNULL)
            sync_file(archive)
            if tree(path) != before:
                raise ValueError('Host mount changed while snapshotting; pause host writers: ' + str(path))
            record.update(archive=archive.name, sha256=sha256(archive), files=before)
        results.append(record)
    return results


def verify(records, folder, mounts):
    if [(m['path'], m['mode']) for m in records] != [(m['path'], m['mode']) for m in mounts]:
        raise ValueError('Checkpoint mounts do not match this playground')
    for record in records:
        if record['mode'] != 'rw':
            continue
        archive = folder / record['archive']
        if archive.parent != folder or sha256(archive) != record['sha256']:
            raise ValueError('Host mount archive checksum mismatch')
        with tarfile.open(archive) as stream:
            for member in stream:
                name = PurePosixPath(member.name)
                if name.is_absolute() or '..' in name.parts or not (member.isdir() or member.isfile() or member.issym() or member.islnk()):
                    raise ValueError('Unsafe host snapshot member: ' + member.name)
                if member.uid != os.getuid() or member.gid not in {*os.getgroups(), os.getgid()}:
                    raise ValueError('Host snapshot ownership cannot be restored: ' + member.name)
                if member.issym() or member.islnk():
                    target = (name.parent if member.issym() else PurePosixPath('.')) / member.linkname
                    depth = 0
                    if target.is_absolute():
                        raise ValueError('Unsafe host snapshot link: ' + member.name)
                    for part in target.parts:
                        depth += -1 if part == '..' else int(part != '.')
                        if depth < 0:
                            raise ValueError('Unsafe host snapshot link: ' + member.name)


class Restore:
    """A journal is retained until VM admission commits or directory rollback completes."""
    def __init__(self, directory):
        self.directory = directory
        self.journal = directory / 'restore.json'

    def pending(self):
        if self.journal.exists():
            raise ValueError('Interrupted restore; run playground recover before continuing')

    def prepare(self, records, folder, state):
        self.pending()
        rows = []
        data = {'schema': 'playground-restore/v1', 'before': state, 'rows': rows}
        write_json(self.journal, data)
        for record in records:
            if record['mode'] != 'rw':
                continue
            path = Path(record['path'])
            # Siblings permit atomic renames on this filesystem; backups stay outside the grant.
            stage = Path(tempfile.mkdtemp(prefix='.' + path.name + '-restore-', dir=path.parent))
            try:
                before = tree(path)
            except (OSError, ValueError):
                # Broken guest files must not prevent rewind; the original tree is retained whole.
                before = None
            row = {'path': str(path), 'stage': str(stage), 'backup': str(stage) + '-before',
                   'original': identity(path), 'restored': identity(stage), 'files_before': before}
            rows.append(row)
            write_json(self.journal, data)
            subprocess.run(['tar', '--acls', '--xattrs', '-xpf', str(folder / record['archive']),
                            '--same-owner', '--numeric-owner', '-C', str(stage)], check=True, stdin=subprocess.DEVNULL)
            if tree(stage) != record['files']:
                raise ValueError('Restored mount metadata or content differs from checkpoint: ' + str(path))
        return data

    def replace(self, transaction):
        for row in transaction['rows']:
            path, stage, backup = (Path(row[key]) for key in ('path', 'stage', 'backup'))
            if identity(path) != row['original'] or (row['files_before'] is not None and tree(path) != row['files_before']):
                raise ValueError('Host directory changed during restore: ' + str(path))
            path.rename(backup)
            sync_directory(path.parent)
            stage.rename(path)
            sync_directory(path.parent)

    def rollback(self):
        data = json.loads(self.journal.read_text())
        for row in reversed(data['rows']):
            path, stage, backup = (Path(row[key]) for key in ('path', 'stage', 'backup'))
            if backup.exists():
                if identity(backup) != row['original']:
                    raise ValueError('Recovery backup identity changed: ' + str(backup))
                if path.exists():
                    if identity(path) != row['restored'] or stage.exists():
                        raise ValueError('Recovery path changed; inspect restore.json: ' + str(path))
                    path.rename(stage)
                    sync_directory(path.parent)
                backup.rename(path)
                sync_directory(path.parent)
            elif not path.exists() or identity(path) != row['original']:
                raise ValueError('Original host directory unavailable; inspect restore.json: ' + str(path))
        # Caller persists restored VM/state identity before removing the journal.
        return data['before']

    def finish(self):
        destination = self.directory / 'recoveries'
        destination.mkdir(exist_ok=True)
        path = destination / (uuid.uuid4().hex + '.json')
        self.journal.rename(path)
        sync_directory(self.directory)
        sync_directory(destination)
        return str(path)
