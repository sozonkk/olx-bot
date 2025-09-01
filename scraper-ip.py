import requests
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed
import time
import os
import json
import re
from datetime import datetime

# --- KONFIGURACJA ---
# Zaktualizowana lista linków.
SEARCH_URLS = [
    "https://www.olx.pl/warszawa/q-iphone-12/?search%5Bdist%5D=75&search%5Bfilter_enum_phonemodel%5D%5B0%5D=iphone-12&search%5Bfilter_enum_phonemodel%5D%5B1%5D=iphone-12-mini&search%5Bfilter_enum_phonemodel%5D%5B2%5D=iphone-12-pro-max&search%5Bfilter_enum_phonemodel%5D%5B3%5D=iphone-12-pro&search%5Bfilter_enum_state%5D%5B0%5D=used&search%5Bfilter_float_price%3Afrom%5D=300&search%5Bfilter_float_price%3Ato%5D=600"
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

# --- OTO ZAKTUALIZOWANA I POPRAWIONA SEKCJA ---
def send_discord_notification(listing):
    """Wysyła rozbudowane powiadomienie na Discorda."""
    if not WEBHOOK_URL:
        print("BŁĄD: Brak skonfigurowanego WEBHOOK_URL!")
        return

    # Upewnij się, że link jest pełny
    if not listing['link'].startswith('http'):
        listing['link'] = f"https://www.olx.pl{listing['link']}"

    webhook = DiscordWebhook(url=WEBHOOK_URL, username="🤖 Bot OLX Okazje")
    
    # Tworzenie "embed" - czyli ładnej, sformatowanej wiadomości
    embed = DiscordEmbed(
        title=listing['title'][:256],  # Tytuł ma limit 256 znaków
        description="Nowa oferta znaleziona na OLX!",
        color="03b2f8",
        url=listing['link']
    )
    
    # Dodanie pól - upewniamy się, że żadna wartość nie jest pusta
    embed.add_embed_field(name="💰 Cena", value=listing.get('price', 'Brak') or "Brak", inline=True)
    embed.add_embed_field(name="💾 Pamięć", value=listing.get('memory', 'Brak') or "Brak", inline=True)
    embed.add_embed_field(name="📍 Lokalizacja", value=listing.get('location', 'Brak') or "Brak", inline=True)
    embed.add_embed_field(name="📅 Dodano", value=listing.get('date_added', 'Brak') or "Brak", inline=True)
    
    # Dodanie miniaturki, tylko jeśli link do obrazka istnieje
    if listing.get('image_url'):
        embed.set_thumbnail(url=listing['image_url'])
        
    embed.set_footer(text=f"ID Ogłoszenia: {listing.get('id', 'N/A')}")
    embed.set_timestamp()
    
    webhook.add_embed(embed)
    
    try:
        response = webhook.execute()
        if response.status_code in [200, 204]:
             print(f"✅ Wysłano powiadomienie dla: {listing['title']}")
        else:
            # Drukowanie szczegółowej odpowiedzi błędu od Discorda
            print(f"❌ Błąd wysyłania na Discord: {response.status_code}, Odpowiedź: {response.content}")
    except Exception as e:
        print(f"❌ Krytyczny błąd podczas wysyłania na Discord: {e}")
# --- KONIEC ZAKTUALIZOWANEJ SEKCJI ---

def scrape_single_url(url_to_scrape):
    """Pobiera i przetwarza wszystkie ogłoszenia z jednego linku."""
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