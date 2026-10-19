import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from agentdesk.api import create_app
from agentdesk.config import DEFAULT_CONFIG, create_model
from agentdesk.runtime import Runner
from agentdesk.storage import Store
from test_workbench import ScriptedModel, wait

class OfflineRunner(Runner):
    mode = "history"
    def start(self, *args, **kwargs):
        return super().start(*args, **kwargs, model_override=ScriptedModel(mode=self.mode))

def test_deepseek_product_defaults_enable_high_thinking():
    model = create_model(DEFAULT_CONFIG, 'test-key')
    assert model.model_name == 'deepseek-flash'
    assert model.reasoning_effort == 'high'
    assert model.extra_body == {'thinking': {'type': 'enabled'}}
    assert model.http_client._trust_env is False
    assert model.http_async_client._trust_env is False

@pytest.fixture
def api(tmp_path):
    app = create_app(tmp_path, OfflineRunner)
    with TestClient(app) as client:
        boot = client.get('/api/bootstrap').json()
        sid = client.post('/api/sessions', json={'workspace':boot['workspace']}).json()['id']
        client.put('/api/credentials', json={'provider':'DeepSeek','api_key':'local-test-key'})
        yield client, sid, app.state.desk

def test_existing_database_migrates_without_losing_history(tmp_path):
    store = Store(tmp_path/'desk.sqlite')
    sid = store.new_session(tmp_path, DEFAULT_CONFIG, '旧版会话')
    store.add_message(sid,'user','保留旧消息')
    store.remember(tmp_path,'保留旧记忆')
    with TestClient(create_app(tmp_path,OfflineRunner)) as client:
        boot = client.get('/api/bootstrap').json()
        assert boot['sessions'][0]['title']=='旧版会话'
        assert boot['sessions'][0]['config']['provider']=='DeepSeek'
        assert boot['sessions'][0]['config']['model']=='deepseek-flash'
        assert boot['sessions'][0]['config']['reasoning_effort']=='high'
        assert client.get(f'/api/sessions/{sid}').json()['messages'][0]['content']=='保留旧消息'
        assert client.get(f'/api/sessions/{sid}/memories').json()[0]['content']=='保留旧记忆'

def test_chat_api_and_history(api):
    client,sid,desk=api
    assert client.post(f'/api/sessions/{sid}/messages',json={'text':'hello'}).status_code==202
    wait(desk.runner.get(sid))
    assert client.get(f'/api/sessions/{sid}').json()['messages'][-1]['content']=='历史用户消息数：1'
    assert client.post(f'/api/sessions/{sid}/messages',json={'text':'again'}).status_code==202
    wait(desk.runner.get(sid))
    assert client.get(f'/api/sessions/{sid}').json()['messages'][-1]['content']=='历史用户消息数：2'
    exported=client.get(f'/api/sessions/{sid}/export?format=json').json()
    assert len(exported['messages'])==4

def test_approval_api_locks_config_and_validates_decisions(api):
    client,sid,desk=api
    desk.runner.mode='terminal'
    client.post(f'/api/sessions/{sid}/messages',json={'text':'run'})
    wait(desk.runner.get(sid))
    assert not (desk.workspace/'result.txt').exists()
    assert client.put(f'/api/sessions/{sid}/config',json=DEFAULT_CONFIG).status_code==409
    assert client.post(f'/api/sessions/{sid}/resume',json={'decisions':[{'type':'approve'},{'type':'approve'}]}).status_code==400
    assert client.post(f'/api/sessions/{sid}/resume',json={'decisions':[{'type':'approve'}]}).status_code==202
    wait(desk.runner.get(sid))
    assert (desk.workspace/'result.txt').read_text(encoding='utf-8-sig').strip()=='hello workspace'
    assert client.post(f'/api/sessions/{sid}/resume',json={'decisions':[{'type':'approve'}]}).status_code==409

def test_upload_preview_and_cross_session_attachment_rejection(api):
    client,sid,desk=api
    response=client.post(f'/api/sessions/{sid}/uploads',files=[('files',('notes.txt','测试内容'.encode(),'text/plain'))])
    assert response.status_code==201
    path=response.json()[0]['path']
    assert client.get(f'/api/sessions/{sid}/preview',params={'path':path}).json()['text']=='测试内容'
    assert client.get(f'/api/sessions/{sid}/download',params={'path':path}).content=='测试内容'.encode()
    other=client.post('/api/sessions',json={'workspace':str(desk.workspace)}).json()['id']
    assert client.post(f'/api/sessions/{other}/messages',json={'text':'read','attachments':[path]}).status_code==400
    assert client.post(f'/api/sessions/{sid}/messages',json={'text':'read','attachments':[path]}).status_code==202
    wait(desk.runner.get(sid))
    assert client.get(f'/api/sessions/{sid}').json()['messages'][0]['attachments'][0]['path']==path

