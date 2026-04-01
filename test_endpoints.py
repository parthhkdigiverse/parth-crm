import httpx

r = httpx.post('http://localhost:8000/api/auth/login', data={'username': 'admin@example.com', 'password': 'password123'})
try:
    token = r.json()['access_token']
except KeyError:
    print('Failed to authenticate:', r.text)
    exit(1)

headers = {'Authorization': f'Bearer {token}'}

def test_endpoint(name, url):
    print(f'\n--- {name} ---')
    res = httpx.get(url, headers=headers)
    print(f'Status: {res.status_code}')
    if res.status_code != 200:
        print(res.text)

test_endpoint('Clients', 'http://localhost:8000/api/clients/')
test_endpoint('Issues', 'http://localhost:8000/api/issues/?limit=100')
test_endpoint('Meetings', 'http://localhost:8000/api/meetings/?limit=100')
