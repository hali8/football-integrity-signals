"""fis-fetch: source-selecting entry point for every dataset this project knows."""

from __future__ import annotations

import argparse

from fis import sources


def _defaults_for(source: sources.Source) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=f"fis-fetch {source.name}", add_help=False)
    source.add_fetch_arguments(parser)
    return parser.parse_args([])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fis-fetch", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--all",
        action="store_true",
        help="fetch every registered source (large; can take a long time)",
    )
    subparsers = parser.add_subparsers(dest="source", metavar="SOURCE")
    for name in sources.known():
        source = sources.get(name)
        sub = subparsers.add_parser(name, help=source.description)
        source.add_fetch_arguments(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.all and args.source is not None:
        parser.error("--all cannot be combined with a source subcommand")

    if args.all:
        names = sources.resolve(None, all_=True)
        sizes = ", ".join(f"{n} (~{sources.get(n).approx_download_gb:.1f} GB)" for n in names)
        print(f"warning: fetching every source -- {sizes}. This can take a long time.")
        status = 0
        for name in names:
            source = sources.get(name)
            status = source.run_fetch(_defaults_for(source)) or status
        return status

    name = sources.resolve(args.source)[0]
    source = sources.get(name)
    run_args = args if args.source is not None else _defaults_for(source)
    return source.run_fetch(run_args)


if __name__ == "__main__":
    raise SystemExit(main())
