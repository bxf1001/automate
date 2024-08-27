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

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QProgressBar, QLabel
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QStyleFactory
from PyQt6.QtGui import QPalette, QColor

class SearchThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(list)

    def __init__(self, query, tags, num_results, csv_path, excel_path):
        super().__init__()
        self.query = query
        self.tags = tags
        self.num_results = num_results
        self.csv_path = csv_path
        self.excel_path = excel_path
        self.domain_results = {}

    def run(self):
        driver = webdriver.Chrome()
        search_results = []
        
        try:
            driver.get("https://www.google.com")
            search_box = driver.find_element(By.NAME, "q")
            search_box.send_keys(self.query)
            search_box.send_keys(Keys.RETURN)
            
            while len(search_results) < self.num_results:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.g")))
                links = driver.find_elements(By.CSS_SELECTOR, "div.g a")
                
                for link in links:
                    url = link.get_attribute("href")
                    if url and "http" in url:
                        domain = urlparse(url).netloc
                        if 'www.' in domain:
                            domain = domain.split('www.')[1]
                        main_domain = domain.split('.')[0].lower()
                        if any(tag in main_domain for tag in self.tags) and domain.endswith(('.com', '.in', '.org')):
                            search_results.append(url)
                    
                    if len(search_results) >= self.num_results:
                        break
                
                self.progress.emit(int(len(search_results) / self.num_results * 100))
                
                next_button = driver.find_elements(By.ID, "pnnext")
                if not next_button:
                    break
                next_button[0].click()
                time.sleep(2)
        
        finally:
            driver.quit()
        processed_results = [self.process_url(url) for url in search_results]
        self.save_to_csv(processed_results, self.csv_path)
        self.save_to_excel(processed_results, self.excel_path)
        self.finished.emit(processed_results)
        self.finished.emit(search_results[:self.num_results])




    def save_to_excel(self, results, filename):
        wb = Workbook()
        ws = wb.active
        ws.title = "Feed Factories Emails"
        
        ws.append(['Domain', 'Website URL', 'Contact Page', 'Emails'])
        for result in results:
            if result and len(result) == 4:
                ws.append([result[0], result[1], result[2], ', '.join(result[3])])
            else:
                ws.append(['Error', 'Error', 'Error', 'Error'])
        
        wb.save(filename)


    def fetch_page(self,url):
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers)
        return response.text

    def parse_page(self,content):
        tree = html.fromstring(content)
        return tree.xpath('//div[@class="yuRUbf"]/a/@href')

    def manual_search(self,query, num_results=10 ):
        search_results = []
        page = 0
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {}
            while len(search_results) < num_results:
                url = f"https://www.google.com/search?q={query}&start={page * 10}"
                future = executor.submit(self.fetch_page, url)
                future_to_url[future] = url
                page += 1
            
            for future in as_completed(future_to_url):
                content = future.result()
                links = self.parse_page(content)
                search_results.extend(links)
                if len(search_results) >= num_results:
                    break
                time.sleep(random.uniform(0.5, 1.5))  # Reduced delay
        
        return search_results[:num_results]

    def google_search(self,query, num_results=200):
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


    def requests_retry_session(self,
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

    def find_contact_page(self,soup, base_url):
        contact_links = soup.find_all('a', href=re.compile(r'contact', re.I))
        for link in contact_links:
            return urljoin(base_url, link['href'])
        return None

    def extract_emails(self,url, max_retries=3):
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

    def process_url(self,url, max_retries=3):
        domain = urlparse(url).netloc
        for attempt in range(max_retries):
            try:
                response = self.requests_retry_session().get(url, timeout=30)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    contact_page = self.find_contact_page(soup, url)
                    emails = self.extract_emails(url)  # Check main page
                    
                    if contact_page:
                        emails.extend(self.extract_emails(contact_page))
                    
                    # Check a few more pages if no emails found
                    if not emails:
                        for link in soup.find_all('a', href=True)[:5]:  # Limit to first 5 links
                            page_url = urljoin(url, link['href'])
                            if url in page_url:  # Only check pages from the same domain
                                emails.extend(self.extract_emails(page_url))
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

    def save_to_csv(self, results, filename):
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Domain', 'Website URL', 'Contact Page', 'Emails'])
            for result in results:
                if result and len(result) == 4:
                    writer.writerow([result[0], result[1], result[2], ', '.join(result[3])])
                else:
                    writer.writerow(['Error', 'Error', 'Error', 'Error'])


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Email Fetcher Bot")
        self.setGeometry(100, 100, 400, 300)
        self.setWindowIcon(QIcon("icon.png"))

        layout = QVBoxLayout()

        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Enter search query")
        layout.addWidget(self.query_input)

        tag_layout = QHBoxLayout()
        self.tag_inputs = []
        for i in range(3):
            tag_input = QLineEdit()
            tag_input.setPlaceholderText(f"Tag {i+1}")
            self.tag_inputs.append(tag_input)
            tag_layout.addWidget(tag_input)
        layout.addLayout(tag_layout)

        self.num_results_input = QLineEdit()
        self.num_results_input.setPlaceholderText("Number of results")
        layout.addWidget(self.num_results_input)

        button_layout = QHBoxLayout()
        self.fetch_button = QPushButton("Fetch")
        self.reset_button = QPushButton("Reset")
        self.exit_button = QPushButton("Exit")
        button_layout.addWidget(self.fetch_button)
        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.exit_button)
        layout.addLayout(button_layout)
        self.csv_path_input = QLineEdit()
        self.csv_path_input.setPlaceholderText("CSV save location")
        self.csv_browse_button = QPushButton("Browse")
        csv_layout = QHBoxLayout()
        csv_layout.addWidget(self.csv_path_input)
        csv_layout.addWidget(self.csv_browse_button)
        layout.addLayout(csv_layout)

        self.excel_path_input = QLineEdit()
        self.excel_path_input.setPlaceholderText("Excel save location")
        self.excel_browse_button = QPushButton("Browse")
        excel_layout = QHBoxLayout()
        excel_layout.addWidget(self.excel_path_input)
        excel_layout.addWidget(self.excel_browse_button)
        layout.addLayout(excel_layout)
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel()
        layout.addWidget(self.status_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        # Apply Fusion style
        QApplication.setStyle(QStyleFactory.create('Fusion'))

        # Set up a dark palette for a futuristic look
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))

        QApplication.setPalette(dark_palette)

        # Apply custom stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2E2E2E;
            }
            QLineEdit {
                background-color: #3D3D3D;
                color: #FFFFFF;
                border: 1px solid #5A5A5A;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton {
                background-color: #4A90E2;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #5AA0F2;
            }
            QProgressBar {
                border: 2px solid #4A90E2;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4A90E2;
            }
        """)

        self.fetch_button.clicked.connect(self.start_search)
        self.reset_button.clicked.connect(self.reset_fields)
        self.exit_button.clicked.connect(self.close)
        self.csv_browse_button.clicked.connect(self.browse_csv_location)
        self.excel_browse_button.clicked.connect(self.browse_excel_location)
        
    def start_search(self):
        query = self.query_input.text()
        tags = [tag.text() for tag in self.tag_inputs if tag.text()]
        num_results = self.num_results_input.text()
        csv_path = self.csv_path_input.text()
        excel_path = self.excel_path_input.text()

        if not query or not num_results or not csv_path or not excel_path:
            QMessageBox.warning(self, "Missing Information", "Please fill in all required fields.")
            return

        try:
            num_results = int(num_results)
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Number of results must be a valid integer.")
            return

        self.search_thread = SearchThread(query, tags, num_results, csv_path, excel_path)
        self.search_thread.progress.connect(self.update_progress)
        self.search_thread.finished.connect(self.search_finished)
        self.search_thread.start()


    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def search_finished(self, results):
        self.status_label.setText(f"Found {len(results)} results")
        # Process and display results
        
    def browse_csv_location(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save CSV File", "", "CSV Files (*.csv)")
        if file_path:
            self.csv_path_input.setText(file_path)

    def browse_excel_location(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Excel File", "", "Excel Files (*.xlsx)")
        if file_path:
            self.excel_path_input.setText(file_path)


    def reset_fields(self):
        self.query_input.clear()
        for tag_input in self.tag_inputs:
            tag_input.clear()
        self.num_results_input.clear()
        self.progress_bar.setValue(0)
        self.status_label.clear()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())