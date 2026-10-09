import os
import re
import tempfile
import unittest
from unittest.mock import patch
from app import create_app


class PersonalPresets(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"RUNTIME_DIR": self.temp.name})
        self.environment.start()
        self.config = dict(TESTING=True, SECRET_KEY="tests", WTF_CSRF_ENABLED=True, SESSION_COOKIE_SECURE=False)
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.login("alice")
        self.url = "/setup/cow/production/presets"

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def login(self, owner):
        with self.client.session_transaction() as session:
            session["user"] = {"id": owner, "email": owner + "@example.com"}

    def headers(self):
        html = self.client.get("/login").get_data(as_text=True)
        token = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
        return {"X-CSRFToken": token}

    def save(self, name="Relatório", bins=None, url=None):
        return self.client.post(url or self.url, json={"name":name,"bins":bins or {"mode":"manual","breaks":"100, 500, 1000"}}, headers=self.headers())

    def test_save_list_reuse_and_persistence_after_app_restart(self):
        result = self.save()
        self.assertEqual(result.status_code, 201)
        preset_id = result.json["id"]
        self.client = create_app(self.config).test_client()
        self.login("alice")
        preset = self.client.get(self.url).json["presets"][0]
        self.assertEqual(preset["id"], preset_id)
        from src.utils.classification import class_limits
        self.assertEqual(class_limits([],preset["bins"]),[100,500,1000,float("inf")])
        self.assertEqual(preset["name"], "Relatório")

    def test_ownership_and_indicator_isolation(self):
        preset_id = self.save().json["id"]
        self.assertEqual(self.client.get("/setup/cow/milking/presets").json["presets"],[])
        self.assertEqual(self.client.get("/setup/goat/production/presets").json["presets"],[])
        self.login("bob")
        self.assertEqual(self.client.get(self.url).json["presets"],[])
        self.assertEqual(self.client.delete("/setup/presets/"+preset_id,headers=self.headers()).status_code,404)
        self.assertEqual(self.save().status_code,201)
        self.login("alice")
        self.assertEqual(self.client.delete("/setup/presets/"+preset_id,headers=self.headers()).status_code,200)
        self.assertEqual(self.client.get(self.url).json["presets"],[])

    def test_validation_duplicates_and_modes(self):
        self.assertEqual(self.save().status_code,201)
        self.assertEqual(self.save().status_code,400)
        self.assertEqual(self.save(name=" ").status_code,400)
        self.assertEqual(self.save(name="x"*81).status_code,400)
        for bins in ({"mode":"manual","breaks":"2, 1"},{"mode":"manual","breaks":"NaN"}, {"mode":"equal_width","k":99}, {"mode":"invalid"}):
            self.assertEqual(self.save(bins=bins).status_code,400)
        self.assertEqual(self.save(name="Quantis",bins={"mode":"automatic"}).status_code,201)
        self.assertEqual(self.save(name="Iguais",bins={"mode":"equal_width","k":6}).status_code,201)
        self.assertEqual(self.save(name="Cileite",bins={"mode":"cileite"}).status_code,201)
        self.assertEqual(self.save(bins={"mode":"cileite"},url="/setup/goat/production/presets").status_code,400)

    def test_login_and_csrf_required(self):
        self.assertEqual(self.client.post(self.url,json={}).status_code,400)
        preset_id = self.save().json["id"]
        self.assertEqual(self.client.delete("/setup/presets/"+preset_id).status_code,400)
        headers = self.headers()
        with self.client.session_transaction() as session:
            session.pop("user")
        self.assertEqual(self.client.post(self.url,json={},headers=headers).status_code,401)
        self.assertEqual(self.client.delete("/setup/presets/"+preset_id,headers=headers).status_code,401)
        self.assertIn(self.client.get(self.url).status_code,(302,401))

    def test_setup_page_has_personal_preset_controls(self):
        with patch("src.controllers.setup.AvailableYears") as available:
            available.return_value.get.return_value = {"ibge":[2022], "shapes":[2022]}
            response = self.client.get("/setup/cow/production/")
        self.assertEqual(response.status_code,200)
        html = response.get_data(as_text=True)
        self.assertIn('id="personal-presets"',html)
        self.assertIn('data-endpoint="/setup/cow/production/presets"',html)
        self.assertIn('data-delete-url="/setup/presets/PRESET_ID"',html)

    def test_edit_keeps_id_and_enforces_owner_scope_and_validation(self):
        preset_id = self.save().json['id']
        url = self.url + '/' + preset_id
        data = {'name':'Atualizado','bins':{'mode':'manual','breaks':'2, 8, 14'}}
        self.assertEqual(self.client.put(url,json=data).status_code,400)
        self.login('bob')
        self.assertEqual(self.client.put(url,json=data,headers=self.headers()).status_code,404)
        self.login('alice')
        self.assertEqual(self.client.put('/setup/cow/milking/presets/'+preset_id,json=data,headers=self.headers()).status_code,404)
        self.assertEqual(self.client.put(url,json=data,headers=self.headers()).status_code,200)
        presets = self.client.get(self.url).json['presets']
        self.assertEqual(len(presets),1)
        self.assertEqual(presets[0]['id'],preset_id)
        self.assertEqual(presets[0]['name'],'Atualizado')
        self.assertEqual(presets[0]['bins']['breaks'],'2.0, 8.0, 14.0')
        self.save(name='Outro')
        data['name']='Outro'
        self.assertEqual(self.client.put(url,json=data,headers=self.headers()).status_code,400)
        data['bins']['breaks']='8, 2'
        self.assertEqual(self.client.put(url,json=data,headers=self.headers()).status_code,400)
        self.assertEqual(self.client.get(self.url).json['presets'][0]['name'],'Atualizado')
