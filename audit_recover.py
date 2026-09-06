"""Recovery test harness. Audit hook is evidence, not a security sandbox."""
import json
import os
from pathlib import Path
import sys

from memory2d import recover


def main():
    bundle, output, forbidden = map(Path, sys.argv[1:4])
    forbidden = forbidden.resolve()
    blocked = []

    def audit(event, args):
        if event.startswith('socket.'):
            raise PermissionError('Network disabled during recovery')
        if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path == forbidden or forbidden in path.parents:
                blocked.append(str(path))
                raise PermissionError('Source-photo directory forbidden')

    sys.addaudithook(audit)
    # Negative control proves that the input-access guard is active.
    try:
        (forbidden / 'grace_hopper.jpg').read_bytes()
    except PermissionError:
        pass
    else:
        raise AssertionError('Source read was not blocked')
    recover(bundle, output)
    assert len(blocked) == 1, 'Decoder attempted to access a source photo'
    print(json.dumps({'source_probe_blocked': True, 'decoder_source_attempts': 0,
                      'network_guard': True, 'fresh_process': True}))


if __name__ == '__main__':
    main()
