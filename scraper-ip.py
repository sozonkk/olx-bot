import requests
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed
import time
import os
import json
import re
from datetime import datetime

# --- KONFIGURACJA ---
# Dodaj tutaj tyle linków, ile modeli i lokalizacji chcesz monitorować.
SEARCH_URLS = [
    "https://www.olx.pl/warszawa/q-iphone-12/?search%5Bdist%5D=75&search%5Bfilter_enum_phonemodel%5D%5B0%5D=iphone-12&search%5Bfilter_enum_phonemodel%5D%5B1%5D=iphone-12-mini&search%5Bfilter_enum_phonemodel%5D%5B2%5D=iphone-12-pro-max&search%5Bfilter_enum_phonemodel%5D%5B3%5D=iphone-12-pro&search%5Bfilter_enum_state%5D%5B0%5D=used&search%5Bfilter_float_price%3Afrom%5D=300&search%5Bfilter_float_price%3Ato%5D=600",
]

# URL do webhooka będzie pobierany z bezpiecznego miejsca na Railway
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

# Nazwa pliku, w którym będą zapisywane ID już sprawdzonych ogłoszeń
PROCESSED_IDS_FILE = "processed_ids.json"
# --- KONIEC KONFIGURACJI ---

def load_processed_ids():
    """Wczytuje ID już sprawdzonych ogłoszeń z pliku JSON."""
    if not os.path.exists(PROCESSED_IDS_FILE):
        return set()
    try:
        with open(PROCESSED_IDS_FILE, 'r') as f:
            return set(json.load(f))
    except (json.JSONDecodeError, FileNotFoundError):
        return set()

def save_processed_ids(ids_set):
    """Zapisuje ID sprawdzonych ogłoszeń do pliku JSON."""
    with open(PROCESSED_IDS_FILE, 'w') as f:
        json.dump(list(ids_set), f, indent=4)

def extract_memory_from_title(title):
    """Wyciąga pojemność pamięci z tytułu za pomocą wyrażeń regularnych."""
    memory_pattern = r'(\d{2,4})\s*[Gg][Bb]'
    match = re.search(memory_pattern, title)
    if match:
        return f"{match.group(1)} GB"
    return "Nie podano"

def send_discord_notification(listing):
    """Wysyła rozbudowane powiadomienie na Discorda."""
    if not WEBHOOK_URL:
        print("BŁĄD: Brak skonfigurowanego WEBHOOK_URL!")
        return

    webhook = DiscordWebhook(url=WEBHOOK_URL, username="🤖 Bot OLX Okazje")
    embed = DiscordEmbed(
        title=f"🚨 {listing['title']}",
        description=f"Nowa oferta znaleziona na OLX!",
        color="03b2f8",
        url=listing['link']
    )
    embed.set_thumbnail(url=listing['image_url'])
    embed.add_embed_field(name="💰 Cena", value=listing['price'], inline=True)
    embed.add_embed_field(name="💾 Pamięć", value=listing['memory'], inline=True)
    embed.add_embed_field(name="📍 Lokalizacja", value=listing['location'], inline=True)
    embed.add_embed_field(name="📅 Dodano", value=listing['date_added'], inline=True)
    embed.set_footer(text=f"ID Ogłoszenia: {listing['id']}")
    embed.set_timestamp()
    
    webhook.add_embed(embed)
    response = webhook.execute()
    print(f"✅ Wysłano powiadomienie dla: {listing['title']}")

def scrape_single_url(url_to_scrape):
    """Pobiera i przetwarza wszystkie ogłoszenia z jednego linku."""
    print(f"\n--- Sprawdzam URL: {url_to_scrape[:50]}... ---")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    found_listings = []
    try:
        response = requests.get(url_to_scrape, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        ads = soup.find_all('div', {'data-cy': 'l-card'})

        if not ads:
            print("Nie znaleziono żadnych ogłoszeń dla tego linku.")
            return []

        for ad in ads:
            listing_id = ad.get('id')
            if not listing_id: continue

            title_elem = ad.find('h6')
            price_elem = ad.find('p', {'data-testid': 'ad-price'})
            link_elem = ad.find('a')
            location_date_elem = ad.find('p', {'data-testid': 'location-date'})
            
            if not all([title_elem, price_elem, link_elem, location_date_elem]): continue

            title = title_elem.get_text().strip()
            price = price_elem.get_text().strip()
            link = "https://www.olx.pl" + link_elem['href']
            
            location_date_text = location_date_elem.get_text().strip()
            location, date_added = (location_date_text.split(' - ') + ['Brak danych'])[:2]

            image = ad.find('img')
            image_url = image['src'] if image and image.has_attr('src') else "https://i.imgur.com/2s4b6ns.png"
            
            memory = extract_memory_from_title(title)
            
            found_listings.append({
                'id': listing_id,
                'title': title,
                'price': price,
                'link': link,
                'memory': memory,
                'location': location,
                'date_added': date_added,
                'image_url': image_url
            })
        return found_listings
    except Exception as e:
        print(f"❌ Wystąpił błąd podczas sprawdzania linku: {e}")
        return []

if __name__ == "__main__":
    is_first_run = not os.path.exists(PROCESSED_IDS_FILE)
    processed_ids = load_processed_ids()
    
    print(f"🚀 Bot OLX wystartował o {datetime.now().strftime('%H:%M:%S')}")
    if is_first_run:
        print("📢 To jest pierwsze uruchomienie. Zapisuję aktualne ogłoszenia bez wysyłania powiadomień.")
    
    all_current_listings = []
    for url in SEARCH_URLS:
        all_current_listings.extend(scrape_single_url(url))
        time.sleep(3) # Mała przerwa między kolejnymi linkami

    new_found_ids = set()
    notifications_sent = 0

    if is_first_run:
        for listing in all_current_listings:
            new_found_ids.add(listing['id'])
        print(f"\n✅ Zakończono pierwsze uruchomienie. Zapisano {len(new_found_ids)} istniejących ogłoszeń do pamięci.")
    else:
        for listing in all_current_listings:
            if listing['id'] not in processed_ids:
                send_discord_notification(listing)
                new_found_ids.add(listing['id'])
                notifications_sent += 1
                time.sleep(2) # Przerwa między wysyłaniem powiadomień
        
        if notifications_sent > 0:
            print(f"\n🎉 Znaleziono i wysłano {notifications_sent} nowych ogłoszeń!")
        else:
            print("\n😴 Brak nowych ogłoszeń w tym cyklu.")

    # Zaktualizuj plik z ID tylko jeśli znaleziono nowe
    if new_found_ids:
        updated_ids = processed_ids.union(new_found_ids)
        save_processed_ids(updated_ids)

    print(f"🏁 Bot zakończył pracę o {datetime.now().strftime('%H:%M:%S')}")