import urllib.request
import ssl
import re
import json
import time
import sys
import os
from html import unescape

# LLM léger servi par Ollama (ex. : `ollama pull gemma3:1b`)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemma3:1b")
DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

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


def html_to_text(html):
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S)
    html = re.sub(r"<[^>]+>", "\n", html)
    html = unescape(html).replace("\xa0", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in html.split("\n")]
    return "\n".join(line for line in lines if line)


def schedule_excerpt(text):
    # Extrait la zone des horaires pour limiter le contexte envoyé au modèle
    start = text.find("Lundi")
    if start == -1:
        return ""
    return text[max(0, start - 300) : start + 2500]


def extract_horaires_llm(html):
    excerpt = schedule_excerpt(html_to_text(html))
    if not excerpt:
        print("Avertissement : aucun horaire trouvé dans la page.", file=sys.stderr)
        return {}

    schema = {
        "type": "object",
        "properties": {
            day: {"type": "string"} for day in DAYS
        },
        "required": DAYS,
    }
    prompt = (
        "Extrais les horaires d'ouverture réguliers de la période en cours "
        "pour chaque jour de la semaine à partir du texte ci-dessous. "
        "Pour chaque jour, donne les créneaux au format "
        "'06 h 30 – 07 h 45 11 h 45 – 19 h 45' (séparés par un espace), "
        "ou 'Fermé' si la piscine est fermée. N'invente rien.\n\n" + excerpt
    )
    body = json.dumps(
        {
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0},
        }
    ).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            content = json.load(response)["message"]["content"]
        result = json.loads(content)
    except Exception as e:
        print(f"Erreur d'extraction LLM ({LLM_MODEL}) : {e}", file=sys.stderr)
        return {}

    return {
        day: re.sub(r"\s+", " ", str(result[day])).strip()
        for day in DAYS
        if result.get(day)
    }


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

    # remove duplicates
    data["bassins"] = list(set(data["bassins"]))

    # Horaires : extraction par LLM léger à partir du texte de la page
    data["horaires"] = extract_horaires_llm(html)

    return data


def main():
    try:
        urllib.request.urlopen(OLLAMA_URL.rsplit("/api/", 1)[0] + "/api/version", timeout=5)
    except Exception as e:
        sys.exit(f"Ollama injoignable ({OLLAMA_URL}) : {e}")

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

    # sort pools by name
    if not any(f["properties"]["horaires"] for f in features):
        sys.exit("Aucun horaire extrait : le fichier GeoJSON n'est pas écrasé.")
    features.sort(key=lambda x: x["properties"]["nom"])

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
