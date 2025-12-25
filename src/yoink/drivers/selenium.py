import json
import os
import time
from abc import ABC
from io import BytesIO
from typing import Any, Callable, Dict, List, Mapping, Optional

import yaml
from selenium.common.exceptions import (ElementClickInterceptedException,
                                        NoSuchElementException,
                                        StaleElementReferenceException,
                                        TimeoutException, WebDriverException)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.remote_connection import RemoteConnection
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import Select, WebDriverWait

# from yoink.core.utilities.format_utils import (
from yoink.common import extract_code_from_funct
from yoink.drivers.base import (JS_GET_INTERACTIVES, JS_GET_SCROLLABLE_PARENT,
                                JS_WAIT_DOM_IDLE, BaseDriver, DOMNode,
                                InteractionType, PossibleInteractionsByXpath,
                                ScrollDirection)
from yoink.exceptions import (AmbiguousException, CannotBackException,
                              NoElementException)

ATTACH_MOVE_LISTENER = """
if (!window._yoink_move_listener) {
    window._yoink_move_listener = function() {
        const bbs = document.querySelectorAll('.yoink-highlight');
        bbs.forEach(bb => {
            const rect = bb._tracking.getBoundingClientRect();
            bb.style.top = rect.top + 'px';
            bb.style.left = rect.left + 'px';
            bb.style.width = rect.width + 'px';
            bb.style.height = rect.height + 'px';
        });
    };
    window.addEventListener('scroll', window._yoink_move_listener);
    window.addEventListener('resize', window._yoink_move_listener);
}
"""

REMOVE_HIGHLIGHT = """
if (window._yoink_move_listener) {
    window.removeEventListener('scroll', window._yoink_move_listener);
    window.removeEventListener('resize', window._yoink_move_listener);
    delete window._yoink_move_listener;
}
arguments[0].filter(a => a).forEach(a => a.style.cssText = a.dataset.originalStyle || '');
document.querySelectorAll('.yoink-highlight').forEach(a => a.remove());
"""


class XPathResolved(ABC):
    def __init__(self, xpath: str, driver: Any, element: WebElement) -> None:
        self.xpath = xpath
        self._driver = driver
        self.element = element
        super().__init__()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._driver.switch_default_frame()


