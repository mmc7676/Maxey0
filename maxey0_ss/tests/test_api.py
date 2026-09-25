from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.examples.maker_checker_judge import build_demo


def test_a2a_endpoint():
    system = build_demo()
    client = TestClient(create_app(system))
    r = client.post('/v1/a2a/message', json={"sender":"external", "task":"threat modeling", "concept":"security", "skill":"threat modeling", "context":{}})
    assert r.status_code == 200
    assert r.json()['accepted'] is True


def test_scw_drift_endpoint():
    system = build_demo()
    instance = system.scw_runtime.start('SCW2', 'Maxey2')
    client = TestClient(create_app(system))
    assert client.post(f'/v1/context/scws/{instance.id}/anchor', json={'vector':[1,0]}).status_code == 200
    result = client.post(f'/v1/context/scws/{instance.id}/drift', json={'vector':[-1,0], 'threshold':0.15}).json()
    assert result['drifted'] is True
