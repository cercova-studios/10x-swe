"""Synthetic CLI contract: omitted retries = 3, 0 = first attempt only.

A retry follows a failed attempt. This demonstration fails every attempt,
so attempts = max_retries + 1. No network or repository code is used.
"""
import argparse
import json


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--retries', type=int, default=None)
    args = parser.parse_args(argv)
    if args.retries is not None and args.retries < 0:
        parser.error('--retries must be non-negative')
    return args


def resolve_retries(value):
    return value or 3


def main(argv=None):
    args = parse_args(argv)
    max_retries = resolve_retries(args.retries)
    print(json.dumps({'max_retries': max_retries, 'attempts': max_retries + 1}))


if __name__ == '__main__':
    main()
