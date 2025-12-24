import inspect
import re
import importlib
import pkgutil
import inspect
from typing import Type, List, TypeVar
import re
from typing import Callable, List, TypeVar

from bs4 import BeautifulSoup

T = TypeVar("T")

DEFAULT_ENGINES: List[str] = [
    "Navigation Controls",
    "Python Engine",
    "Navigation Engine",
    "COMPLETE",
]


def extract_code_from_funct(funct: Callable) -> List[str]:
    """Extract code lines from a function while removing the first line (function definition) and the last line (return) and correcting indentation"""
    source_code = inspect.getsource(funct)
    source_code_lines = source_code.splitlines()[1:]  # remove the first line
    nident = len(source_code_lines[0]) - len(source_code_lines[0].lstrip())  # count nb char in indentation
    return [line[nident:] for line in source_code_lines[:-1]]  # every line except the return


def extract_imports_from_lines(lines: List[str]) -> str:
    """Only keep import lines from python code lines and join them"""
    return "\n".join([line for line in lines if line.startswith("from") or line.startswith("import")])


def extract_before_next_engine(text: str) -> str:
    # Define the patterns for "Next engine:" and similar patterns
    next_engine_patterns = [r"Next engine:\s*", r"### Next Engine:\s*"]

    # Split the text using the "Next engine:" patterns
    for pattern in next_engine_patterns:
        split_text = re.split(pattern, text, maxsplit=1)
        if len(split_text) > 1:
            result = split_text[0].strip()
            break
    else:
        result = text.strip()

    thoughts_pattern = r"^Thoughts:\s*"
    result = re.sub(thoughts_pattern, "", result).strip()

    return result


def extract_next_engine(text: str, next_engines: List[str] = DEFAULT_ENGINES) -> str:
    # Use a regular expression to find the content after "Next engine:"

    next_engine_patterns = [r"Next engine:\s*(.*)", r"### Next Engine:\s*(.*)"]

    for pattern in next_engine_patterns:
        next_engine_match = re.search(pattern, text)
        if next_engine_match:
            extracted_text = next_engine_match.group(1).strip()
            # To avoid returning a non-existent engine

            for engine in next_engines:
                if engine.lower() in extracted_text.lower():
                    return engine

    raise ValueError(f"No next engine found in the text: {text}")


def clean_html(
    html_to_clean: str,
    tags_to_remove: List[str] = ["style", "svg", "script"],
    attributes_to_keep: List[str] = ["id", "href"],
) -> str:
    """
    Clean HTML content by removing specified tags and attributes while keeping specified attributes.

    Args:
        html_to_clean (str): The HTML content to clean.
        tags_to_remove (List[str]): List of tags to remove from the HTML content. Default is ['style', 'svg', 'script'].
        attributes_to_keep (List[str]): List of attributes to keep in the HTML tags. Default is ['id', 'href'].

    Returns:
        str: The cleaned HTML content.

    Example:
    >>> from clean_html_for_llm import clean_html
    >>> cleaned_html = clean_html(
    ...     '<div id="main" style="color:red">Hello <script>alert("World")</script></div>',
    ...     tags_to_remove=["script"],
    ...     attributes_to_keep=["id"],
    ... )
    """
    for tag in tags_to_remove:
        html_to_clean = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", html_to_clean, flags=re.DOTALL)

    attributes_to_keep = "|".join(attributes_to_keep)
    pattern = rf'\b(?!({attributes_to_keep})\b)\w+(?:-\w+)?\s*=\s*["\'][^"\']*["\']'
    cleaned_html = re.sub(pattern, "", html_to_clean)
    return cleaned_html


def find_subclasses(base_class: Type[T], package) -> List[Type[T]]:
    """Recursively import all submodules in `package` and return all subclasses of `base_class`."""
    found = []

    if isinstance(package, str):
        package = importlib.import_module(package)

    for module_info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        module_name = module_info.name
        try:
            mod = importlib.import_module(module_name)
        except Exception as e:
            print(f"⚠️ Failed to import {module_name}: {e}")
            continue

        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, base_class) and obj is not base_class:
                found.append(obj)

    return found


def is_valid_url(url: str) -> bool:
    """Exhaustive regex to check for valid URL."""
    regex = re.compile(
        r"^(?:http|ftp)s?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|"  # ...or ipv4
        r"\[?[A-F0-9]*:[A-F0-9:]+\]?)"  # ...or ipv6
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return re.match(regex, url) is not None


def is_valid_html(html: str) -> bool:
    """Simple check to see if HTML can be parsed."""
    try:
        BeautifulSoup(html, "lxml")
        return True
    except Exception:
        return False
