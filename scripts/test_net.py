import urllib.request
import ssl


def fetch_url(url):
    try:
        # Create a context that doesn't verify SSL certificates (just in case)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(url, context=ctx) as response:
            return response.read().decode("utf-8")
    except Exception as e:
        return str(e)


print(
    fetch_url("https://www.paris.fr/lieux/piscine-suzanne-berlioux-les-halles-2916")[
        :500
    ]
)
