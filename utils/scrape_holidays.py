from typing import Dict
import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import List, Optional





MONTH_TO_NUM = {
    "january" : '01',
    "february" : '02',
    "march" : '03',
    "april" : '04',
    "may" : '05',
    "june" : '06',
    "july" : '07',
    "august" : '08',
    "september" : '09',
    "october" : '10',
    "november" : '11',
    "december" : '12',
}

def scrape_holidays() -> list[str]:
    client = httpx.Client(http2=True, timeout=10)
    
    
    url = "https://english.hamropatro.com/nepali-public-holidays"
    
    # holidays-table-wrapper-date cal-table-date
    
    resp = client.get(url)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "html.parser")
    
    rows = soup.find_all(
        "tr",
        style = "line-height: 1.8em;"
    )
    
    print(f'num of rows - {len(rows)}')
    holidays = []
    for row in rows:
        td = row.find_all(
            "td",
            class_ = "holidays-table-wrapper-date cal-table-date"
        )
        
        if len(td) >= 2:
            holidays.append(td[1])
            
    
    
        
    days = []
    for day in holidays:
        days.append(day.get_text(strip=True))
        
    
    
    print(days)
    
    result = []
    for day in days:
        parts = day.split(" ")
        month = MONTH_TO_NUM[parts[1].lower()]
        
        
        year = parts[0]
        month = MONTH_TO_NUM[parts[1].lower()]
        days = parts[2].zfill(2)
        
        
        formatted = f'{year}-{month}-{days}'
        result.append(formatted)


    print(result)
    return result



def save_to_file(holidays: list[str]) -> bool:
    
    
    file = "data/holidays.py"
    
    with open(file, "w") as f:
        
        
        f.write(f"holidays = {holidays}")
        
    return True
    
    
holidays = scrape_holidays()
save_to_file(holidays)