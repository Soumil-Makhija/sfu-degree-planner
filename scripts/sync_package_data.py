#!/usr/bin/env python3
"""Copy reviewed normalized JSON into wheel resources, or check exact equality."""
import argparse
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = root / 'sfu_planner' / 'data'
    target.mkdir(exist_ok=True)
    for filename in ('catalog.json', 'requirements.json'):
        source, destination = root / 'data' / filename, target / filename
        if args.check:
            if not destination.is_file() or destination.read_bytes() != source.read_bytes():
                parser.exit(1, f'Package resource differs: {filename}\n')
        else:
            shutil.copyfile(source, destination)
    print('Package resources match reviewed source data.')


if __name__ == '__main__':
    main()
