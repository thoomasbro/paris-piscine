import urllib.request
import ssl
import re
import json
import time
import sys

# Base URL
BASE_URL = "https://www.paris.fr"
MAIN_PAGE = "https://www.paris.fr/lieux/piscines/tous-les-horaires"

def fetch_url(url):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def get_pool_links(html):
    # Find all links to pool details
    # Pattern: <a href="/lieux/piscine-..."
    # Note: The main page lists them.
    # Let's try to find all links that start with /lieux/piscine- or /lieux/espace-sportif-pontoise (some might not have piscine in slug)
    # Based on previous read_url_content, they are like:
    # https://www.paris.fr/lieux/piscine-suzanne-berlioux-les-halles-2916
    # https://www.paris.fr/lieux/espace-sportif-pontoise-2918
    
    # We can look for links inside the list.
    # A generic regex for /lieux/ followed by something and an ID might work.
    # But we want to avoid other places.
    # The user said "La liste des piscines est accessible ici".
    
    links = set()
    # Regex to capture hrefs starting with /lieux/ and ending with digits (ID)
    pattern = r'href="(/lieux/[^"]+-\d+)"'
    matches = re.findall(pattern, html)
    
    for match in matches:
        # Filter out non-pool places if possible, but most on this page should be pools.
        # We can check if "piscine" is in the slug, but "espace-sportif-pontoise" is also a pool.
        # The page is specifically "tous-les-horaires" for PISCINES, so we can probably trust the links.
        full_url = BASE_URL + match
        links.add(full_url)
        
    return list(links)

def extract_pool_data(html, url):
    data = {}
    
    # Name
    # <h1 class="title is-level-1" ...>  \n  Piscine Suzanne Berlioux (Les Halles)\n\n</h1>
    name_match = re.search(r'<h1[^>]*class="title is-level-1"[^>]*>(.*?)</h1>', html, re.DOTALL)
    if name_match:
        data['name'] = name_match.group(1).strip()
    else:
        # Fallback
        title_match = re.search(r'<title>(.*?) - Ville de Paris</title>', html)
        if title_match:
            data['name'] = title_match.group(1).strip()
        else:
            data['name'] = "Unknown"

    # Address
    # <div class="sidebar-section-content"><strong>Piscine Suzanne Berlioux (Les Halles)</strong><br />10 place de la rotonde Forum des halles, Paris 1e</div>
    # Note: The strong tag might contain the name.
    # We look for sidebar-section-content
    addr_match = re.search(r'<div class="sidebar-section-content"><strong>.*?</strong><br />(.*?)</div>', html, re.DOTALL)
    if addr_match:
        data['address'] = addr_match.group(1).strip()
    else:
        # Try without strong tag if structure varies
        addr_match_2 = re.search(r'<div class="sidebar-section-content">(.*?)</div>', html, re.DOTALL)
        if addr_match_2:
            # This might capture other sidebars, so be careful.
            # The one with address usually has <br /> or is the first one?
            # Let's stick to the one with <br /> if possible.
            pass
        data['address'] = "Address not found"

    # Coordinates
    # data-map-markers="[[48.862644,2.343597]]"
    coord_match = re.search(r'data-map-markers="\[\[(.*?),(.*?)\]\]"', html)
    if coord_match:
        lat = float(coord_match.group(1))
        lon = float(coord_match.group(2))
        data['coordinates'] = [lon, lat] # GeoJSON uses [lon, lat]
    else:
        data['coordinates'] = None
        
    return data

def main():
    print("Fetching main page...")
    main_html = fetch_url(MAIN_PAGE)
    if not main_html:
        return

    links = get_pool_links(main_html)
    print(f"Found {len(links)} pool links.")
    
    features = []
    
    for i, link in enumerate(links):
        print(f"[{i+1}/{len(links)}] Processing {link}...")
        html = fetch_url(link)
        if not html:
            continue
            
        pool_data = extract_pool_data(html, link)
        
        if pool_data['coordinates']:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": pool_data['coordinates']
                },
                "properties": {
                    "nom": pool_data['name'],
                    "adresse": pool_data['address'],
                    "url": link
                }
            }
            features.append(feature)
        else:
            print(f"Warning: No coordinates found for {link}")
            
        time.sleep(0.5) # Be nice to the server

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    
    with open('piscines_paris.geojson', 'w', encoding='utf-8') as f:
        json.dump(geojson, f, indent=2, ensure_ascii=False)
        
    print(f"Done. Saved {len(features)} pools to piscines_paris.geojson")

if __name__ == "__main__":
    main()
