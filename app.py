from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import os, requests, re, json

app = Flask(__name__)

load_dotenv()
API_KEY = os.getenv("API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")


def google_search(query, start, sort_by):
    """Fetch search results from Google Custom Search API."""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": API_KEY,
        "cx": SEARCH_ENGINE_ID,
        "q": query,
        "start": start,
        "sort": sort_by,       # [INFO]: "" -> byRelevance, "date" -> byDate
        # "filter": 1,         # [INFO]: removes duplicate results
        # "exactTerms": query, # [INFO]: forces exact match
    }
    try:
        # [INFO]: fetch search results (from Google JSON API)
        json_response = requests.get(url, params).json()
        # app.logger.info(f"\n\n[DEBUG]: response={json_response}\n----------\n")

        # [INFO]: pretty print JSON response (for debugging)
        json_dump = json.dumps(json_response, indent=2)
        app.logger.info(f"\n\n[DEBUG]: response={json_dump}")
        app.logger.info("\n----------\n")

        # [INFO]: check for Google API specific errors
        if 'error' in json_response:
            log_error_message(json_response)
            return default_types()

        # [INFO]: extract search results
        results = extract_results(json_response)
        app.logger.info(f"\n\n[DEBUG]: results={results}\n----------\n")

        # [INFO]: get next page index, total results count and search time
        next_start = get_next_start(json_response)
        total_results, search_time = extract_from_search_info(json_response)

        return results, next_start, total_results, search_time
    
    except requests.exceptions.RequestException as e:
        app.logger.error(f"\n\n[ERROR]: Request -> {e}\n----------\n")
        return default_types()


def default_types():
    """Returns default values for search results."""
    return [], 0, 0, 0

def log_error_message(json_response):
    """Logs error message from Google API response."""
    error = json_response['error']
    app.logger.error(f"\n\n[ERROR]: GoogleAPI ({error['code']}) -> {error['message']}\n----------\n")

def extract_results(json_response):
    """Extracts search results from API response."""
    results = []
    for item in json_response.get("items", []):
        results.append({
            "title": item.get("htmlTitle"),
            "link": item.get("link"),
            "display_link": item.get("displayLink"),
            "snippet": item.get("htmlSnippet"),
            "breadcrumb_trail": extract_breadcrumb_trail(item)
        })
    return results

def get_next_start(json_response):
    """Extracts the next page start index from API response."""
    next_page_info = json_response.get("queries", {}).get("nextPage", [{}])[0]
    return next_page_info.get("startIndex", 0)

def extract_from_search_info(json_response):
    """Extracts required search information from API response."""
    search_info = json_response.get("searchInformation", {})
    return search_info.get("totalResults", 0), round(search_info.get("searchTime", 0), 2)

def extract_breadcrumb_trail(item):
    """Extracts breadcrumb trail from search result."""
    listitem = item.get("pagemap", {}).get("listitem", [])
    app.logger.info(f"\n\n[DEBUG]: listitem={listitem}\n----------\n")

    if listitem:
        trail = [li.get("name") for li in listitem[:-1]] # [INFO]: excludes last item (current page)
        trail.insert(0, item.get("displayLink"))         # [INFO]: insert domain as first item
        return " > ".join(trail)                         # [NOTE]: refine_breadcrumb_trail() can be applied here
    
    else: # [INFO]: construct trail from URL as fallback
        url_part = re.sub(r'https?://', '', item.get("link"))        # [INFO]: remove protocol
        trail = re.sub(r'(.*?)(\?|\.php|\.html).*', r'\1', url_part) # [INFO]: remove query params and file extension
        app.logger.info(f"\n\n[DEBUG]: url={url_part}, trail={trail}\n----------\n")
        return refine_breadcrumb_trail(trail.split("/"))

def refine_breadcrumb_trail(segments):
    """Refines breadcrumb trail segments."""
    def __format(segment, value="..."): return value if len(segment) > 30 else segment
    formatted_segments = [__format(segment) for segment in segments[:-1]]

    if segments:
        # formatted_segments.append(segments[-1])        # [INFO]: don't modify last segment
        formatted_segments.append(__format(segments[-1], # [INFO]: truncate last segment
                                           segments[-1][:30] + "..."))
    return " > ".join(formatted_segments)


@app.route("/")
def home():
    """Renders the home page."""
    return render_template("index.html")

@app.route("/search")
def search():
    """Handles search requests."""
    query = request.args.get("q", "")
    start = request.args.get("start", 1, type=int)
    sort_by = request.args.get("sort_by", "")
    # app.logger.info(f"\n\n[DEBUG]: query={query}, start={start}, sort_by={sort_by}\n----------\n")

    if not query:
        return jsonify({"error": "No search query provided"}), 400
    
    results, next_start, total_results, search_time = google_search(query, start, sort_by)
    
    return jsonify({
        "results": results,
        "next_start": next_start,
        "total_results": total_results,
        "search_time": search_time
    })

@app.route("/proxy")
def proxy():
    """Proxy endpoint to fetch and serve pages to bypass CORS issues."""
    url = request.args.get("url")
    if not url:
        return "Error: No URL provided", 400

    try:
        response = requests.get(
            url, 
            headers={ "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }, 
            timeout=5
        )
        
        if response.status_code != 200:
            return "Error fetching page", 500
        
        html = response.text
        domain = re.match(r"https?://[^/]+", url).group(0)  # [INFO]: extract base domain

        # [INFO]: fix relative links by injecting <base> tag in <head> section of HTML
        html = re.sub(r"(<head[^>]*>)", rf"\1<base href='{domain}/'>", html, count=1)

        return html
    
    except requests.exceptions.RequestException:
        return "Error fetching page", 500


if __name__ == "__main__":
    app.run(debug=True)
