import time
import pytest
import os
import allure
import datetime
import string
import random
import json
import zipfile
import base64
import configparser
import inspect
import importlib.util
from typing import Optional, Any

from allure_commons.types import AttachmentType
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

import LoggerReports
import Browser


# Helper for logging and allure
def log_and_report(message: str, function_name: str, screenshot: bool = False, driver: Optional[Any] = None, trace: Optional[Any] = None, report: Optional[Any] = None) -> str:
    """Log a message and attach to report/allure optionally with a screenshot.

    Parameters:
    - message (str): Message to log.
    - function_name (str): Name of the function or step associated with this message.
    - screenshot (bool): If True and driver provided, capture and attach screenshot.
    - driver (WebDriver|None): Selenium WebDriver instance used to capture screenshots.
    - trace: Optional trace/logger object used by the test framework for additional reporting.
    - report: Optional report object (for example an allure or custom reporter) to record step.

    This helper centralizes logging and reporting behavior used across the UI test helpers.
    It will not raise exceptions; any errors while taking screenshots are logged via LoggerReports.

    Returns:
        str: the original message (useful for passing into asserts as the message).
    """
    LoggerReports.logger.info(message)
    if report:
        report.step(message)
        allure.step(message)
    if screenshot and driver:
        allure.step("Please find below the screenshot for the same:")
        WebRunner().screenshot(driver, function_name, trace)
        allure.attach(driver.get_screenshot_as_png(), name=message, attachment_type=AttachmentType.PNG)
    return message


