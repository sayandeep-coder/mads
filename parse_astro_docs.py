import httpx
from bs4 import BeautifulSoup

r = httpx.get("https://freeastrologyapi.com/api-docs")
soup = BeautifulSoup(r.text, 'html.parser')

endpoints = []
for h3 in soup.find_all('h3'):
    print("---")
    print("Heading:", h3.text.strip())
    # Find next pre/code blocks
    curr = h3
    while curr:
        curr = curr.find_next_sibling()
        if not curr or curr.name == 'h3':
            break
        if curr.name in ['pre', 'code'] or curr.find('pre') or curr.find('code'):
            print(curr.text.strip())
            
