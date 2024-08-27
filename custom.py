from googleapiclient.discovery import build

def google_search(query, num_results=10):
    service = build("customsearch", "v1", developerKey="AIzaSyDdp3kkZRgwZ6kePoOnpJyUltSk68UjHEA")
    results = service.cse().list(q=query, cx="70cecd9d812164b8d", num=num_results).execute()
    
    search_results = []
    for item in results.get('items', []):
        search_results.append(item['link'])
    
    return search_results