import os
import glob
import time
import random
import shutil
import asyncio
import pathlib
from typing import Union

from pyrogram import Client
from pyrogram.types import Message
from better_proxy import Proxy
from multiprocessing import Queue

from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager

from bot.config import settings

from bot.utils import logger
from bot.utils.emojis import num, StaticEmoji


def get_session_names() -> list[str]:
    session_names = glob.glob("sessions/*.session")
    session_names = [
        os.path.splitext(os.path.basename(file))[0] for file in session_names
    ]

    return session_names


def get_proxies() -> list[Proxy]:
    if settings.USE_PROXY_FROM_FILE:
        with open(file="bot/config/proxies.txt", encoding="utf-8-sig") as file:
            proxies = [Proxy.from_str(proxy=row.strip()).as_url for row in file]
    else:
        proxies = []

    return proxies


def get_command_args(
        message: Union[Message, str],
        command: Union[str, list[str]] = None,
        prefixes: str = "/",
) -> str:
    if isinstance(message, str):
        return message.split(f"{prefixes}{command}", maxsplit=1)[-1].strip()
    if isinstance(command, str):
        args = message.text.split(f"{prefixes}{command}", maxsplit=1)[-1].strip()
        return args
    elif isinstance(command, list):
        for cmd in command:
            args = message.text.split(f"{prefixes}{cmd}", maxsplit=1)[-1]
            if args != message.text:
                return args.strip()
    return ""


def with_args(text: str):
    def decorator(func):
        async def wrapped(client: Client, message: Message):
            if message.text and len(message.text.split()) == 1:
                await message.edit(f"<emoji id=5210952531676504517>❌</emoji>{text}")
            else:
                return await func(client, message)

        return wrapped

    return decorator


def get_help_text():
    return f"""<b>
{StaticEmoji.FLAG} [Demo version]

{num(1)} /help - Displays all available commands
{num(2)} /tap [on|start, off|stop] - Starts or stops the tapper

</b>"""


async def stop_tasks(client: Client = None) -> None:
    if client:
        all_tasks = asyncio.all_tasks(loop=client.loop)
    else:
        loop = asyncio.get_event_loop()
        all_tasks = asyncio.all_tasks(loop=loop)

    clicker_tasks = [task for task in all_tasks
                     if isinstance(task, asyncio.Task) and task._coro.__name__ == 'run_tapper']

    for task in clicker_tasks:
        try:
            task.cancel()
        except:
            ...


def escape_html(text: str) -> str:
    text = str(text)
    return text.replace('<', '\\<').replace('>', '\\>')

if not pathlib.Path("webdriver").exists() or len(list(pathlib.Path("webdriver").iterdir())) == 0:
    logger.info("Downloading webdriver. It may take some time...")
    pathlib.Path("webdriver").mkdir(parents=True, exist_ok=True)
    webdriver_path = pathlib.Path(ChromeDriverManager().install())
    shutil.move(webdriver_path, f"webdriver/{webdriver_path.name}")
    logger.info("Webdriver downloaded successfully")

def tapswap_driver(proxy_options):
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    if os.name == 'posix':
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')

    mobile_emulation = {
        "deviceMetrics": {"width": 375, "height": 812, "pixelRatio": 3.0},
        "userAgent": "Mozilla/5.0 (Linux; Android 13; SM-A515F Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.134 Mobile Safari/537.36"
    }
    chrome_options.add_experimental_option("mobileEmulation", mobile_emulation)
    return webdriver.Chrome(service=ChromeService(next(pathlib.Path("webdriver").iterdir()).as_posix()),
                            options=chrome_options, seleniumwire_options=proxy_options)

driver = None

session_queue = Queue()

def safe_qsize(queue: Queue) -> int:
    try:
        return queue.qsize()
    except NotImplementedError:
        # Alternative way to count items if qsize() is not implemented
        count = 0
        while not queue.empty():
            queue.get()
            count += 1
        # Re-populate the queue
        for _ in range(count):
            queue.put(1)
        return count

def login_in_browser(auth_url: str, proxy: str) -> tuple[str, str, str]:
    global driver
    if driver is None:
        if proxy:
            proxy_options = {
                'proxy': {
                    'http': proxy,
                    'https': proxy,
                }
            }
        else:
            proxy_options = None

        driver = tapswap_driver(proxy_options)

    driver.get(auth_url)

    time.sleep(random.randint(7, 15))

    try:
        skip_button = driver.find_element(By.CSS_SELECTOR, '#app > div:nth-of-type(2)')
        if skip_button:
            skip_button.click()
            time.sleep(random.randint(2, 5))
    except:
        ...

    try:
        coin_button = driver.find_element(By.CSS_SELECTOR, '#ex1-layer')
        if coin_button:
            coin_button.click()
    except:
        ...

    time.sleep(5)

    response_text = '{}'
    x_cv = '631'
    x_touch = '1'

    for request in driver.requests:
        request_body = request.body.decode('utf-8')
        if request.url == "https://api.tapswap.club/api/account/challenge":
            response_text = request.response.body.decode('utf-8')

        if request.url == "https://api.tapswap.club/api/player/submit_taps":
            headers = dict(request.headers.items())
            x_cv = headers.get('X-Cv') or headers.get('x-cv')
            x_touch = headers.get('X-Touch', '') or headers.get('x-touch', '')

    session_queue.put(1)

    if len(get_session_names()) == session_queue.qsize():
        driver.quit()
        driver = None
        while session_queue.qsize() > 0:
            session_queue.get()

    return response_text, x_cv, x_touch
    