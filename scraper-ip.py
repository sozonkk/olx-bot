import requests
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed
import time
import os
import json
import re
from datetime import datetime

# --- KONFIGURACJA ---
SEARCH_URLS = [
    "https://www.olx.pl/warszawa/q-iphone-12/?search%5Bdist%5D=75&search%5Bfilter_enum_phonemodel%5D%5B0%5D=iphone-12&search%5Bfilter_enum_phonemodel%5D%5B1%5D=iphone-12-mini&search%5Bfilter_enum_phonemodel%5D%5B2%5D=iphone-12-pro-max&search%5Bfilter_enum_phonemodel%5D%5B3%5D=iphone-12-pro&search%5Bfilter_enum_state%5D%5B0%5D=used&search%5Bfilter_float_price%3Afrom%5D=300&search%5Bfilter_float_price%3Ato%5D=600"
]
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PROCESSED_IDS_FILE = "processed_ids.json"
# --- KONIEC KONFIGURACJI ---

def load_processed_ids():
    if not os.path.exists(PROCESSED_IDS_FILE):
        return set()
    try:
        with open(PROCESSED_IDS_FILE, 'r') as f:
            return set(json.load(f))
    except (json.JSONDecodeError, FileNotFoundError):
        return set()

def save_processed_ids(ids_set):
    with open(PROCESSED_IDS_FILE, 'w') as f:
        json.dump(list(ids_set), f, indent=4)

def extract_memory_from_title(title):
    memory_pattern = r'(\d{2,4})\s*[Gg][Bb]'
    match = re.search(memory_pattern, title)
    if match:
        return f"{match.group(1)} GB"
    return "Nie podano"

# --- NOWA, UPROSZCZONA FUNKCJA WYSYŁANIA ---
def send_discord_notification(listing):
    """Wysyła uproszczone powiadomienie na Discorda (tylko tytuł, cena, link)."""
    if not WEBHOOK_URL:
        print("BŁĄD: Brak skonfigurowanego WEBHOOK_URL!")
        return

    webhook = DiscordWebhook(url=WEBHOOK_URL, username="🤖 Bot OLX Okazje")
    
    # Tworzymy maksymalnie prosty "embed"
    embed = DiscordEmbed(
        title=f"🚨 {listing.get('title', 'Brak tytułu')[:250]}", # Ograniczamy tytuł do 250 znaków dla bezpieczeństwa
        description=f"**Cena:** {listing.get('price', 'Nie podano')}",
        color="03b2f8",
        url=listing.get('link')
    )
    
    webhook.add_embed(embed)
    
    try:
        response = webhook.execute()
        if response.status_code in [200, 204]:
             print(f"✅ Wysłano (uproszczone) powiadomienie dla: {listing['title']}")
        else:
            print(f"❌ Błąd wysyłania na Discord: {response.status_code}, Odpowiedź: {response.content}")
    except Exception as e:
        print(f"❌ Krytyczny błąd podczas wysyłania na Discord: {e}")
# --- KONIEC NOWEJ FUNKCJI ---

def scrape_single_url(url_to_scrape):
    print(f"\n--- Sprawdzam URL: {url_to_scrape[:50]}... ---")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    found_listings = []
    try:
        response = requests.get(url_to_scrape, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        ads = soup.find_all('div', class_='css-1sw7q4x')

        if not ads:
            print("Nie znaleziono żadnych ogłoszeń dla tego linku. Sprawdź selektor.")
            return []

        for ad in ads:
            link_elem = ad.find('a', href=True)
            if not link_elem: continue
            
            link = link_elem['href']
            if not link.startswith('http'):
                link = f"https://www.olx.pl{link}"

            listing_id_match = re.search(r'-ID([a-zA-Z0-9]+)\.html', link)
            listing_id = listing_id_match.group(1) if listing_id_match else None
            if not listing_id: continue

            title_elem = ad.find('h6')
            title = title_elem.get_text(strip=True) if title_elem else "Brak tytułu"

            price_elem = ad.find('p', {'data-testid': 'ad-price'})
            price = price_elem.get_text(strip=True) if price_elem else "Nie podano ceny"

            location_date_elem = ad.find('p', {'data-testid': 'location-date'})
            location, date_added = ("Brak danych", "Dzisiaj")
            if location_date_elem:
                parts = location_date_elem.get_text(strip=True).split(' - ')
                location = parts[0] if len(parts) > 0 else "Brak danych"
                date_added = parts[1] if len(parts) > 1 else "Dzisiaj"

            image_elem = ad.find('img')
            image_url = image_elem['src'] if image_elem and image_elem.has_attr('src') else "https://i.imgur.com/2s4b6ns.png"
            
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
        print(f"Znaleziono {len(found_listings)} ogłoszeń na stronie.")
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
        time.sleep(3)

    new_found_ids = set()
    notifications_sent = 0

    if is_first_run:
        for listing in all_current_listings:
            new_found_ids.add(listing['id'])
        if new_found_ids:
             print(f"\n✅ Zakończono pierwsze uruchomienie. Zapisano {len(new_found_ids)} istniejących ogłoszeń do pamięci.")
    else:
        for listing in all_current_listings:
            if listing['id'] not in processed_ids:
                send_discord_notification(listing)
                new_found_ids.add(listing['id'])
                notifications_sent += 1
                time.sleep(2)
        
        if notifications_sent > 0:
            print(f"\n🎉 Znaleziono i wysłano {notifications_sent} nowych ogłoszeń!")
        else:
            print("\n😴 Brak nowych ogłoszeń w tym cyklu.")

    if new_found_ids:
        updated_ids = processed_ids.union(new_found_ids)
        save_processed_ids(updated_ids)

    print(f"🏁 Bot zakończył pracę o {datetime.now().strftime('%H:%M:%S')}")