def test_path_guards_and_unknown_session(api):
    client,sid,_=api
    for endpoint in ['files','preview','download']:
        assert client.get(f'/api/sessions/{sid}/{endpoint}',params={'path':'../desk.sqlite'}).status_code==400
    assert client.get('/api/sessions/missing').status_code==404
    assert client.post('/api/sessions',json={'workspace':'relative'}).status_code==400
    assert client.put(f'/api/sessions/{sid}/config',json=dict(DEFAULT_CONFIG,provider='unknown')).status_code==422

def test_credentials_are_encrypted_and_persist_for_this_computer(api):
    client,sid,desk=api
    assert client.get('/api/bootstrap').json()['credentials']['DeepSeek']
    exported=client.get(f'/api/sessions/{sid}/export').text
    assert 'local-test-key' not in exported
    assert b'local-test-key' not in desk.store.path.read_bytes()
    with TestClient(client.app) as other:
        # The same local Windows user can use the encrypted saved credential.
        assert other.get('/api/bootstrap').json()['credentials']['DeepSeek']
    with TestClient(create_app(desk.store.path.parent, OfflineRunner)) as restarted:
        assert restarted.get('/api/bootstrap').json()['credentials']['DeepSeek']
    client.put('/api/credentials', json={'provider':'DeepSeek','api_key':''})
    with TestClient(create_app(desk.store.path.parent, OfflineRunner)) as cleared:
        assert not cleared.get('/api/bootstrap').json()['credentials']['DeepSeek']
    assert client.post('/api/sessions',json={'workspace':str(desk.workspace)},headers={'Origin':'https://untrusted.example'}).status_code==403

def test_memory_archive_and_rename(api):
    client,sid,desk=api
    assert client.patch(f'/api/sessions/{sid}',json={'title':'重命名'}).json()['title']=='重命名'
    mid=client.post(f'/api/sessions/{sid}/memories',json={'content':'中文优先'}).json()['id']
    assert len(client.get(f'/api/sessions/{sid}/memories').json())==1
    client.delete(f'/api/sessions/{sid}/memories/{mid}')
    assert not client.get(f'/api/sessions/{sid}/memories').json()
    client.patch(f'/api/sessions/{sid}',json={'archived':True})
    assert not client.get('/api/sessions').json()
    assert client.get('/api/sessions?archived=true').json()[0]['id']==sid
    client.patch(f'/api/sessions/{sid}',json={'archived':False})
    assert client.get('/api/sessions').json()[0]['id']==sid

def test_child_project_creation_and_stable_preview(tmp_path):
    app = create_app(tmp_path, OfflineRunner)
    with TestClient(app) as client:
        first = client.post('/api/sessions', json={'idea':'我要做一个双人坦克游戏，要能放技能！','placement':'auto'})
        assert first.status_code == 201
        session = first.json()
        assert session['project']['idea'].startswith('我要做')
        assert session['project']['fingerprint']['signature']
        workspace = Path(session['workspace'])
        assert workspace.is_dir() and workspace.parent == tmp_path/'projects'
        (workspace/'assets').mkdir()
        (workspace/'assets'/'style.css').write_text('body{color:teal}', encoding='utf-8')
        (workspace/'index.html').write_text('<h1>坦克出发</h1><link rel="stylesheet" href="assets/style.css">', encoding='utf-8')
        app.state.desk.store.publish_project(session['id'], 'index.html')
        refreshed = client.get(f"/api/sessions/{session['id']}").json()['session']
        assert refreshed['project']['preview_ready']
        assert client.get(refreshed['project']['preview_url']).text.startswith('<h1>坦克出发')
        assert 'teal' in client.get(refreshed['project']['preview_url']+'assets/style.css').text

        second = client.post('/api/sessions', json={'idea':'我要做一个双人坦克游戏，要能放技能！','placement':'auto'}).json()
        assert second['workspace'] != session['workspace']
        assert second['project']['fingerprint']['signature'] != session['project']['fingerprint']['signature']
