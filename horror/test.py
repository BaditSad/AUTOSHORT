import time
import base64
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

def generate_image_raphael(prompt: str, output_path="output.jpg"):
    chrome_options = Options()
    # Désactive headless pour tester visuellement
    # chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get("https://raphaelai.org/")

        print("⚠️ Si un captcha apparaît, résous-le manuellement.")
        time.sleep(10)  # temps pour résoudre Cloudflare si besoin

        # remplir le champ prompt
        prompt_box = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//textarea[@placeholder='Describe what you want to see']"))
        )
        driver.execute_script(
            "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            prompt_box,
            prompt
        )

        # chercher le bouton "Generate"
        generate_button = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(translate(., 'GENERATE', 'generate'), 'generate')]"))
        )

        driver.execute_script("arguments[0].scrollIntoView(true);", generate_button)
        time.sleep(1)
        generate_button.click()

        # attendre que l’image apparaisse
        img_elem = WebDriverWait(driver, 90).until(
            EC.presence_of_element_located((By.XPATH, "//img[contains(@src, 'data:image')]"))
        )

        src = img_elem.get_attribute("src")
        header, encoded = src.split(",", 1)
        img_bytes = base64.b64decode(encoded)

        with open(output_path, "wb") as f:
            f.write(img_bytes)

        print(f"✅ Image sauvegardée : {output_path}")
        return output_path

    finally:
        driver.quit()


if __name__ == "__main__":
    generate_image_raphael("Un chat noir mystérieux sous la pluie, ambiance cinématique", "chat_noir.jpg")