# Decorator for logging steps
def log_step(step_name):
    """Decorator to log START and SUCCESS/FAIL around a function execution.

    Usage:
        @log_step("My step")
        def my_func(...):
            ...

    The decorator logs the start and success messages. On exception it captures a screenshot
    (if a driver is passed as the second argument to the wrapped function) and re-raises the exception.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            log_and_report(f"START: {step_name}", function_name=step_name)
            try:
                result = func(*args, **kwargs)
                log_and_report(f"SUCCESS: {step_name}", function_name=step_name)
                return result
            except Exception as e:
                driver = args[1] if len(args) > 1 else None
                log_and_report(f"FAIL: {step_name} | {e}", screenshot=True, driver=driver, function_name=step_name)
                raise

        return wrapper

    return decorator


by_map = {
    "xpath": By.XPATH,
    "css": By.CSS_SELECTOR,
    "id": By.ID,
    "name": By.NAME,
    "tag": By.TAG_NAME,
    "link": By.LINK_TEXT,
    "partial": By.PARTIAL_LINK_TEXT,
    "class": By.CLASS_NAME
}


class WebRunner:
    """Collection of generic Selenium WebDriver helper methods used across UI tests.

    Attributes:
        timeout (int): default wait timeout taken from Browser().timeout.
    """
    timeout = Browser().timeout

    # ---------------- Browser Setup ----------------
    def open_browser(self, browser: str, trace):
        """Open a browser instance using the project's Browser helper.

        Parameters:
            browser (str): Browser name (e.g., 'chrome', 'firefox').
            trace: Logging/trace object passed to Browser.

        Returns:
            WebDriver: Selenium WebDriver instance on success.

        Raises:
            Exception: Re-raises exceptions from Browser().call_browser after logging.
        """
        function_name = self.open_browser.__name__
        test_start_timestamp = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        log_and_report("Run started at | " + test_start_timestamp + " |", function_name)

        driver = None
        try:
            driver = Browser().call_browser(browser, trace)
            log_and_report(f"{browser} browser launched successfully", function_name, trace=trace)
        except Exception as e:
            log_and_report(f"{browser} browser launch failed", function_name, screenshot=True, driver=driver, trace=trace)
            raise
        self.driver = driver
        return self.driver

    # ---------------- Navigation ----------------
    def navigate_to_url(self, driver, base_url: str, trace):
        """Navigate the provided driver to the given URL.

        Parameters:
            driver (WebDriver): Selenium WebDriver instance.
            base_url (str): URL to navigate to.
            trace: trace/logger object used for reporting.

        On failure the function logs and fails the pytest test.
        """
        try:
            driver.get(base_url)
            log_and_report(f"Navigated to {base_url} successfully", function_name=self.navigate_to_url.__name__)
        except Exception as e:
            log_and_report(f"Failed to navigate to {base_url}", function_name=self.navigate_to_url.__name__, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    # ---------------- Element Actions ----------------
    def web_locator(self, driver, element_value, mode, function_name: str, trace, report):
        """Locate a single element and return it.

        Parameters:
            driver (WebDriver): Selenium WebDriver instance.
            element_value (str): Locator string (xpath/css/id/etc.).
            mode (str): Key describing locator type (e.g., 'xpath', 'css', 'id').
            function_name (str): Name of calling function (used for logging).
            trace: trace/logger object.
            report: optional report object for steps.

        Returns:
            WebElement: The found WebElement.

        On failure logs a screenshot and attaches info to report.
        """
        try:
            WebDriverWait(driver, self.timeout).until(ec.presence_of_element_located((by_map.get(mode.lower(), By.XPATH), element_value)))
            locator = driver.find_element(by_map.get(mode.lower(), By.XPATH), element_value)
            self.scroll_to_element(driver, locator, function_name, trace, report)
            log_and_report(f"Located element for {function_name}", function_name)
            return locator
        except Exception as e:
            log_and_report(f"Failed to locate element for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)

    def web_locators_list(self, driver, element_value, mode, function_name, trace, report):
        """Locate multiple elements and return a list.

        Parameters:
            driver (WebDriver): Selenium WebDriver instance.
            element_value (str): Locator string.
            mode (str): Locator mode key.
            function_name (str): Caller name for logging.
            trace, report: optional reporting objects.

        Returns:
            list[WebElement]: Found elements or empty list on failure.
        """
        try:
            WebDriverWait(driver, self.timeout).until(ec.presence_of_all_elements_located((by_map.get(mode.lower(), By.XPATH), element_value)))
            locators = driver.find_elements(by_map.get(mode.lower(), By.XPATH), element_value)
            log_and_report(f"Located elements list for {function_name}", function_name)
            return locators
        except Exception as e:
            log_and_report(f"Failed to locate elements list for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            return []

    def javascript_click(self, driver, locator, function_name, trace, report):
        """Click an element using JavaScript execution.

        Using JS click can bypass overlay/visibility issues that prevent normal click.

        Parameters:
            driver (WebDriver): Selenium WebDriver instance.
            locator (WebElement): Element to click.
            function_name (str): Caller name for logging.
            trace, report: optional reporting objects.
        """
        try:
            self.scroll_to_element(driver, locator, function_name, trace, report)
            driver.execute_script("arguments[0].click();", locator)
            log_and_report(f"Clicked element using JavaScript_Click function for {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to click element using JavaScript for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def click(self, driver, locator, function_name: str, trace, report):
        """Click an element using a safe wait-then-click pattern.

        Tries to use an explicit wait for clickability first, otherwise falls back to element.click().
        """
        try:
            try:
                self.scroll_to_element(driver, locator, function_name, trace, report)
                WebDriverWait(driver, self.timeout).until(ec.element_to_be_clickable(locator)).click()
            except Exception as e:
                locator.click()
            log_and_report(f"Clicked element for {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to click element for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def explicit_click(self, driver, locator, function_name: str, trace, report):
        """Explicitly wait until an element is clickable and click it.

        Parameters and error handling similar to `click` but will not fallback to direct click.
        """
        try:
            WebDriverWait(driver, self.timeout).until(ec.element_to_be_clickable(locator)).click()
            log_and_report(f"Clicked element for {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to click element for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def input_clear(self, driver, locator, input_value: str, function_name: str, trace, report):
        """Clear an input and type a new value robustly.

        Clears the element and sends a series of BACKSPACE keys to ensure previous content removed before typing.
        """
        try:
            self.scroll_to_element(driver, locator, function_name, trace, report)
            element = WebDriverWait(driver, self.timeout).until(ec.visibility_of(locator))
            element.clear()
            locator.send_keys([Keys.BACKSPACE] * 200)
            element.send_keys(input_value)
            log_and_report(f"Input '{input_value}' in {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to input in {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def input(self, driver, locator, input_value: str, function_name: str, trace, report):
        """Send keys to an element.

        Simple wrapper around WebElement.send_keys with logging and error reporting.
        """
        try:
            self.scroll_to_element(driver, locator, function_name, trace, report)
            locator.send_keys(input_value)
            log_and_report(f"Input '{input_value}' in {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to input in {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def clear_value(self, driver, locator, function_name, trace, report):
        """Clear the value of an input element using JS and WebElement.clear().

        This helps when normal clear() alone isn't sufficient due to framework behaviors.
        """
        try:
            self.scroll_to_element(driver, locator, function_name, trace, report)
            element = WebDriverWait(driver, self.timeout).until(ec.visibility_of(locator))
            driver.execute_script("arguments[0].value = '';", locator)
            element.clear()
            log_and_report(f"Cleared value in {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to clear value in {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    # ---------------- Waits, Visibilities ----------------
    def explicit_wait_presence_of_element(self, driver, element_value, mode, function_name: str, trace):
        """Wait until an element is present in the DOM (not necessarily visible).

        Parameters:
            driver, element_value, mode, function_name, trace: same conventions as other helpers.
        """
        try:
            locator = WebDriverWait(driver, self.timeout).until(ec.presence_of_element_located((by_map.get(mode.lower(), By.XPATH), element_value)))
            self.scroll_to_element(driver, locator, function_name, trace, allure)
            log_and_report(f"Waited for element in {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed waiting for element in {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def is_element_displayed(self, driver, element_value, trace='', report='', mode='xpath'):
        """Check if an element exists and is displayed. Returns boolean.

        Note: implementation tries to find element and call is_displayed, but returns a boolean variable
        that defaults to False. On exceptions, it logs and returns False.
        """
        function_name = self.is_element_displayed.__name__
        is_displayed = False
        try:
            is_displayed = driver.find_element(by_map.get(mode.lower(), By.XPATH), element_value)
            self.scroll_to_element(driver, is_displayed, function_name, trace, report)
            is_displayed.is_displayed()
            log_and_report(f"Waited for element to display on the web page", function_name=function_name)
            return is_displayed
        except Exception as e:
            log_and_report(f"Failed waiting to display on the web page", function_name=function_name, screenshot=True, driver=driver, trace=trace)
            return is_displayed

    def explicit_is_element_displayed(self, driver, element_value, function_name: str = '', trace='', report='', mode='xpath'):
        """Explicitly wait for presence of element and return the web element or None on failure."""
        try:
            is_displayed = WebDriverWait(driver, self.timeout).until(ec.presence_of_element_located((by_map.get(mode.lower(), By.XPATH), element_value)))
            self.scroll_to_element(driver, is_displayed, function_name, trace, report)
            log_and_report(f"Waited for element in {function_name}", function_name)
            return is_displayed
        except Exception as e:
            log_and_report(f"Failed waiting for element in {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            return None

    def explicit_wait_presence_of_element_is_invisible(self, driver, element_value, mode, function_name, trace):
        """Wait until a given element becomes invisible on the page."""
        try:
            WebDriverWait(driver, self.timeout).until(ec.invisibility_of_element_located((by_map.get(mode.lower(), By.XPATH), element_value)))
            log_and_report(f"Waited for element to be invisible in {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed waiting for element to be invisible in {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def is_enabled(self, driver, locator):
        """Return a visible element (used as an 'is enabled' check)."""
        return WebDriverWait(driver, self.timeout).until(ec.visibility_of_element_located(locator))

    def is_visible_on_screen(self, driver, element_value, mode="xpath", wait_time=30):
        """Temporarily reduce implicit wait and check element visibility within a short wait time.

        Returns True if visible, False otherwise.
        """
        function_name = self.is_visible_on_screen.__name__
        try:
            driver.implicitly_wait(1)
            locator = WebDriverWait(driver, wait_time).until(ec.visibility_of_element_located((by_map.get(mode.lower(), By.XPATH), element_value)))
            if locator: driver.execute_script('return arguments[0].scrollIntoView({ behavior: "auto", block: "center", inline: "center" });', locator)
            driver.implicitly_wait(self.timeout)
            log_and_report(f"Element is visible on screen", function_name=self.is_visible_on_screen.__name__)
            return True
        except Exception as e:
            driver.implicitly_wait(self.timeout)
            return False

    def is_visible(self, driver, element_value, mode="xpath"):
        """Check whether element is visible using an explicit wait; return True/False."""
        try:
            WebDriverWait(driver, self.timeout).until(ec.visibility_of_element_located((by_map.get(mode.lower(), By.XPATH), element_value)))
            return True
        except Exception as e:
            return False

    # ---------------- Screenshot ----------------
    def screenshot(self, driver, function_name: str, trace):
        """Capture a screenshot to the failure_screenshots folder and attach to allure.

        Parameters:
            driver (WebDriver): Selenium WebDriver.
            function_name (str): Used as filename for screenshot.
            trace: trace/logger used for step logging.
        """
        try:
            screenshot_path = os.path.abspath(__file__ + "/../../../") + '/failure_screenshots/'
            driver.save_screenshot(screenshot_path + function_name + ".png")
            allure.attach(driver.get_screenshot_as_png(), name=function_name, attachment_type=AttachmentType.PNG)
            # Use keyword arguments to match signature: message, function_name, screenshot=False, driver=None, trace=None
            log_and_report(f"Screenshot captured for {function_name}", function_name=function_name, trace=trace)
        except Exception as e:
            log_and_report(f"Failed to capture screenshot for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)

    # ---------------- Dropdown ----------------
    def select_dropdown(self, driver, locator, mode, value, function_name: str, trace, report):
        """Select an option from a <select> element by index, value or visible text.

        Parameters mirror those used elsewhere in this helper class.
        """
        try:
            select = Select(locator)
            if mode == "index":
                select.select_by_index(int(value))
            elif mode == "value":
                select.select_by_value(value)
            elif mode == "visible_text":
                select.select_by_visible_text(value)
            log_and_report(f"Selected '{str(value)}' in dropdown for {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to select dropdown for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    # ---------------- Hover ----------------
    def hover_to(self, driver, locator, function_name: str, trace, report, mode="xpath"):
        """Move the mouse over the provided element using ActionChains."""
        try:
            element = WebDriverWait(driver, self.timeout).until(ec.presence_of_element_located((by_map.get(mode.lower(), By.XPATH), locator)))
            ActionChains(driver).move_to_element(element).perform()
            log_and_report(f"Hovered to element for {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to hover for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    # ---------------- drag and drop ----------------
    def drag_drop(self, driver, source, destination, function_name, trace, report):
        """Drag source element and drop onto destination element."""
        try:
            ActionChains(driver).drag_and_drop(source, destination).perform()
            log_and_report(f"Dragged and dropped element for {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to drag and drop for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    # ---------------- Get Text, Get Value, Asserts ----------------
    def get_text(self, driver, locator, function_name: str, trace, report):
        """Return the text content of an element with logging and error handling."""
        try:
            text = locator.text
            log_and_report(f"Got text '{str(text)}' for {function_name}", function_name)
            return text
        except Exception as e:
            log_and_report(f"Failed to get text for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def get_value(self, driver, element_value, attribute, function_name: str, trace, report, mode='xpath'):
        """Get the attribute value from an element located by the given locator string."""
        try:
            WebDriverWait(driver, self.timeout).until(ec.presence_of_element_located((by_map.get(mode.lower(), By.XPATH), element_value)))
            value = driver.find_element(by_map.get(mode.lower(), By.XPATH), element_value).get_attribute(attribute)
            log_and_report(f"Got value '{str(value)}' for {function_name}", function_name)
            return value
        except Exception as e:
            log_and_report(f"Failed to get value for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def assert_element_text(self, driver, locator, element_text, function_name: str, trace, report):
        """Assert that a WebElement's text equals the expected text and fail the test on mismatch."""
        try:
            actual_text = locator.text
            assert actual_text == element_text, log_and_report(f"Text mismatch: Expected '{element_text}', Found '{actual_text}'", function_name)
            log_and_report(f"Asserted text '{str(element_text)}' for {function_name}", function_name)
        except AssertionError as ae:
            log_and_report(f"Assertion failed for {function_name}: {ae}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()
        except Exception as e:
            log_and_report(f"Failed to assert text for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def explicit_assert_element_text(self, driver, element_value, element_text, function_name, trace, report):
        """Explicitly wait for an element then assert its text; supports dynamic placeholder.

        If element_text is None or 'dynamic', asserts the text is not "--".
        """
        try:
            web_element = WebDriverWait(driver, self.timeout).until(ec.presence_of_element_located((By.XPATH, element_value)))
            if element_text is None or element_text is 'dynamic':
                assert web_element.text != "--", log_and_report(f"Text mismatch: Expected '{element_text}', Found '{web_element.text}'", function_name)
            else:
                assert web_element.text == element_text, log_and_report(f"Text mismatch: Expected '{element_text}', Found '{web_element.text}'", function_name)

            log_and_report(f"Asserted text '{str(element_text)}' for {function_name}", function_name)
        except AssertionError as ae:
            log_and_report(f"Assertion failed for {function_name}: {ae}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()
        except Exception as e:
            log_and_report(f"Failed to assert text for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    # ---------------- Tear Down ----------------
    def tear_down(self, driver, trace, report):
        """Quit the browser and log the result. Fails the test if quit fails."""
        try:
            driver.quit()
            log_and_report("Browser closed successfully", function_name=self.tear_down.__name__)
        except Exception as e:
            log_and_report("Failed to close browser", function_name=self.tear_down.__name__, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def close_all_windows_except_current(self, driver, trace, report):
        """Close all browser windows except the current one using window handles."""
        try:
            current = driver.current_window_handle
            for window in driver.window_handles:
                if window != current:
                    driver.switch_to.window(window)
                    driver.close()

            driver.switch_to.window(current)
            log_and_report("Closed all windows except current window", function_name=self.close_all_windows_except_current.__name__, screenshot=True, driver=driver, trace=trace)
        except Exception as e:
            log_and_report("Failed to close all windows except current", function_name=self.close_all_windows_except_current.__name__, screenshot=True, driver=driver, trace=trace)

    # ---------------- Alerts ----------------
    def confirm_alert(self, driver, function_name, trace, report):
        """Wait for an alert to be present and accept it."""
        try:
            WebDriverWait(driver, self.timeout).until(ec.alert_is_present())
            alert = driver.switch_to.alert
            alert.accept()
            log_and_report(f"Confirmed alert for {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to confirm alert for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    # ---------------- Frames, Windows ----------------
    def find_frame_by_id(self, driver, frame_id, trace, report):
        """Wait for a frame to be available by id and switch to it."""
        try:
            WebDriverWait(driver, self.timeout).until(ec.frame_to_be_available_and_switch_to_it((By.ID, frame_id)))
            log_and_report(f"Switched to frame with ID: {frame_id}", function_name=self.find_frame_by_id.__name__)
        except Exception as e:
            log_and_report(f"Failed to switch to frame with ID: {frame_id}", function_name=self.find_frame_by_id.__name__, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def find_frame_by_name(self, driver, frame_name, trace, report):
        """Wait for a frame to be available by name and switch to it."""
        try:
            WebDriverWait(driver, self.timeout).until(ec.frame_to_be_available_and_switch_to_it((By.NAME, frame_name)))
            log_and_report(f"Switched to frame with Name: {frame_name}", function_name=self.find_frame_by_name.__name__)
        except Exception as e:
            log_and_report(f"Failed to switch to frame with Name: {frame_name}", function_name=self.find_frame_by_name.__name__, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def switch_previous_window(self, driver, trace, report):
        """Switch to the previous window in the window_handles list."""
        try:
            windows_count = len(driver.window_handles)
            previous_window = driver.window_handles[windows_count - 2]
            driver.switch_to.window(previous_window)
            log_and_report("Switched to previous window", function_name=self.switch_previous_window.__name__)
        except Exception as e:
            log_and_report("Failed to switch to previous window", function_name=self.switch_previous_window.__name__, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def switch_next_window(self, driver, trace, report):
        """Switch to the most recently opened window."""
        try:
            windows_count = len(driver.window_handles)
            next_window = driver.window_handles[windows_count - 1]
            driver.switch_to.window(next_window)
            log_and_report("Switched to next window", function_name=self.switch_next_window.__name__)
        except Exception as e:
            log_and_report("Failed to switch to next window", function_name=self.switch_next_window.__name__, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def switch_first_window(self, driver, trace, report):
        """Switch to the first non-main window (index 1)."""
        try:
            first_window = driver.window_handles[1]
            driver.switch_to.window(first_window)
            log_and_report("Switched to first window", function_name=self.switch_first_window.__name__)
        except Exception as e:
            log_and_report("Failed to switch to first window", function_name=self.switch_first_window.__name__, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def switch_second_window(self, driver, trace, report):
        """Switch to the second non-main window (index 2)."""
        try:
            second_window = driver.window_handles[2]
            driver.switch_to.window(second_window)
            log_and_report("Switched to second window", function_name=self.switch_second_window.__name__)
        except Exception as e:
            log_and_report("Failed to switch to second window", function_name=self.switch_second_window.__name__, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    # ---------------- General ----------------
    def genearte_word(self, driver, prefix, function_name, trace, report):
        """Generate a timestamped 'word' value using the provided prefix.

        Returns a string combining the prefix and current datetime formatted.
        """
        try:
            word = prefix + datetime.datetime.now().strftime("%m/%d,%H:%M:%S")
            log_and_report(f"Generated word '{str(word)}' for {function_name}", function_name)
            return word
        except Exception as e:
            log_and_report(f"Failed to generate word for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def generate_password(self, driver, length, function_name, trace, report):
        """Return a randomly generated password of given length using a broad character set.

        Parameters:
            length (int): Desired password length.

        Returns:
            str: Randomly generated password.
        """
        try:
            letters = string.ascii_lowercase + string.ascii_uppercase + string.ascii_letters + string.punctuation + string.digits
            log_and_report(f"Successfully generated password for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            return ''.join(random.choice(letters) for i in range(length))
        except Exception as e:
            log_and_report(f"Failed to generate password for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def press_enter(self, driver, locator, function_name, trace, report):
        """Send ENTER key to the provided element."""
        try:
            locator.send_keys(Keys.ENTER)
            log_and_report(f"Pressed ENTER key for {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to press ENTER key for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def press_esc_key(self, driver, function_name, trace, report):
        """Send ESCAPE key to the current browser using ActionChains."""
        try:
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            log_and_report(f"Pressed ESCAPE key for {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to press ESCAPE key for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def press_backspace_key(self, driver, function_name, trace, report):
        """Send BACKSPACE key to the current browser using ActionChains."""
        try:
            ActionChains(driver).send_keys(Keys.BACKSPACE).perform()
            log_and_report(f"Pressed BACKSPACE key for {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to press BACKSPACE key for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def move_the_mouse_by_offset(self, driver, locator, x_coordinate, y_coordinate, function_name, trace, report):
        """Move the mouse to an element then offset by x/y pixels."""
        try:
            ActionChains(driver).move_to_element(locator).move_by_offset(x_coordinate, y_coordinate).perform()
            log_and_report(f"Moved mouse by offset ({x_coordinate}, {y_coordinate}) for {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to move mouse by offset for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def scroll_to_element(self, driver, locator, function_name, trace, report):
        """Scroll the page to make the element visible and centered in viewport."""
        try:
            if locator: driver.execute_script('return arguments[0].scrollIntoView({ behavior: "auto", block: "center", inline: "center" });', locator)
        except Exception as e:
            log_and_report(f"Failed to scroll to element for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def json_file_reader(self, file_path):
        """Read and return JSON content from a file path. Returns parsed JSON or prints exception."""
        try:
            with open(file_path) as f:
                data = json.load(f)
            return data
        except Exception as e:
            print(e)

    def zip_dir(self, directory, zipname):
        """Zip the contents of a directory into a zip file named zipname.

        The zip will contain the directory as the root folder inside the archive.
        """

        if os.path.exists(directory):
            outZipFile = zipfile.ZipFile(zipname, 'w', zipfile.ZIP_DEFLATED)

            # The root directory within the ZIP file.
            rootdir = os.path.basename(directory)

            for dirpath, dirnames, filenames in os.walk(directory):

                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    parentpath = os.path.relpath(filepath, directory)
                    arcname = os.path.join(rootdir, parentpath)
                    outZipFile.write(filepath, arcname)

            outZipFile.close()

    def upload_image_or_file(self, driver, trace, report, function_name, drop_location, file_path, file_type):
        """Upload a file or image into a web dropzone by synthesizing a drag/drop event.

        Parameters:
            driver (WebDriver): Selenium WebDriver instance.
            trace, report: logging/report objects.
            function_name (str): Step name used for logging.
            drop_location (str): XPath to the drop target element.
            file_path (str): Local filesystem path to the file to upload.
            file_type (str): 'image' or 'json' to help set content-type header in the synthetic file.
        """
        try:
            drop_zone = driver.find_element(By.XPATH, drop_location)
            time.sleep(1)
            file_path = file_path

            with open(file_path, "rb") as file:
                file_data = file.read()
                file_base64 = base64.b64encode(file_data).decode()

            js_script = """
                           var fileName = arguments[0];
                           var fileDataBase64 = arguments[1];
                           var contentType = arguments[2];
                           var dropZone = arguments[3];

                           function base64ToFile(base64, filename, contentType) {
                               var byteString = atob(base64.split(',')[1]);
                               var ab = new ArrayBuffer(byteString.length);
                               var ia = new Uint8Array(ab);
                               for (var i = 0; i < byteString.length; i++) {
                                   ia[i] = byteString.charCodeAt(i);
                               }
                               var blob = new Blob([ab], { type: contentType });
                               return new File([blob], filename, { type: contentType });
                           }

                           var file = base64ToFile(fileDataBase64, fileName, contentType);
                           var dataTransfer = new DataTransfer();
                           dataTransfer.items.add(file);

                           var event = new DragEvent('drop', {
                               bubbles: true,
                               cancelable: true,
                               dataTransfer: dataTransfer
                           });

                           dropZone.dispatchEvent(event);
                           """
            if file_type == "image":
                file_type = "image/jpeg"
            elif file_type == "json":
                file_type = "application/json"
            driver.execute_script(js_script, os.path.basename(file_path), 'data:image/jpeg;base64,' + file_base64, file_type, drop_zone)
            log_and_report(f"Uploaded image to ({file_path} for {function_name}", function_name)
        except Exception as e:
            log_and_report(f"Failed to upload image/file for {function_name}", function_name, screenshot=True, driver=driver, trace=trace)
            pytest.fail()

    def get_xpath_from_coordinates(self, driver, x, y):
        """Return a rough XPath to the element located at the given client coordinates by executing JS."""
        script = """
        var element = document.elementFromPoint(arguments[0], arguments[1]);
        function getPathTo(element) {
            if (element.tagName == 'HTML') return '/HTML[1]';
            if (element===document.body) return '/HTML[1]/BODY[1]';
            var index = 0;
            var siblings = element.parentNode.childNodes;
            for (var i = 0; i < siblings.length; i++) {
                var sibling = siblings[i];
                if (sibling===element) {
                    return getPathTo(element.parentNode) + '/' + element.tagName + '[' + (index+1) + ']';
                }
                if (sibling.nodeType===1 && sibling.tagName===element.tagName) {
                    index++;
                }
            }
        }
        return getPathTo(element);
        """
        return driver.execute_script(script, x, y)

    def display_log(self, driver, message: str):
        """Inject a floating logger DIV into the page and set its text to the provided message."""
        script = f"""
        let logDiv = document.getElementById('automation-logger');
        if (!logDiv) {{
            logDiv = document.createElement('div');
            logDiv.id = 'automation-logger';
            logDiv.style.position = 'fixed';
            logDiv.style.top = '10px';
            logDiv.style.left = '10px';
            logDiv.style.padding = '10px';
            logDiv.style.background = 'rgba(0,0,0,0.7)';
            logDiv.style.color = 'white';
            logDiv.style.fontSize = '14px';
            logDiv.style.zIndex = 9999;
            logDiv.style.borderRadius = '8px';
            logDiv.style.boxShadow = '0 0 10px rgba(0,0,0,0.5)';
            document.body.appendChild(logDiv);
        }}
        logDiv.innerText = `{message}`;
        """
        driver.execute_script(script)

    def store_failed_xpaths(self, element_value, function_name):
        """Store a failed xpath into a local INI file, recording the failing test location.

        The routine attempts to discover the calling test class and variable name that matched the
        element_value so that the stored key contains a helpful name. On any error this falls back
        to writing into the 'Failed To Locate' section.
        """
        global config, store_coordinates
        try:
            store_coordinates = os.path.join(os.path.abspath(__file__ + "/../../../") + "/test_data/" + "failed_xpaths.ini")
            config = configparser.ConfigParser()
            config.read(store_coordinates)
            stack = inspect.stack()
            caller_frame = stack[2][0]
            cls_name = stack[2][1]
            module_name = os.path.splitext(os.path.basename(cls_name))[0]
            spec = importlib.util.spec_from_file_location(module_name, cls_name)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            var_name = ""
            var_present = False
            try:
                for name, obj in module.__dict__.items():
                    if isinstance(obj, type) and str(module_name) in str(obj):
                        class_attributes = obj.__dict__
                        for var_name, val in class_attributes.items():
                            if val == element_value and "__" not in var_name and "__" not in val:
                                var_present = True
                                break
            except:
                pass
            class_name = caller_frame.f_locals['self'].__class__.__name__
            if var_present:
                function_name = f"{class_name}.{function_name}.{var_name}"
            else:
                function_name = f"{class_name}.{function_name}"
            config["Failed XPaths"][function_name] = f"{element_value}"
            with open(store_coordinates, "w") as file:
                config.write(file)
            print(f"stored failed xpath: {element_value}")
        except Exception as e:
            config["Failed To Locate"]["failed_to_locate"] = f"{element_value}"
            with open(store_coordinates, "w") as file:
                config.write(file)
            print(f"failed to failed xpath for {element_value}")
            print(e)
