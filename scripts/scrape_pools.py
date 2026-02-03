import urllib.request
import ssl
import re
import json
import time
import sys
import os

# Base URL
BASE_URL = "https://www.paris.fr"
MAIN_PAGE = "https://www.paris.fr/lieux/piscines/tous-les-horaires"


def fetch_url(url):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx) as response:
            return response.read().decode("utf-8")
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


def clean_text(text):
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Replace &nbsp; with space
    text = text.replace("&nbsp;", " ")
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_pool_data(html, url):
    data = {}

    # Name
    name_match = re.search(
        r'<h1[^>]*class="title is-level-1"[^>]*>(.*?)</h1>', html, re.DOTALL
    )
    if name_match:
        data["name"] = clean_text(name_match.group(1))
    else:
        title_match = re.search(r"<title>(.*?) - Ville de Paris</title>", html)
        if title_match:
            data["name"] = title_match.group(1).strip()
        else:
            data["name"] = "Unknown"

    # Address
    addr_match = re.search(
        r'<div class="sidebar-section-content"><strong>.*?</strong><br />(.*?)</div>',
        html,
        re.DOTALL,
    )
    if addr_match:
        data["address"] = clean_text(addr_match.group(1))
    else:
        data["address"] = "Address not found"

    # Coordinates
    coord_match = re.search(r'data-map-markers="\[\[(.*?),(.*?)\]\]"', html)
    if coord_match:
        lat = float(coord_match.group(1))
        lon = float(coord_match.group(2))
        data["coordinates"] = [lon, lat]
    else:
        data["coordinates"] = None

    # Bassins
    # Look for the "Bassins" section content.
    # It seems to be in <div class="places--pool-characteristics-description">...</div>
    # We can just find all occurrences of this class.
    # This regex captures the label (strong) and the value
    # Example: <strong>Largeur du bassin&nbsp;: </strong>\n        20 mètres
    bassin_matches = re.findall(
        r'<div class=[\'"]places--pool-characteristics-description[\'"]>(.*?)</div>',
        html,
        re.DOTALL,
    )

    # The HTML structure shows bassins are grouped in tabs or lists.
    # But simply extracting all characteristics might be enough for now,
    # or we can try to group them if they appear sequentially.
    # Given the structure seen in view_file, it looks like:
    # <div ...><strong>Largeur...</strong> value</div>
    # <div ...><strong>Longueur...</strong> value</div>

    # Let's try to capture them as a list of strings first to see what we get,
    # or try to parse key-value pairs.
    bassin_info = []
    for match in bassin_matches:
        # match is like "<strong>Largeur...</strong> value"
        clean_match = clean_text(match)
        if clean_match:
            bassin_info.append(clean_match)

    data["bassins"] = bassin_info
    # Horaires
    # The structure is complex with tabs for periods. We want the current period.
    # The current period usually has a class "false" (not hidden?) or we can look for the visible one.
    # In the file view, we saw: <div class="places--schedules-regular-content-row ...">
    # containing weekday and timerange.

    horaires = {}
    # We can iterate over rows.
    # Regex to find rows: <div class="places--schedules-regular-content-row ..."> ... </div>
    # This is hard with regex due to nesting.

    # Simpler approach: Find "Lundi", "Mardi"... and the following time range.
    days = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

    # We need to be careful not to mix periods.
    # The active tab content seems to be in <div class="places--schedules-regular-content" ...>
    # Let's try to extract the whole block first if possible, but regex is limited.

    # Let's try to find the day and then capture the next time range list.
    for day in days:
        # Search for the day name followed by some tags and then the time range
        # <div class="places--schedules-regular-content-weekday">\n                    Lundi\n                  </div>
        # ...
        # <div class="places--schedules-regular-content-timerange">...</div>

        # This regex might be too greedy or fail due to newlines.
        # Let's try a simpler one: look for the day, then look for the next timerange block.

        # Find start of day block
        day_idx = html.find(f">{day}</div>")  # Approximate check for day div content
        if day_idx == -1:
            # Try with extra whitespace
            match_day = re.search(
                r'<div class="places--schedules-regular-content-weekday">\s*'
                + day
                + r"\s*</div>",
                html,
            )
            if match_day:
                day_idx = match_day.end()
            else:
                continue

        # From day_idx, look for the next timerange div
        timerange_start = html.find(
            "places--schedules-regular-content-timerange", day_idx
        )
        if timerange_start != -1:
            # Extract content of this div. It might be tricky to find the closing div without a parser.
            # But we can look for the next "places--schedules-regular-content-row" or end of file.
            next_row = html.find(
                "places--schedules-regular-content-row", timerange_start
            )
            if next_row == -1:
                next_row = len(html)

            timerange_html = html[timerange_start:next_row]

            # Extract times from this chunk
            # 06&nbsp;h&nbsp;30 – 08&nbsp;h&nbsp;30
            # We can just clean text and look for patterns like "XX h XX - XX h XX"

            clean_times = clean_text(timerange_html)
            # The clean text might look like "06 h 30 – 08 h 30 10 h 30 – 23 h 30"
            # Let's try to keep it readable.

            # Actually, the times are often in <div class="places--schedules-regular-content-exceptional-sub ...">
            # Let's extract text from that specific class if it exists in the chunk
            sub_match = re.search(
                r"places--schedules-regular-content-exceptional-sub[^>]*>(.*?)</div>",
                timerange_html,
                re.DOTALL,
            )
            if sub_match:
                times = clean_text(sub_match.group(1))
                horaires[day] = times
            else:
                # Fallback to cleaning the whole timerange chunk
                # Remove "Fermé" if it's there?
                horaires[day] = clean_times

    data["horaires"] = horaires

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
        print(f"[{i + 1}/{len(links)}] Processing {link}...")
        html = fetch_url(link)
        if not html:
            continue

        pool_data = extract_pool_data(html, link)

        if pool_data["coordinates"]:
            feature = {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": pool_data["coordinates"]},
                "properties": {
                    "nom": pool_data["name"],
                    "adresse": pool_data["address"],
                    "url": link,
                    "bassins": pool_data["bassins"],
                    "horaires": pool_data["horaires"],
                },
            }
            features.append(feature)
        else:
            print(f"Warning: No coordinates found for {link}")

        time.sleep(0.5)  # Be nice to the server

    geojson = {"type": "FeatureCollection", "features": features}

    # Save to site directory
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "site",
        "piscines_paris.geojson",
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2, ensure_ascii=False)

    print(f"Done. Saved {len(features)} pools to {output_path}")


if __name__ == "__main__":
    main()
