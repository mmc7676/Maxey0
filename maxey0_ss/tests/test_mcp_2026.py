from fastapi.testclient import TestClient
from maxey0_ss.api.app import create_app


def headers(method, name=""):
    h={"MCP-Protocol-Version":"2026-07-28","Mcp-Method":method}
    if name: h["Mcp-Name"]=name
    return h


def test_discover_is_stateless_no_session_header():
    c=TestClient(create_app())
    r=c.post('/mcp', headers=headers('server/discover'), json={'jsonrpc':'2.0','id':1,'method':'server/discover','params':{}})
    assert r.status_code == 200
    assert r.json()['result']['protocolVersion']=='2026-07-28'
    assert 'Mcp-Session-Id' not in r.headers


def test_tools_list_has_cache_hints():
    c=TestClient(create_app())
    r=c.post('/mcp', headers=headers('tools/list'), json={'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}})
    assert r.status_code == 200
    assert r.json()['result']['ttlMs'] > 0


def test_tool_call_routes_by_header():
    c=TestClient(create_app())
    r=c.post('/mcp', headers=headers('tools/call','maxey0-ss.health'), json={'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'maxey0-ss.health','arguments':{}}})
    assert r.status_code == 200
    assert r.json()['result']['structuredContent']['mcp_protocol']=='2026-07-28'


def test_ui_resource_is_mcp_app_shape():
    c=TestClient(create_app())
    r=c.post('/mcp', headers=headers('resources/list'), json={'jsonrpc':'2.0','id':4,'method':'resources/list','params':{}})
    uris=[x['uri'] for x in r.json()['result']['resources']]
    assert 'ui://maxey0-ss/super-space.html' in uris
    rr=c.post('/mcp', headers=headers('resources/read'), json={'jsonrpc':'2.0','id':5,'method':'resources/read','params':{'uri':'ui://maxey0-ss/super-space.html'}})
    assert rr.status_code==200
    assert 'Maxey0-SuperSpace' in rr.json()['result']['contents'][0]['text']
