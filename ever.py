import requests
from bs4 import BeautifulSoup
import re
import csv
from concurrent.futures import ThreadPoolExecutor

def fetch_email_from_website(url):
    try:
        # Send a GET request to the website
        response = requests.get(url, timeout=10)
        
        # Check if the request was successful
        if response.status_code == 200:
            # Parse the HTML content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all text in the HTML
            text = soup.get_text()
            
            # Use regex to find email addresses
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            emails = re.findall(email_pattern, text)
            
            if emails:
                return url, emails[0]  # Return the URL and the first email found
            else:
                return url, "No email found"
        else:
            return url, f"Failed to fetch. Status code: {response.status_code}"
    except requests.RequestException as e:
        return url, f"Error: {str(e)}"

def process_urls(urls):
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_email_from_website, urls))
    return results

def save_to_csv(results, filename='email_results.csv'):
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Website URL', 'Email'])
        writer.writerows(results)

# List of website URLs
website_urls = [
    "https://www.kcpsugar.com/contact-us/",
    "https://theandhrasugars.com/contact-us/",
    "https://example.net",
    # Add more URLs here
]

# Process the URLs and get results
results = process_urls(website_urls)

# Save results to CSV
save_to_csv(results)

print("Email extraction completed. Results saved to email_results.csv")
