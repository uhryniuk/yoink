import argparse
import sys
from pathlib import Path

from yoink import __version__
from yoink.common import is_valid_url, load_urls_from_json, load_urls_from_txt
from yoink.drivers.selenium import SeleniumDriver
from yoink.exceptions import CliError


def _handle_stdio() -> list[str]:
    urls = []
    for line in sys.stdin:
        line = line.strip()
        if line and is_valid_url(line):
            urls.append(line)
    return urls


def _handle_url_file(url_path: Path) -> list[str]:
    if url_path.suffix == ".txt":
        return load_urls_from_txt(url_path)
    elif url_path.suffix == ".json":
        return load_urls_from_json(url_path)

    print("unknown file extension, treating as text:", url_path, file=sys.stderr)
    return load_urls_from_txt(url_path)


def _handle_input(url_data: str) -> list[str]:
    url_path = Path(url_data)
    if url_data == "-":
        return _handle_stdio()
    elif url_path.exists() and url_path.is_file():
        return _handle_url_file(url_path)
    elif is_valid_url(url_data):
        return [url_data]

    raise CliError(f"Could not parse url information from input: {url_data}", exit_code=1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="yoink", description="Fetch and archive URLs.")
    p.add_argument("input", type=str, nargs="?", help="URL or path to files containing URLs ('-' for stdin)")
    p.add_argument("--workers", "-w", type=int, default=1, help="Number of concurrent workers (default: 1)")
    p.add_argument("--tarball", "-t", action="store_true", help="Create a tarball of fetched artifacts")
    p.add_argument("--directory", "-d", type=str, default=None, help="Directory to extract or write files to")
    p.add_argument("--version", action="store_true", help="Show version and exit")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    urls: list[str] = []
    try:
        if not bool(args.input):
            print("Error: no input provided", file=sys.stderr)
            return 1

        urls.extend(_handle_input(args.input))
    except Exception as exc:
        print(f"Error: cannot read inputs: {exc}", file=sys.stderr)
        return 2

    if len(urls) == 0:
        print("No urls parsed from input", file=sys.stderr)
        return 0

    # Placeholder: instantiate a driver to show imports are valid
    for url in urls:
        _driver = SeleniumDriver()
        _driver.get(url)
        _driver.wait_for_dom_stable()
        print("extracted!")
        html = _driver.get_html()
        print(len(html))
        _driver.destroy()
        del _driver

    return 0