class SeleniumDriver(BaseDriver):
    driver: WebDriver
    last_hover_xpath: Optional[str] = None

    def __init__(
        self,
        url: Optional[str] = None,
        get_selenium_driver: Optional[Callable[[], WebDriver]] = None,
        headless: bool = True,
        user_data_dir: Optional[str] = None,
        width: Optional[int] = 1080,
        height: Optional[int] = 1080,
        options: Optional[Options] = None,
        driver: Optional[WebDriver] = None,
        log_waiting_time: bool = False,
        waiting_completion_timeout: int = 10,
        remote_connection: Optional["BrowserbaseRemoteConnection"] = None,
    ) -> None:
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.width = width
        self.height = height
        self.options = options
        self.driver = driver
        self.log_waiting_time = log_waiting_time
        self.waiting_completion_timeout = waiting_completion_timeout
        self.remote_connection = remote_connection
        super().__init__(url, get_selenium_driver)

    #   Default code to init the driver.
    #   Before making any change to this, make sure it is compatible with code_for_init, which parses the code of this function
    #   These imports are necessary as they will be pasted to the output
    def default_init_code(self) -> Any:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        from yoink.drivers.base import JS_SETUP_GET_EVENTS

        if self.options:
            chrome_options = self.options
        else:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument("--headless=new")
            if self.user_data_dir:
                chrome_options.add_argument(f"--user-data-dir={self.user_data_dir}")
            user_agent = "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36"
            chrome_options.add_argument(f"user-agent={user_agent}")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.page_load_strategy = "normal"
        # allow access to cross origin iframes
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-site-isolation-trials")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        if self.remote_connection:
            chrome_options.add_experimental_option("debuggerAddress", "localhost:9223")
            self.driver = webdriver.Remote(self.remote_connection, options=chrome_options)
        elif self.driver is None:
            self.driver = webdriver.Chrome(options=chrome_options)

            # 538: browserbase implementation - move execute_cdp_cmd to inner block to avoid error
            # AttributeError: 'WebDriver' object has no attribute 'execute_cdp_cmd'
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": JS_SETUP_GET_EVENTS},
            )
        self.resize_driver(self.width, self.height)
        return self.driver

    def code_for_init(self) -> str:
        init_lines = extract_code_from_funct(self.init_function)
        code_lines = []
        keep_next = True
        for line in init_lines:
            if "--user-data-dir" in line:
                line = line.replace(f"{{self.user_data_dir}}", f'"{self.user_data_dir}"')
            if "if" in line:
                if ("headless" in line and not self.headless) or (
                    "user_data_dir" in line and self.user_data_dir is None
                ):
                    keep_next = False
            elif keep_next:
                if "self" not in line:
                    code_lines.append(line.strip())
            else:
                keep_next = True
        code_lines.append(self.code_for_resize(self.width, self.height))
        return "\n".join(code_lines) + "\n"

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.destroy()

    def get_driver(self) -> WebDriver:
        return self.driver

    def resize_driver(self, width: int | None, height: int | None) -> None:
        if width is None and height is None:
            return None
        # Selenium is only being able to set window size and not viewport size
        self.driver.set_window_size(width, height)
        viewport_height = self.driver.execute_script("return window.innerHeight;")

        height_difference = height - viewport_height
        self.driver.set_window_size(width, height + height_difference)
        self.width = width
        self.height = height

    def code_for_resize(self, width: int | None, height: int | None) -> str:
        return f"""
driver.set_window_size({width}, {height})
viewport_height = driver.execute_script("return window.innerHeight;")
height_difference = {height} - viewport_height
driver.set_window_size({width}, {height} + height_difference)
"""

    def get_url(self) -> Optional[str]:
        if self.driver.current_url == "data:,":
            return None
        return self.driver.current_url

    def code_for_get(self, url: str) -> str:
        return f'driver.get("{url}")'

    def get(self, url: str) -> None:
        self.driver.get(url)

    def back(self) -> None:
        if self.driver.execute_script("return !document.referrer"):
            raise CannotBackException()
        self.driver.back()

    def code_for_back(self) -> None:
        return "driver.back()"

    def get_html(self) -> str:
        return self.driver.page_source

    def get_screenshot_as_png(self) -> bytes:
        return self.driver.get_screenshot_as_png()

    def destroy(self) -> None:
        self.driver.quit()

    def maximize_window(self) -> None:
        self.driver.maximize_window()

    def check_visibility(self, xpath: str) -> bool:
        try:
            # Done manually here to avoid issues
            element = self.resolve_xpath(xpath).element
            res = element is not None and element.is_displayed() and element.is_enabled()
            self.switch_default_frame()
            return res
        except:
            return False

    def switch_frame(self, xpath: str) -> None:
        iframe = self.driver.find_element(By.XPATH, xpath)
        self.driver.switch_to.frame(iframe)

    def switch_default_frame(self) -> None:
        self.driver.switch_to.default_content()

    def switch_parent_frame(self) -> None:
        self.driver.switch_to.parent_frame()

    def resolve_xpath(self, xpath: Optional[str]) -> XPathResolved:
        if not xpath:
            raise NoSuchElementException("xpath is missing")
        before, sep, after = xpath.partition("iframe")
        if len(before) == 0:
            return None
        if len(sep) == 0:
            res = self.driver.find_element(By.XPATH, before)
            res = XPathResolved(xpath, self, res)
            return res
        self.switch_frame(before + sep)
        element = self.resolve_xpath(after)
        return element

    def exec_code(
        self,
        code: str,
        globals: dict[str, Any] = None,
        locals: Mapping[str, object] = None,
    ):
        # Ensures that numeric values are quoted to avoid issues with YAML parsing
        code = quote_numeric_yaml_values(code)

        data = yaml.safe_load(code)
        if not isinstance(data, List):
            data = [data]
        for item in data:
            for action in item["actions"]:
                action_name = action["action"]["name"]
                args = action["action"]["args"]
                xpath = args.get("xpath", None)

                match action_name:
                    case "click":
                        self.click(xpath)
                    case "setValue":
                        self.set_value(xpath, args["value"])
                    case "setValueAndEnter":
                        self.set_value(xpath, args["value"], True)
                    case "dropdownSelect":
                        self.dropdown_select(xpath, args["value"])
                    case "hover":
                        self.hover(xpath)
                    case "scroll":
                        self.scroll(
                            xpath,
                            ScrollDirection.from_string(args.get("value", "DOWN")),
                        )
                    case "failNoElement":
                        raise NoElementException("No element: " + args["value"])
                    case "failAmbiguous":
                        raise AmbiguousException("Ambiguous: " + args["value"])
                    case _:
                        raise ValueError(f"Unknown action: {action_name}")

                self.wait_for_idle()

    def execute_script(self, js_code: str, *args) -> Any:
        return self.driver.execute_script(js_code, *args)

    def scroll_up(self) -> None:
        self.scroll(direction=ScrollDirection.UP)

    def scroll_down(self) -> None:
        self.scroll(direction=ScrollDirection.DOWN)

    def code_for_execute_script(self, js_code: str, *args) -> str:
        return f"driver.execute_script({js_code}, {', '.join(str(arg) for arg in args)})"

    def hover(self, xpath: str) -> None:
        with self.resolve_xpath(xpath) as element_resolved:
            self.last_hover_xpath = xpath
            ActionChains(self.driver).move_to_element(element_resolved.element).perform()

    def scroll_page(self, direction: ScrollDirection = ScrollDirection.DOWN) -> None:
        self.driver.execute_script(direction.get_page_script())

    def get_scroll_anchor(self, xpath_anchor: Optional[str] = None) -> WebElement:
        with self.resolve_xpath(xpath_anchor or self.last_hover_xpath) as element_resolved:
            element = element_resolved.element
            parent = self.driver.execute_script(JS_GET_SCROLLABLE_PARENT, element)
            scroll_anchor = parent or element
            return scroll_anchor

    def get_scroll_container_size(self, scroll_anchor: WebElement):
        container = self.driver.execute_script(JS_GET_SCROLLABLE_PARENT, scroll_anchor)
        if container:
            return (
                self.driver.execute_script(
                    "const r = arguments[0].getBoundingClientRect(); return [r.width, r.height]",
                    scroll_anchor,
                ),
                True,
            )
        return (
            self.driver.execute_script(
                "return [window.innerWidth, window.innerHeight]",
            ),
            False,
        )

    def is_bottom_of_page(self) -> bool:
        return not self.can_scroll(direction=ScrollDirection.DOWN)

    def can_scroll(
        self,
        xpath_anchor: Optional[str] = None,
        direction: ScrollDirection = ScrollDirection.DOWN,
    ) -> bool:
        try:
            scroll_anchor = self.get_scroll_anchor(xpath_anchor)
            return self.driver.execute_script(
                direction.get_script_element_is_scrollable(),
                scroll_anchor,
            )
        except NoSuchElementException:
            return self.driver.execute_script(direction.get_script_page_is_scrollable())

    def scroll(
        self,
        xpath_anchor: Optional[str] = None,
        direction: ScrollDirection = ScrollDirection.DOWN,
        scroll_factor=0.75,
    ) -> None:
        try:
            scroll_anchor = self.get_scroll_anchor(xpath_anchor)
            size, is_container = self.get_scroll_container_size(scroll_anchor)
            scroll_xy = direction.get_scroll_xy(size, scroll_factor)
            if is_container:
                ActionChains(self.driver).move_to_element(scroll_anchor).scroll_from_origin(
                    ScrollOrigin(scroll_anchor, 0, 0), scroll_xy[0], scroll_xy[1]
                ).perform()
            else:
                ActionChains(self.driver).scroll_by_amount(scroll_xy[0], scroll_xy[1]).perform()
            if xpath_anchor:
                self.last_hover_xpath = xpath_anchor
        except NoSuchElementException:
            self.scroll_page(direction)

    def click(self, xpath: str) -> None:
        with self.resolve_xpath(xpath) as element_resolved:
            element = element_resolved.element
            self.last_hover_xpath = xpath
            try:
                element.click()
            except ElementClickInterceptedException:
                try:
                    # Move to the element and click at its position
                    ActionChains(self.driver).move_to_element(element).click().perform()
                except WebDriverException as click_error:
                    raise Exception(f"Failed to click at element coordinates of {xpath} : {str(click_error)}")
            except Exception as e:
                import traceback

                traceback.print_exc()
                raise Exception(f"An unexpected error occurred when trying to click on {xpath}: {str(e)}")

    def set_value(self, xpath: str, value: str, enter: bool = False) -> None:
        with self.resolve_xpath(xpath) as element_resolved:
            elem = element_resolved.element
            try:
                self.last_hover_xpath = xpath
                if elem.tag_name == "select":
                    # use the dropdown_select to set the value of a select
                    return self.dropdown_select(xpath, value)
                if elem.tag_name == "input" and elem.get_attribute("type") == "file":
                    # set the value of a file input
                    return self.upload_file(xpath, value)

                elem.clear()
            except:
                # might not be a clearable element, but global click + send keys can still success
                pass

        self.click(xpath)

        (
            ActionChains(self.driver)
            .key_down(Keys.CONTROL)
            .send_keys("a")
            .key_up(Keys.CONTROL)
            .send_keys(Keys.DELETE)  # clear the input field
            .send_keys(value)
            .perform()
        )
        if enter:
            ActionChains(self.driver).send_keys(Keys.ENTER).perform()

    def dropdown_select(self, xpath: str, value: str) -> None:
        with self.resolve_xpath(xpath) as element_resolved:
            element = element_resolved.element
            self.last_hover_xpath = xpath

            if element.tag_name != "select":
                print(f"Cannot use dropdown_select on {element.tag_name}, falling back to simple click on {xpath}")
                return self.click(xpath)

            select = Select(element)
            try:
                select.select_by_value(value)
            except NoSuchElementException:
                select.select_by_visible_text(value)

    def upload_file(self, xpath: str, file_path: str) -> None:
        with self.resolve_xpath(xpath) as element_resolved:
            element = element_resolved.element
            self.last_hover_xpath = xpath
            element.send_keys(file_path)

    def perform_wait(self, duration: float) -> None:
        import time

        time.sleep(duration)

    def is_idle(self) -> bool:
        active = 0
        logs = self.driver.get_log("performance")
        active = 0
        request_ids = set()
        for log in logs:
            log_json = json.loads(log["message"])["message"]
            method = log_json["method"]
            if method == "Network.requestWillBeSent":
                request_ids.add(log_json["params"]["requestId"])
            elif method in ("Network.loadingFinished", "Network.loadingFailed"):
                request_ids.discard(log_json["params"]["requestId"])
            elif method in ("Page.frameStartedLoading", "Browser.downloadWillBegin"):
                active += 1
            elif method == "Page.frameStoppedLoading":
                active -= 1
            elif method == "Browser.downloadProgress" and log_json["params"]["state"] in (
                "completed",
                "canceled",
            ):
                active -= 1

        return len(request_ids) == 0 and active <= 0

    def wait_for_dom_stable(self, timeout=10) -> None:
        self.driver.execute_script(JS_WAIT_DOM_IDLE, max(0, round(timeout * 1000)))

    def wait_for_idle(self) -> None:
        t = time.time()
        elapsed = 0
        try:
            WebDriverWait(self.driver, self.waiting_completion_timeout).until(lambda d: self.is_idle())
            elapsed = time.time() - t
            self.wait_for_dom_stable(self.waiting_completion_timeout - elapsed)
        except TimeoutException:
            pass

        total_elapsed = time.time() - t
        if self.log_waiting_time or total_elapsed > 10:
            print(
                f"Waited {total_elapsed}s for browser being idle ({elapsed} for network + {total_elapsed - elapsed} for DOM)"
            )

    def get_capability(self) -> str:
        return SELENIUM_PROMPT_TEMPLATE

    def get_tabs(self) -> str:
        driver = self.driver
        window_handles = driver.window_handles
        # Store the current window handle (focused tab)
        current_handle = driver.current_window_handle
        tab_info = []
        tab_id = 0

        for handle in window_handles:
            # Switch to each tab
            driver.switch_to.window(handle)

            # Get the title of the current tab
            title = driver.title

            # Check if this is the focused tab
            if handle == current_handle:
                tab_info.append(f"{tab_id} - [CURRENT] {title}")
            else:
                tab_info.append(f"{tab_id} - {title}")

            tab_id += 1

        # Switch back to the original tab
        driver.switch_to.window(current_handle)

        tab_info = "\n".join(tab_info)
        tab_info = "Tabs opened:\n" + tab_info
        return tab_info

    def switch_tab(self, tab_id: int) -> None:
        driver = self.driver
        window_handles = driver.window_handles

        # Switch to the tab with the given id
        driver.switch_to.window(window_handles[tab_id])
