import csv
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from lxml import html
from openpyxl import Workbook
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


domain_results = {}

def save_to_excel(results, filename='feed_factories_emails.xlsx'):
    wb = Workbook()
    ws = wb.active
    ws.title = "feed Factories Emails"
    
    ws.append(['Website URL', 'Contact Page', 'Emails'])
    for result in results:
        ws.append([result[0], result[1], ', '.join(result[2])])
    
    wb.save(filename)

def selenium_google_search(query, num_results=100):
    driver = webdriver.Chrome()
    search_results = []
    
    try:
        driver.get("https://www.google.com")
        search_box = driver.find_element(By.NAME, "q")
        search_box.send_keys(query)
        search_box.send_keys(Keys.RETURN)
        
        while len(search_results) < num_results:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.g")))
            links = driver.find_elements(By.CSS_SELECTOR, "div.g a")
            
            for link in links:
                url = link.get_attribute("href")
                if url and "http" in url:
                    domain = urlparse(url).netloc
                    if 'www.' in domain:
                        domain = domain.split('www.')[1]
                    main_domain = domain.split('.')[0].lower()
                    if 'feed' in main_domain and domain.endswith(('.com', '.in', '.org')):
                        search_results.append(url)
                
                if len(search_results) >= num_results:
                    break
            
            next_button = driver.find_elements(By.ID, "pnnext")
            if not next_button:
                break
            next_button[0].click()
            time.sleep(2)
    
    finally:
        driver.quit()
    
    return search_results[:num_results]

def fetch_page(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    response = requests.get(url, headers=headers)
    return response.text

def parse_page(content):
    tree = html.fromstring(content)
    return tree.xpath('//div[@class="yuRUbf"]/a/@href')

def manual_search(query, num_results=10 ):
    search_results = []
    page = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {}
        while len(search_results) < num_results:
            url = f"https://www.google.com/search?q={query}&start={page * 10}"
            future = executor.submit(fetch_page, url)
            future_to_url[future] = url
            page += 1
        
        for future in as_completed(future_to_url):
            content = future.result()
            links = parse_page(content)
            search_results.extend(links)
            if len(search_results) >= num_results:
                break
            time.sleep(random.uniform(0.5, 1.5))  # Reduced delay
    
    return search_results[:num_results]

def google_search(query, num_results=200):
    service = build("customsearch", "v1", developerKey="AIzaSyDdp3kkZRgwZ6kePoOnpJyUltSk68UjHEA")
    search_results = []
    
    for i in range(0, num_results, 10):
        results = service.cse().list(q=query, cx="70cecd9d812164b8d", num=10, start=i + 1).execute()
        for item in results.get('items', []):
            url = item['link']
            domain = urlparse(url).netloc
            if 'www.' in domain:
                domain = domain.split('www.')[1]
            main_domain = domain.split('.')[0].lower()
            if 'feed' in main_domain and domain.endswith(('.com', '.in', '.org','.co.in')):
                search_results.append(url)
        
        if len(search_results) >= num_results or 'nextPage' not in results.get('queries', {}):
            break
    
    return search_results[:num_results]


def requests_retry_session(
    retries=3,
    backoff_factor=0.3,
    status_forcelist=(500, 502, 504),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def find_contact_page(soup, base_url):
    contact_links = soup.find_all('a', href=re.compile(r'contact', re.I))
    for link in contact_links:
        return urljoin(base_url, link['href'])
    return None

def extract_emails(url, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                text = soup.get_text()
                email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                emails = re.findall(email_pattern, text)
                
                # Check for obfuscated emails
                obfuscated_pattern = r'\b[A-Za-z0-9._%+-]+\s*\[at\]\s*[A-Za-z0-9.-]+\s*\[dot\]\s*[A-Z|a-z]{2,}\b'
                obfuscated_emails = re.findall(obfuscated_pattern, text)
                emails.extend([e.replace('[at]', '@').replace('[dot]', '.') for e in obfuscated_emails])
                
                return list(set(emails))  # Remove duplicates
        except requests.RequestException:
            if attempt == max_retries - 1:
                print(f"Failed to fetch {url} after {max_retries} attempts")
            time.sleep(2)  # Wait before retrying
    return []

def process_url(url, max_retries=3):
    domain = urlparse(url).netloc
    for attempt in range(max_retries):
        try:
            response = requests_retry_session().get(url, timeout=30)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                contact_page = find_contact_page(soup, url)
                emails = extract_emails(url)  # Check main page
                
                if contact_page:
                    emails.extend(extract_emails(contact_page))
                
                # Check a few more pages if no emails found
                if not emails:
                    for link in soup.find_all('a', href=True)[:5]:  # Limit to first 5 links
                        page_url = urljoin(url, link['href'])
                        if url in page_url:  # Only check pages from the same domain
                            emails.extend(extract_emails(page_url))
                        if emails:
                            break  # Stop searching once emails are found
                
                return domain, url, contact_page or "No contact page found", list(set(emails))
            elif response.status_code == 406:
                print(f"Ignoring 406 error for {url}")
                return domain, url, "Ignored due to 406 error", []
            else:
                print(f"Attempt {attempt + 1}: Status code {response.status_code} for {url}")
        except requests.RequestException as e:
            print(f"Attempt {attempt + 1}: Error processing {url}: {str(e)}")
        time.sleep(2)  # Wait before retrying
    return domain, url, "Max retries reached", []





def save_to_csv(results, filename='feed_factories_emails.csv'):
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Website URL', 'Contact Page', 'Emails'])
        for result in results:
            if result:
                writer.writerow([result[0], result[1], ', '.join(result[2])])
            else:
                writer.writerow(['Error', 'Error', 'Error'])

def main():
    query = "feed factories in Andhra Pradesh"
    num_results = 100  # Adjust this number based on how many search results you want to process

    print(f"Searching for: {query}")
    search_results = selenium_google_search(query, num_results)

    print(f"Processing {len(search_results)} websites...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(process_url, search_results))
    for domain, url, contact_page, emails in results:
        if domain not in domain_results or len(emails) > len(domain_results[domain][2]):
            domain_results[domain] = (url, contact_page, emails)

    save_to_csv(domain_results.values())
    save_to_excel(domain_results.values())

    print("Results saved to feed_factories_emails.csv and feed_factories_emails.xlsx")


if __name__ == "__main__":
    main()