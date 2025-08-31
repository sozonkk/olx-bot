import requests
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed
import time
import os

# --- KONFIGURACJA ---
# Wklej tutaj URL z Twoim wyszukiwaniem na OLX
OLX_URL = "https://www.olx.pl/warszawa/q-iphone-12/?search%5Bdist%5D=75&search%5Bfilter_float_price:from%5D=300&search%5Bfilter_float_price:to%5D=600&search%5Bfilter_enum_phonemodel%5D%5B0%5D=iphone-12&search%5Bfilter_enum_phonemodel%5D%5B1%5D=iphone-12-mini&search%5Bfilter_enum_phonemodel%5D%5B2%5D=iphone-12-pro-max&search%5Bfilter_enum_phonemodel%5D%5B3%5D=iphone-12-pro&search%5Bfilter_enum_state%5D%5B0%5D=used"

# URL do webhooka będzie pobierany z bezpiecznego miejsca na Railway
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

# Nazwa pliku, w którym będą zapisywane linki do już sprawdzonych ogłoszeń
PROCESSED_ADS_FILE = "processed_ads.txt"
# --- KONIEC KONFIGURACJI ---


def get_processed_ads():
    try:
        with open(PROCESSED_ADS_FILE, 'r') as f:
            return set(f.read().splitlines())
    except FileNotFoundError:
        return set()

def save_processed_ad(url):
    with open(PROCESSED_ADS_FILE, 'a') as f:
        f.write(url + '\n')

def send_discord_notification(title, price, url, image_url):
    if not WEBHOOK_URL:
        print("BŁĄD: Brak skonfigurowanego WEBHOOK_URL!")
        return

    webhook = DiscordWebhook(url=WEBHOOK_URL)
    embed = DiscordEmbed(
        title=f"🚨 Nowa okazja: {title}",
        description=f"**Cena:** {price}",
        color="03b2f8"
    )
    embed.set_thumbnail(url=image_url)
    embed.add_embed_field(name="Link do ogłoszenia", value=f"[Kliknij tutaj]({url})")
    embed.set_footer(text="Bot OLX by Gemini")
    embed.set_timestamp()

    webhook.add_embed(embed)
    response = webhook.execute()
    print(f"Wysłano powiadomienie dla: {title}")

def scrape_olx():
    processed_ads = get_processed_ads()
    print(f"Rozpoczynam sprawdzanie... Sprawdzonych ogłoszeń: {len(processed_ads)}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(OLX_URL, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        ads = soup.find_all('div', {'data-cy': 'l-card'})

        if not ads:
            print("Nie znaleziono żadnych ogłoszeń. Sprawdź selektor HTML lub link OLX.")
            return

        for ad in reversed(ads):
            title_element = ad.find('h6')
            price_element = ad.find('p', {'data-testid': 'ad-price'})
            link_element = ad.find('a')

            if not all([title_element, price_element, link_element]):
                continue

            title = title_element.get_text().strip()
            price = price_element.get_text().strip()
            link = "https://www.olx.pl" + link_element['href']

            if link in processed_ads:
                continue

            image = ad.find('img')
            image_url = image['src'] if image and image.has_attr('src') else "https://i.imgur.com/2s4b6ns.png"

            send_discord_notification(title, price, link, image_url)
            save_processed_ad(link)
            time.sleep(2)

    except requests.exceptions.RequestException as e:
        print(f"Błąd połączenia z OLX: {e}")
    except Exception as e:
        print(f"Wystąpił nieoczekiwany błąd: {e}")

if __name__ == "__main__":
    scrape_olx()