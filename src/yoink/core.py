from pyper import task

from yoink.drivers.selenium import SeleniumDriver


class ExtractResult:
    url: str
    html: str

    def __init__(self, url: str, html: str) -> None:
        self.url = url
        self.html = html


def get(url: str, *args, **kwargs) -> ExtractResult:
    driver = SeleniumDriver()
    driver.get(url)
    driver.wait_for_dom_stable()
    html = driver.get_html()
    driver.destroy()

    return ExtractResult(url, html)


def get_all(urls: list[str], *args, **kwargs) -> list[ExtractResult]:
    pipeline = task(lambda: urls, branch=True) | task(get, multiprocess=True, workers=1)

    results = []
    for result in pipeline():
        results.append(result)
        print(f"extracted: {type(result)}")
    return results
