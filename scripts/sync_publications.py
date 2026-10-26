"""Sync transaction: primary-source failure leaves all tracked files untouched."""
import argparse
import sys
from pathlib import Path
from publications import Client, SourceError, read_json, sync, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report', type=Path, default=Path('work/sync-report.json'))
    parser.add_argument('--direct', action='store_true', help='Ignore local proxy environment; keep TLS verification enabled')
    args = parser.parse_args()
    try:
        old = read_json(args.root / 'data/publications.json')
        new, pending, events = sync(old, Client(args.direct))
        changed = write_json(args.root / 'data/publications.json', new)
        pending_changed = write_json(args.root / 'data/pending-publications.json', pending)
        write_json(args.report, {'success': True, 'changed': changed, 'pending_changed': pending_changed, 'events': events, 'pending': pending})
        print(f'Content changed: {changed}; review queue changed: {pending_changed}; pending: {len(pending)}')
        return 0
    except (SourceError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        write_json(args.report, {'success': False, 'error': str(exc), 'changed': False})
        print('Sync failed; existing data preserved: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
