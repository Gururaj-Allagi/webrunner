import inspect
import json
import os
import time
import zipfile
import base64
import importlib.util
import string
import random
import datetime
from typing import Optional, Union, List, Dict, Any, Tuple
from functools import wraps

import allure
import configparser
import pytest
from allure_commons.types import AttachmentType
from selenium import webdriver
from selenium.common.exceptions import (NoSuchElementException, TimeoutException, WebDriverException)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager


class WebRunnerError(Exception):
    """Base exception for WebRunner errors"""
    pass


class BrowserConfigurationError(WebRunnerError):
    """Exception for browser configuration issues"""
    pass


class ElementNotFoundError(WebRunnerError):
    """Exception for element not found cases"""
    pass


class WebRunner:
    DEFAULT_TIMEOUT = 30
    DEFAULT_WAIT = 1

    def __init__(self):
        self.driver: Optional[webdriver.Remote] = None
        self._config = self._load_config()

    def _load_config(self) -> configparser.ConfigParser:
        """Load configuration from file"""
        config = configparser.ConfigParser()
        config_path = os.path.join(os.path.abspath(__file__ + "/../../../"), "config.ini")
        config.read(config_path)
        return config

    def retry(max_attempts: int = 3, delay: float = 1.0):
        """Decorator to retry failed operations"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                last_exception = None
                for attempt in range(max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        if attempt < max_attempts - 1:
                            time.sleep(delay)
                raise last_exception
            return wrapper
        return decorator

    def _setup_chrome_options(self, headless: bool = False, download_dir: Optional[str] = None) -> Options:
        """Configure Chrome options"""
        options = Options()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-gpu')
        options.add_argument('--start-maximized')
        
        if headless:
            options.add_argument('--headless')
            options.add_argument("--window-size=1920,1080")
        
        if download_dir:
            prefs = {
                "download.default_directory": download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True
            }
            options.add_experimental_option('prefs', prefs)
        
        return options

    def _setup_firefox_profile(self, download_dir: Optional[str] = None) -> webdriver.FirefoxProfile:
        """Configure Firefox profile"""
        fp = webdriver.FirefoxProfile()
        if download_dir:
            fp.set_preference("browser.download.folderList", 2)
            fp.set_preference("browser.download.manager.showWhenStarting", False)
            fp.set_preference("browser.download.dir", download_dir)
            fp.set_preference("browser.download.useDownloadDir", True)
            fp.set_preference("browser.helperApps.neverAsk.saveToDisk", "attachment/csv")
        fp.set_preference("browser.link.open_newwindow.restriction", 0)
        fp.set_preference("browser.link.open_newwindow", 1)
        return fp

    @retry(max_attempts=3, delay=1)
    def open_browser(self, browser: str, trace: Any) -> webdriver.Remote:
        """Open browser based on configuration"""
        test_start_timestamp = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        trace.logger.info(f"Run started at ||{test_start_timestamp}||")
        
        try:
            browser = browser.lower()
            download_dir = os.path.abspath(__file__ + "/../../../") + "/downloads"
            
            if browser == "chrome":
                options = self._setup_chrome_options()
                self.driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
                
            elif browser == "chrome-headless":
                options = self._setup_chrome_options(headless=True)
                self.driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
                
            elif browser == "chrome-debug":
                options = Options()
                options.add_experimental_option("debuggerAddress", "localhost:9221")
                self.driver = webdriver.Chrome(options=options)
                
            elif browser == "firefox":
                fp = self._setup_firefox_profile(download_dir)
                self.driver = webdriver.Firefox(executable_path=GeckoDriverManager().install(), firefox_profile=fp)
                
            elif browser == "firefox-headless":
                options = webdriver.FirefoxOptions()
                options.add_argument('--headless')
                self.driver = webdriver.Firefox(executable_path=GeckoDriverManager().install(), options=options)
                
            elif browser == "safari":
                self.driver = webdriver.Safari()
                
            else:
                raise BrowserConfigurationError(f"Unsupported browser: {browser}")

            self.driver.implicitly_wait(self.DEFAULT_TIMEOUT)
            trace.logger.info(f"{browser} browser launched successfully")
            return self.driver

        except Exception as e:
            trace.logger.critical(f"Failed to launch {browser} browser")
            trace.logger.exception(e)
            raise BrowserConfigurationError(f"Browser launch failed: {str(e)}")

    def navigate_to_url(self, driver: webdriver.Remote, url: str, trace: Any) -> None:
        """Navigate to specified URL"""
        try:
            driver.get(url)
            trace.logger.info(f"Navigated to {url}")
        except Exception as e:
            trace.logger.error(f"Failed to navigate to {url}")
            trace.logger.exception(e)
            raise WebDriverException(f"Navigation failed: {str(e)}")

    def find_element(self, driver: webdriver.Remote, locator: Tuple[By, str], timeout: int = None) -> WebElement:
        """Find element with explicit wait"""
        timeout = timeout or self.DEFAULT_TIMEOUT
        try:
            return WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located(locator)
            )
        except TimeoutException:
            raise ElementNotFoundError(f"Element not found: {locator}")

    def find_elements(self, driver: webdriver.Remote, locator: Tuple[By, str], timeout: int = None) -> List[WebElement]:
        """Find multiple elements with explicit wait"""
        timeout = timeout or self.DEFAULT_TIMEOUT
        try:
            return WebDriverWait(driver, timeout).until(
                EC.presence_of_all_elements_located(locator)
            )
        except TimeoutException:
            raise ElementNotFoundError(f"Elements not found: {locator}")

    @retry(max_attempts=3, delay=0.5)
    def click(self, driver: webdriver.Remote, element: WebElement, function_name: str, trace: Any, report: Any) -> None:
        """Click on element with retry"""
        try:
            element.click()
            trace.logger.info(f"Clicked element in {function_name}")
            self._display_log(driver, f"Click: {function_name}")
        except Exception as e:
            trace.logger.error(f"Failed to click in {function_name}")
            self._take_action_failure_screenshot(driver, function_name, trace, report)
            raise

    def input_text(self, element: WebElement, text: str, clear: bool = True) -> None:
        """Input text into element"""
        if clear:
            element.clear()
        element.send_keys(text)

    def wait_for_element_visible(self, driver: webdriver.Remote, locator: Tuple[By, str], timeout: int = None) -> WebElement:
        """Wait for element to be visible"""
        timeout = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located(locator)
        )

    def wait_for_element_invisible(self, driver: webdriver.Remote, locator: Tuple[By, str], timeout: int = None) -> bool:
        """Wait for element to be invisible"""
        timeout = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located(locator)
        )

    def wait_for_element_clickable(self, driver: webdriver.Remote, locator: Tuple[By, str], timeout: int = None) -> WebElement:
        """Wait for element to be clickable"""
        timeout = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(locator)
        )

    def get_element_text(self, element: WebElement) -> str:
        """Get text from element"""
        return element.text

    def get_element_attribute(self, element: WebElement, attribute: str) -> str:
        """Get attribute value from element"""
        return element.get_attribute(attribute)

    def is_element_displayed(self, element: WebElement) -> bool:
        """Check if element is displayed"""
        return element.is_displayed()

    def is_element_enabled(self, element: WebElement) -> bool:
        """Check if element is enabled"""
        return element.is_enabled()

    def select_dropdown_by_value(self, element: WebElement, value: str) -> None:
        """Select dropdown option by value"""
        Select(element).select_by_value(value)

    def select_dropdown_by_text(self, element: WebElement, text: str) -> None:
        """Select dropdown option by visible text"""
        Select(element).select_by_visible_text()

    def select_dropdown_by_index(self, element: WebElement, index: int) -> None:
        """Select dropdown option by index"""
        Select(element).select_by_index(index)

    def hover_to_element(self, driver: webdriver.Remote, element: WebElement) -> None:
        """Hover mouse to element"""
        ActionChains(driver).move_to_element(element).perform()

    def drag_and_drop(self, driver: webdriver.Remote, source: WebElement, target: WebElement) -> None:
        """Drag and drop element"""
        ActionChains(driver).drag_and_drop(source, target).perform()

    def scroll_to_element(self, driver: webdriver.Remote, element: WebElement) -> None:
        """Scroll to element"""
        driver.execute_script(
            'arguments[0].scrollIntoView({behavior: "auto", block: "center", inline: "center"});',
            element
        )

    def switch_to_window(self, driver: webdriver.Remote, window_index: int = -1) -> None:
        """Switch to window by index"""
        if len(driver.window_handles) > abs(window_index):
            driver.switch_to.window(driver.window_handles[window_index])
            time.sleep(self.DEFAULT_WAIT)

    def close_window(self, driver: webdriver.Remote, window_index: int = -1) -> None:
        """Close window by index"""
        if len(driver.window_handles) > abs(window_index):
            driver.switch_to.window(driver.window_handles[window_index])
            driver.close()
            time.sleep(self.DEFAULT_WAIT)

    def take_screenshot(self, driver: webdriver.Remote, name: str, trace: Any) -> None:
        """Take screenshot and attach to report"""
        screenshot_path = os.path.join(os.path.abspath(__file__ + "/../../../"), "screenshots", f"{name}.png")
        driver.save_screenshot(screenshot_path)
        allure.attach(
            driver.get_screenshot_as_png(),
            name=name,
            attachment_type=allure.attachment_type.PNG
        )
        trace.logger.info(f"Screenshot saved: {screenshot_path}")

    def _take_action_failure_screenshot(self, driver: webdriver.Remote, function_name: str, trace: Any, report: Any) -> None:
        """Handle failure screenshot and reporting"""
        self.take_screenshot(driver, function_name, trace)
        report.step(f"Failed in {function_name}")
        report.attach(
            driver.get_screenshot_as_png(),
            name=function_name,
            attachment_type=AttachmentType.PNG
        )

    def generate_random_string(self, prefix: str = "", length: int = 8) -> str:
        """Generate random string"""
        chars = string.ascii_letters + string.digits
        random_part = ''.join(random.choice(chars) for _ in range(length))
        return f"{prefix}{random_part}"

    def generate_random_email(self, prefix: str = "test", domain: str = "example.com") -> str:
        """Generate random email"""
        return f"{prefix}{random.randint(1000, 9999)}@{domain}"

    def _display_log(self, driver: webdriver.Remote, message: str) -> None:
        """Display log message on browser"""
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

    def upload_file(self, driver: webdriver.Remote, element: WebElement, file_path: str) -> None:
        """Upload file to input element"""
        element.send_keys(os.path.abspath(file_path))

    def tear_down(self, driver: webdriver.Remote, trace: Any, report: Any) -> None:
        """Close browser and clean up"""
        try:
            if driver is not None:
                driver.quit()
                trace.logger.info("Browser closed successfully")
                report.step("Browser closed successfully")
        except Exception as e:
            trace.logger.error("Failed to close browser")
            trace.logger.exception(e)
            report.step("Failed to close browser")
            raise WebDriverException(f"Teardown failed: {str(e)}")

    # Additional utility methods from original implementation
    def store_coordinates(self, driver: webdriver.Remote, element: WebElement, element_value: str, function_name: str) -> None:
        """Store element coordinates for future use"""
        if str(os.environ.get('update_coordinates')).lower() in ["true", "t", "1"]:
            try:
                self.scroll_to_element(driver, element)
                time.sleep(1)
                
                store_coordinates = os.path.join(
                    os.path.abspath(__file__ + "/../../../"), 
                    "test_data", 
                    "coordinates.ini"
                )
                config = configparser.ConfigParser()
                config.read(store_coordinates)
                
                location = element.location
                size = element.size
                window_size = driver.get_window_size()
                
                x = str((location["x"] + size["width"] / 2) / window_size["width"])
                y = str((location["y"] + size["height"] / 2) / window_size["height"])
                
                # Get calling class and method info
                stack = inspect.stack()
                
                caller_frame = stack[1][0]
                class_name = caller_frame.f_locals['self'].__class__.__name__
                config_key = f"{class_name}.{function_name}"
                
                config["Coordinates"][config_key] = f"{x}, {y}"
                
                with open(store_coordinates, "w") as file:
                    config.write(file)
                    
            except Exception as e:
                print(f"Failed to store coordinates: {str(e)}")

    def get_stored_coordinates(self, driver: webdriver.Remote, function_name: str) -> Tuple[int, int]:
        """Get stored coordinates for element"""
        store_coordinates = os.path.join(
            os.path.abspath(__file__ + "/../../../"), 
            "test_data", 
            "coordinates.ini"
        )
        config = configparser.ConfigParser()
        config.read(store_coordinates)
        
        # Get calling class info
        stack = inspect.stack()
        caller_frame = stack[1][0]
        class_name = caller_frame.f_locals['self'].__class__.__name__
        config_key = f"{class_name}.{function_name}"
        
        if config.has_option("Coordinates", config_key):
            x, y = map(float, config["Coordinates"][config_key].split(","))
            window_size = driver.get_window_size()
            return (
                int(x * window_size["width"]),
                int(y * window_size["height"])
            )
        raise ValueError(f"No coordinates stored for {config_key}")