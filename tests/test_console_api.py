from fastapi.testclient import TestClient
from app.main import app


def test_console_read_apis_and_static_page_do_not_expose_secrets():
    with TestClient(app) as client:
        status=client.get('/api/config/status')
        assert status.status_code==200
        body=status.json(); text=status.text
        assert 'xhs_cookie' not in text.lower() and 'notion_api_key' not in text.lower()
        cookie=app.state.container.settings.xhs_cookie; token=app.state.container.settings.notion_api_key
        if cookie: assert cookie not in text
        if token: assert token not in text
        assert client.get('/api/inbox').status_code==200
        assert client.get('/api/processor/status').json()['data']['status'] in {'idle','processing','success','failed'}
        assert client.get('/api/notion/recent').status_code==200
        assert client.get('/api/hot').status_code==200
        page=client.get('/console')
        assert page.status_code==200 and 'Knowledge Console' in page.text