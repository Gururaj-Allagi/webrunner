These functions I have created based on the my experience, which is suitable for any kine of python selenium frameworks
"""
# WebRunner - Selenium Automation Framework

![Python](https://img.shields.io/badge/python-3.7+-blue.svg)
![Selenium](https://img.shields.io/badge/selenium-4.0+-orange.svg)

## Quick Start
```python
from web_runner import WebRunner
from selenium.webdriver.common.by import By

runner = WebRunner()
driver = runner.open_browser("chrome", logger)
runner.click(driver, (By.ID, "button"), "test", logger, report)
Key Features
Supports Chrome/Firefox/Safari (headless too)

Auto-waits and retries for elements

Built-in screenshots & logging

Allure reporting integration

Mobile/desktop ready

Core Methods
open_browser() - Launch browser

find_element() - Smart element locator

click()/input_text() - Interactions

take_screenshot() - Debugging helper

tear_down() - Cleanup

Config (config.ini)
ini
[DEFAULT]
browser = chrome
timeout = 30
Tips
Use (By.CSS_SELECTOR, ".class") for best performance

Wrap tests in try/except with take_screenshot()

Set headless=True for CI pipelines
