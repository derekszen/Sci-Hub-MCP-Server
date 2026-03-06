import os
import re
import urllib3
import requests
from curl_cffi import requests as curl_requests

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Default mirrors - will try in order
DEFAULT_MIRRORS = [
    'sci-hub.ren',
    'sci-hub.se',
    'sci-hub.st',
    'sci-hub.sg',
    'sci-hub.al',
    'sci-hub.mk',
    'sci-hub.ee',
    'sci-hub.hk',
    'sci-hub.wf',
]

# Get mirrors from environment or use defaults
def get_mirrors():
    """Get list of mirrors from environment or defaults"""
    env_mirrors = os.environ.get('SCIHUB_BASE_URLS', '')
    if env_mirrors:
        return [m.strip() for m in env_mirrors.split(',') if m.strip()]
    return DEFAULT_MIRRORS.copy()


def get_base_url():
    """Get primary mirror URL"""
    return os.environ.get('SCIHUB_BASE_URL', 'https://sci-hub.ren')


def get_timeout():
    """Get timeout from environment"""
    return int(os.environ.get('SCIHUB_TIMEOUT_SECONDS', '30'))


def search_paper_by_doi(doi):
    """Search for paper on Sci-Hub by DOI"""
    mirrors = get_mirrors()
    timeout = get_timeout()
    base_url = get_base_url()

    # Try primary URL first, then mirrors
    urls_to_try = [base_url] + [f'https://{m}/{doi}' for m in mirrors]

    for url in urls_to_try:
        try:
            # Use curl-cffi to bypass Cloudflare
            response = curl_requests.get(
                url,
                timeout=timeout,
                impersonate='chrome'
            )

            if response.status_code == 200:
                # Try to find PDF URL in response
                text = response.text

                # Look for PDF in various patterns
                pdf_patterns = [
                    r'(https?://[^\s"\'<>]+\.pdf[^\s"\'<>]*)',
                    r'data-src="([^"]*\.pdf[^"]*)"',
                    r'src="([^"]*\.pdf[^"]*)"',
                    r'href="([^"]*\.pdf[^"]*)"',
                ]

                for pattern in pdf_patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    if matches:
                        pdf_url = matches[0]
                        return {
                            'doi': doi,
                            'pdf_url': pdf_url,
                            'status': 'success',
                            'title': '',
                            'author': '',
                            'year': ''
                        }

                # Try to extract from iframe
                iframe_match = re.search(r'<iframe[^>]*src="([^"]+)"', text)
                if iframe_match:
                    iframe_src = iframe_match.group(1)
                    if 'pdf' in iframe_src.lower():
                        return {
                            'doi': doi,
                            'pdf_url': iframe_src,
                            'status': 'success',
                            'title': '',
                            'author': '',
                            'year': ''
                        }

        except Exception as e:
            continue

    return {
        'doi': doi,
        'status': 'not_found'
    }


def search_paper_by_title(title):
    """Search for paper by title using CrossRef to get DOI first"""
    try:
        # Get DOI from CrossRef
        url = f"https://api.crossref.org/works?query.title={title}&rows=1"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data['message']['items']:
                doi = data['message']['items'][0]['DOI']
                return search_paper_by_doi(doi)
    except Exception as e:
        print(f"CrossRef search error: {e}")

    return {
        'title': title,
        'status': 'not_found'
    }


def search_papers_by_keyword(keyword, num_results=10):
    """Search for papers by keyword"""
    papers = []
    try:
        url = f"https://api.crossref.org/works?query={keyword}&rows={num_results}"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            for item in data['message']['items']:
                doi = item.get('DOI')
                if doi:
                    result = search_paper_by_doi(doi)
                    if result['status'] == 'success':
                        papers.append(result)
                    else:
                        # Even if PDF not found, return metadata
                        papers.append({
                            'doi': doi,
                            'status': 'found_no_pdf',
                            'title': item.get('title', [''])[0] if item.get('title') else '',
                            'author': ', '.join([a.get('family', '') for a in item.get('author', [])]),
                            'year': item.get('published-print', {}).get('date-parts', [[None]])[0][0] if item.get('published-print') else ''
                        })
    except Exception as e:
        print(f"Search error: {e}")

    return papers


def download_paper(pdf_url, output_path):
    """Download paper PDF"""
    # Try direct download first
    urls_to_try = [pdf_url]

    # If the URL is a Sci-Hub URL, try alternative PDF hosts
    if 'sci-hub' in pdf_url.lower():
        # Extract DOI from URL if possible
        import re
        doi_match = re.search(r'(10\.\d{4,}/[^\s/?#]+)', pdf_url)
        if doi_match:
            doi = doi_match.group(1)
            # Add alternative PDF hosts
            urls_to_try.extend([
                f'https://sci-hub.se/{doi}',
                f'https://sci-hub.st/{doi}',
            ])

    for url in urls_to_try:
        try:
            response = curl_requests.get(
                url,
                timeout=60,
                impersonate='chrome'
            )

            if response.status_code == 200 and len(response.content) > 1000:
                # Ensure output directory exists
                os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)

                with open(output_path, 'wb') as f:
                    f.write(response.content)
                return True
        except Exception as e:
            print(f"Download error for {url}: {e}")
            continue

    return False


if __name__ == "__main__":
    print("Sci-Hub Paper Search Test\n")

    # Test DOI search
    print("1. DOI Search Test")
    result = search_paper_by_doi("10.1038/nature09492")

    if result['status'] == 'success':
        print(f"  Title: {result['title']}")
        print(f"  Author: {result['author']}")
        print(f"  Year: {result['year']}")
        print(f"  PDF URL: {result['pdf_url']}")

        # Test download
        output_file = "paper_test.pdf"
        if download_paper(result['pdf_url'], output_file):
            print(f"  Downloaded to: {output_file}")
        else:
            print("  Download failed")
    else:
        print(f"  Not found: {result['doi']}")
