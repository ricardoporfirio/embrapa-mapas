import importlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box, Polygon, MultiPolygon
from pyproj import Geod

from app import create_app
from src.core.sidra.enums import CultureStyle, TerritorialLevel
from src.models.cow_model import CowModel
from src.transforms.density import transform_density
from src.transforms.productivity import transform_productivity
from src.utils.classification import class_limits, labels_from_bins
from src.utils.atomic import atomic_output
from src.core.jobs import generation_lock, create_job, get_job, finish_job, EventSink, read_events


class Calculations(unittest.TestCase):
    def test_density_matches_geodesic_area_and_preserves_index(self):
        geometry = box(-45, -25, -44, -24)
        frame = gpd.GeoDataFrame({"value": [100, None]}, geometry=[geometry, geometry], crs=4326, index=[7, 11])
        area = abs(Geod(ellps="GRS80").geometry_area_perimeter(geometry)[0]) / 1e6
        result = transform_density(frame, multiplier=1000)
        self.assertAlmostEqual(result.loc[7, "value"], 100000 / area)
        self.assertTrue(pd.isna(result.loc[11, "value"]))
        self.assertEqual(frame.loc[7, "value"], 100)
        projected = transform_density(frame.to_crs(3857), multiplier=1000)
        self.assertAlmostEqual(result.loc[7, "value"], projected.loc[7, "value"], places=6)

    def test_density_holes_parts_and_zero_area(self):
        ring = Polygon([(-45,-25),(-43,-25),(-43,-23),(-45,-23)], holes=[[(-44.8,-24.8),(-44.8,-24.2),(-44.2,-24.2),(-44.2,-24.8)]])
        geometry = MultiPolygon([ring, box(-42,-25,-41,-24)])
        frame = gpd.GeoDataFrame({"value":[1,1]}, geometry=[geometry, Polygon()], crs=4326)
        self.assertGreater(transform_density(frame).loc[0,"value"], 0)
        self.assertTrue(pd.isna(transform_density(frame).loc[1,"value"]))

    def test_productivity_missing_zero_and_geometry_join(self):
        milk = pd.DataFrame({"territory_code":[1,2,3,4],"value":[2,0,None,2]})
        production = gpd.GeoDataFrame({"territory_code":[4,2,1,3], "territory":["D","B","A","C"], "value":[0,50,10,None]}, geometry=[box(i,0,i+1,1) for i in range(4)], crs=4326)
        result = transform_productivity(milk, production, multiplier=1000).set_index("territory_code")
        self.assertEqual(result.loc[1,"value"],5000)
        self.assertEqual(result.loc[4,"value"],0)
        self.assertTrue(pd.isna(result.loc[2,"value"]))
        self.assertTrue(pd.isna(result.loc[3,"value"]))
        self.assertEqual(result.loc[1,"geometry"], production.loc[2,"geometry"])
        self.assertEqual(result.crs, production.crs)

    def test_productivity_matches_period(self):
        milk = pd.DataFrame({"territory_code":[1,1],"period":[2021,2022],"value":[2,4]})
        production = pd.DataFrame({"territory_code":[1,1],"period":[2022,2021],"value":[20,10]})
        result = transform_productivity(milk, production, multiplier=1000)
        self.assertEqual(result["value"].tolist(),[5000,5000])

    def test_sidra_missing_data_is_not_zero(self):
        from src.core.sidra.base_downloader import _BaseSidraDownloader
        data = pd.DataFrame({"D1C":["code","1","2","3"],"D1N":["name","A","B","C"],"V":["value","-","0","..."]})
        result = _BaseSidraDownloader._clean(data)
        self.assertTrue(pd.isna(result.loc[0,"value"]))
        self.assertEqual(result.loc[1,"value"],0)
        self.assertTrue(pd.isna(result.loc[2,"value"]))

    def test_class_limits_empty_constant_decimal_and_manual(self):
        self.assertEqual(class_limits([None], {"mode":"automatic"}), [float("inf")])
        self.assertEqual(class_limits([3,3], {"mode":"automatic"}), [3,float("inf")])
        self.assertEqual(class_limits([0,10], {"mode":"equal_width","k":2}), [5,float("inf")])
        self.assertEqual(class_limits([], {"mode":"manual","breaks":"0, 1.5"}),[0,1.5,float("inf")])
        self.assertEqual(labels_from_bins([float("inf")]),["Todos os valores"])
        self.assertIn("1,5", labels_from_bins([1.5,float("inf")])[0])

    def test_atomic_output_keeps_previous_file_on_error(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/"data.csv"
            target.write_text("old")
            with self.assertRaises(RuntimeError):
                with atomic_output(target) as temp:
                    temp.write_text("partial")
                    raise RuntimeError("failed")
            self.assertEqual(target.read_text(),"old")
            with atomic_output(target) as temp:
                temp.write_text("new")
            self.assertEqual(target.read_text(),"new")
            self.assertEqual(len(list(Path(folder).iterdir())),1)


class DownloadProgress(unittest.TestCase):
    def test_timeout_is_bounded_retried_and_reported(self):
        import requests
        from src.utils.network import get_response, DownloadError
        from src.core.progress import ProgressMeta, progress_context
        session=MagicMock()
        session.get.side_effect=requests.Timeout("slow")
        sink=MagicMock()
        with progress_context(ProgressMeta(job_id="test",queue=sink)), patch("src.utils.network.time.sleep"):
            with self.assertRaisesRegex(DownloadError,"tempo de espera excedido"):
                get_response("https://example.com",label="SIDRA",session=session)
        self.assertEqual(session.get.call_count,2)
        self.assertEqual(session.get.call_args.kwargs["timeout"],(10,60))
        labels=[json.loads(call.args[0])["label"] for call in sink.put.call_args_list]
        self.assertTrue(any("tentativa 2/2" in label for label in labels))

    def test_http_client_error_is_not_retried(self):
        import requests
        from src.utils.network import get_response, DownloadError
        session=MagicMock()
        response=requests.Response(); response.status_code=400
        session.get.return_value=response
        with self.assertRaisesRegex(DownloadError,"HTTP 400"):
            get_response("https://example.com",label="SIDRA",session=session)
        session.get.assert_called_once()

    def test_geobr_tries_mirror_with_timeouts(self):
        from src.utils.network import geobr_url_solver, DownloadError
        response=MagicMock()
        with patch("src.utils.network.get_response",side_effect=[DownloadError("failed"),response]) as get:
            self.assertIs(geobr_url_solver("http://example.com/test.gpkg"),response)
        self.assertEqual(get.call_count,2)
        self.assertIn("github.com",get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs["attempts"],1)

    def test_sidra_uses_timeout_transport_and_normalizes_country(self):
        from src.core.sidra.cow import CowMilkingDownloader
        downloader=CowMilkingDownloader()
        response=MagicMock()
        response.json.return_value=[{"D1C":"code","D1N":"name","V":"value"},{"D1C":"1","D1N":"Brasil","V":"123"}]
        with patch.object(downloader,"_cache_get",return_value=None), patch("src.core.sidra.base_downloader.HttpClient.get_legacy_session"), patch("src.core.sidra.base_downloader.get_response",return_value=response) as get:
            frame=downloader.download(TerritorialLevel.COUNTRY,2022)
        self.assertEqual(frame.loc[0,"territory_code"],76)
        self.assertEqual(frame.loc[0,"value"],123)
        self.assertIn("/t/94/n1/all/p/2022",get.call_args.args[0])

    def test_each_database_stage_emits_progress(self):
        from src.core.generated import Generated
        progress=MagicMock()
        generator=Generated(base_folder="vacas",style_folder="producao",period=[2022],shape_year=2020,model=CowModel(),culture_style=CultureStyle.PRODUCTION,bins={"mode":"automatic"},multiplier=1,progress=progress)
        with patch("src.core.generated.job_country"), patch("src.core.generated.job_region"), patch("src.core.generated.job_state"), patch("src.core.generated.job_municipality") as municipal:
            generator._save_database(2022)
            municipal.assert_called_once()
        labels=[call.args[0] for call in progress.activity.call_args_list]
        self.assertEqual(len(labels),8)
        self.assertTrue(any("Preparando base: Estados" in label for label in labels))
        self.assertTrue(any("Base pronta: Municípios" in label for label in labels))


class JobSources(unittest.TestCase):
    def test_all_metric_types_at_all_territorial_levels(self):
        geometry = box(-45,-25,-44,-24)
        shape = gpd.GeoDataFrame({"geo_territory_code":[1]},geometry=[geometry],crs=4326)
        for scope in ("country","region","state","municipality"):
            module = importlib.import_module(f"src.core.job.job_{scope}")
            shape_name = scope.capitalize()+"Downloader"
            for style in CultureStyle:
                with self.subTest(scope=scope, style=style.name):
                    mk, pr = MagicMock(), MagicMock()
                    mk.download.return_value = pd.DataFrame({"territory_code":[1],"territory":["Test"],"value":[7]})
                    pr.download.return_value = pd.DataFrame({"territory_code":[1],"territory":["Test"],"value":[123]})
                    with patch.object(module,shape_name) as downloader, patch.object(module,"save_csv") as save, patch.object(module,"FolderCreator"), patch.object(module.os.path,"isfile",return_value=False):
                        downloader.return_value.download.return_value = shape
                        getattr(module,f"job_{scope}")(year=2022,shape_year=2020,dir_name="vacas",style_folder="test",culture_style=style,model=CowModel(),downloader_mk=mk,downloader_pr=pr,is_density=style in (CultureStyle.DENSITY_MILKING,CultureStyle.DENSITY_PRODUCTION),is_productivity=style==CultureStyle.PRODUCTIVITY)
                        output = save.call_args.args[0]
                        if style in (CultureStyle.PRODUCTION,CultureStyle.DENSITY_PRODUCTION):
                            pr.download.assert_called_once_with(territorial_level=getattr(TerritorialLevel,scope.upper()),period=2022)
                            mk.download.assert_not_called()
                            expected=123
                        else:
                            mk.download.assert_called_once()
                            expected=7
                        if style==CultureStyle.PRODUCTIVITY:
                            pr.download.assert_called_once()
                            expected=123000/7
                            self.assertEqual(output.loc[0,"unit"],"Em L / cabeça")
                        if style in (CultureStyle.DENSITY_MILKING,CultureStyle.DENSITY_PRODUCTION):
                            expected = transform_density(gpd.GeoDataFrame({"value":[expected]},geometry=[geometry],crs=4326),multiplier=1000 if style==CultureStyle.DENSITY_PRODUCTION else 1).loc[0,"value"]
                        self.assertAlmostEqual(output.loc[0,"value"],expected)
                        if style!=CultureStyle.PRODUCTIVITY and style not in (CultureStyle.PRODUCTION,CultureStyle.DENSITY_PRODUCTION):
                            pr.download.assert_not_called()


class Cartography(unittest.TestCase):
    def test_scale_distance_matches_geodesic_at_its_latitude(self):
        from src.core.poster import MAP_FRAME, scale_geometry
        for extent in ((-78,-30,-35,6),(-50,-40,-25,-15),(-48,-47,-16,-15)):
            with self.subTest(extent=extent):
                view={"extent":extent,"frame":MAP_FRAME}
                scale=scale_geometry(view)
                left,top,right,bottom=MAP_FRAME
                xmin,xmax,ymin,ymax=extent
                start=xmin+(scale["x"]-left)/(right-left)*(xmax-xmin)
                end=xmin+(scale["x"]+scale["width"]-left)/(right-left)*(xmax-xmin)
                measured=abs(Geod(ellps="GRS80").inv(start,scale["latitude"],end,scale["latitude"])[2])/1000
                self.assertAlmostEqual(measured,scale["km"],places=7)
                self.assertLessEqual(scale["width"],500)
                self.assertGreater(scale["width"],0)

    def test_coordinate_ticks_and_hemispheres(self):
        from src.core.poster import geographic_ticks, coordinate_label
        self.assertEqual(coordinate_label(-60,"longitude"),"60.00°W")
        self.assertEqual(coordinate_label(5,"latitude"),"5.00°N")
        self.assertEqual(coordinate_label(-20,"latitude"),"20.00°S")
        self.assertEqual(coordinate_label(0,"latitude"),"0.00°")
        self.assertEqual(geographic_ticks(-78,-30),[-60,-40])


class Rendering(unittest.TestCase):
    def test_dynamic_static_and_poster_without_external_downloads(self):
        from src.core.make_map_dynamic import DynamicMap
        from src.core.make_map_static import StaticMap
        from src.core.poster import render_poster
        from PIL import Image
        frame=gpd.GeoDataFrame({"territory":["A","B"],"value":[1.5,None],"unit":["Em L / cabeça"]*2,"title":["Produtividade"]*2,"abbrev_state":["MG","SP"]},geometry=[box(-45,-25,-44,-24),box(-44,-25,-43,-24)],crs=4326)
        outline=gpd.GeoDataFrame({"abbrev_state":["MG","SP"]},geometry=frame.geometry,crs=4326)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for tiles in (None,"OpenStreetMap"):
                with patch("src.core.make_map_dynamic.StateDownloader.download",return_value=outline):
                    output=root/("plain.html" if tiles is None else "osm.html")
                    DynamicMap(tiles=tiles,bins=[2,float("inf")],output_html=output,remove_outside_brazil=False,show_region_outline=False).build(frame)
                    html=output.read_text(encoding="utf-8")
                    self.assertNotIn("cartocdn",html)
                    self.assertEqual("tile.openstreetmap.org" in html,tiles is not None)
                    self.assertIn("Sem informação",html)
            image=root/"map.png"
            with patch("src.core.make_map_static.StateDownloader.download",return_value=outline):
                StaticMap(bins=[2,float("inf")],output_path=image,dpi=50,figsize=3).build(frame)
            self.assertTrue(image.exists())
            with Image.open(image) as exported:
                metadata=json.loads(exported.info["embrapa_cartography"])
                self.assertEqual(metadata["crs"],"EPSG:4674")
                xmin,xmax,ymin,ymax=metadata["extent"]
                self.assertLess(xmin,-45)
                self.assertGreater(xmax,-43)
                self.assertLess(ymin,-25)
                self.assertGreater(ymax,-24)
                self.assertEqual(len(metadata["axes"]),4)
            poster=root/"poster.png"
            render_poster(title="Produtividade",subtitle="Teste",image_path=image,legend_title="Produtividade",measure_unit="L / cabeça",bins=[2,float("inf")],colors=["#ffffff","#0000ff"],year=2022,output=poster)
            with Image.open(poster) as result:
                self.assertEqual(result.size,(2480,3508))
            self.assertFalse(list(root.glob(".tmp-*")))

    def test_shared_bins_and_selected_basemap_reach_all_maps(self):
        from src.core.generated import Generated
        frames={2021:pd.DataFrame({"value":[0,1]}),2022:pd.DataFrame({"value":[10,11]})}
        generator=Generated(base_folder="vacas",style_folder="producao",period=[2021,2022],shape_year=2020,model=CowModel(),culture_style=CultureStyle.PRODUCTION,bins={"mode":"equal_width","k":2},multiplier=1,basemap="osm",fixed_bins=True)
        generator.ufs=("MG",)
        generator.regs=("sudeste",)
        with patch.object(generator,"_save_database",side_effect=lambda year:frames[year]), patch("src.core.generated.DynamicMap") as dynamic, patch("src.core.generated.StaticMap") as static, patch("src.core.generated.FolderCreator"), patch("src.core.generated.render_poster"):
            generator.run()
        self.assertEqual(dynamic.call_count,6)
        self.assertEqual(static.call_count,6)
        for call in dynamic.call_args_list:
            self.assertEqual(call.kwargs["tiles"],"OpenStreetMap")
            self.assertEqual(call.kwargs["bins"],[5.5,float("inf")])
        for call in static.call_args_list:
            self.assertEqual(call.kwargs["bins"],[5.5,float("inf")])


class WebAndJobs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"RUNTIME_DIR":self.temp.name})
        self.environment.start()
        self.app = create_app({"TESTING":True,"SECRET_KEY":"test-key","WTF_CSRF_ENABLED":True,"SESSION_COOKIE_SECURE":False})
        self.client = self.app.test_client()
        self.payload = dict(culture="cow",type="production",years=[2022],shapes_year=2020,colormap="Blues",bins={"mode":"automatic"},stream=False)

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def authenticate(self):
        with self.client.session_transaction() as session:
            session["user"]={"id":"owner","email":"test@example.com","name":"Test"}

    def token(self):
        html = self.client.get("/login").get_data(as_text=True)
        return re.search(r'name="csrf-token" content="([^"]+)"',html).group(1)

    def post(self,payload=None):
        return self.client.post("/setup/cow/run",json=self.payload if payload is None else payload,headers={"X-CSRFToken":self.token()})

    def test_setup_requires_login(self):
        self.assertEqual(self.client.get("/setup/").status_code,302)
        self.assertEqual(self.post().status_code,401)

    def test_csrf_required(self):
        self.authenticate()
        self.assertEqual(self.client.post("/setup/cow/run",json=self.payload).status_code,400)
        self.assertEqual(self.client.post("/auth/",data={"email":"test","password":"test"}).status_code,400)

    def test_login_does_not_store_firebase_token(self):
        with patch("src.controllers.auth.router.get_auth") as auth:
            auth.return_value.sign_in_with_email_and_password.return_value={"localId":"owner","idToken":"private-token"}
            response=self.client.post("/auth/",data={"email":"test@example.com","password":"test","csrf_token":self.token()})
        self.assertEqual(response.status_code,302)
        with self.client.session_transaction() as session:
            self.assertNotIn("token",session["user"])

    def test_invalid_payloads(self):
        self.authenticate()
        mutations=[{"culture":"goat"},{"years":[]},{"years":[True]},{"years":["x"]},{"shapes_year":None},{"colormap":"bad"},{"basemap":"carto"},{"stream":"true"},{"bins":{"mode":"manual","breaks":"2,1"}},{"bins":{"mode":"manual","breaks":"nan"}},{"bins":{"mode":"equal_width","k":1}}]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assertEqual(self.post(self.payload | mutation).status_code,400)
        self.assertEqual(self.post([]).status_code,400)

    def test_success_failure_and_busy(self):
        self.authenticate()
        with patch("src.controllers.setup.controller.Generated") as generator:
            response=self.post()
            self.assertEqual(response.status_code,200)
            job_id=response.json["job_id"]
            self.assertEqual(get_job(job_id)["status"],"completed")
            self.assertTrue(generator.call_args.kwargs["fixed_bins"])
            self.assertEqual(generator.call_args.kwargs["basemap"],"none")
            generator.return_value.run.side_effect=RuntimeError("internal detail")
            with self.assertLogs(self.app.logger,level="ERROR"):
                failed=self.post()
            self.assertEqual(failed.status_code,500)
            self.assertEqual(get_job(failed.json["job_id"])["status"],"failed")
        lock=generation_lock(); lock.acquire()
        try:
            self.assertEqual(self.post().status_code,409)
        finally:
            lock.release()

    def test_persistent_events_ownership_and_reconnect(self):
        lock=generation_lock(); lock.acquire()
        try:
            job_id=create_job("owner",self.payload)
            EventSink(job_id).put(json.dumps({"phase":"tick"}))
            finish_job(job_id,"completed")
        finally:
            lock.release()
        self.authenticate()
        response=self.client.get(f"/setup/events/{job_id}")
        self.assertIn('"phase": "tick"',response.get_data(as_text=True))
        self.assertIn('"status": "completed"',response.get_data(as_text=True))
        seq=read_events(job_id)[0]["seq"]
        resumed=self.client.get(f"/setup/events/{job_id}",headers={"Last-Event-ID":str(seq)})
        self.assertNotIn('event: progress',resumed.get_data(as_text=True))
        with self.client.session_transaction() as session:
            session["user"]={"id":"other"}
        self.assertEqual(self.client.get(f"/setup/jobs/{job_id}").status_code,404)
        self.assertEqual(self.client.get(f"/setup/events/{job_id}").status_code,404)

    def test_interrupted_job_after_lock_released(self):
        lock=generation_lock(); lock.acquire()
        try:
            job_id=create_job("owner",self.payload)
            self.assertEqual(get_job(job_id)["status"],"running")
        finally:
            lock.release()
        self.assertEqual(get_job(job_id)["status"],"interrupted")

    def test_setup_years_follow_production_and_productivity(self):
        self.authenticate()
        with patch("src.controllers.setup.AvailableYears") as available:
            available.return_value.get.return_value={"ibge":[2021,2022],"shapes":[2020]}
            self.assertEqual(self.client.get("/setup/cow/production/").status_code,200)
            available.assert_called_once_with(74)
        with patch("src.controllers.setup.AvailableYears") as available:
            available.return_value.get.side_effect=[{"ibge":[2020,2021],"shapes":[2020]},{"ibge":[2021,2022],"shapes":[2020]}]
            response=self.client.get("/setup/cow/productivity/")
            self.assertEqual(response.status_code,200)
            self.assertIn('value="2021"',response.get_data(as_text=True))
            self.assertNotIn('value="2022"',response.get_data(as_text=True))
        with patch("src.controllers.setup.AvailableYears") as available:
            available.return_value.get.return_value={"ibge":[],"shapes":[]}
            self.assertEqual(self.client.get("/setup/cow/production/").status_code,503)

    def test_logout_requires_csrf_and_clears_session(self):
        self.authenticate()
        self.assertEqual(self.client.get("/auth/logout").status_code,405)
        self.assertEqual(self.client.post("/auth/logout").status_code,400)
        self.assertEqual(self.client.post("/auth/logout",data={"csrf_token":self.token()}).status_code,302)
        with self.client.session_transaction() as session:
            self.assertNotIn("user",session)

    def test_production_requires_secret_and_secure_cookies(self):
        with patch.dict(os.environ,{"APP_ENV":"production","SECRET_KEY":""}):
            with self.assertRaises(RuntimeError):
                create_app()
        with patch.dict(os.environ,{"APP_ENV":"production","SECRET_KEY":"production-test-key"}):
            self.assertTrue(create_app().config["SESSION_COOKIE_SECURE"])

    def test_sse_connects_immediately_before_any_progress(self):
        lock=generation_lock(); lock.acquire()
        try:
            job_id=create_job("owner",self.payload)
            self.authenticate()
            response=self.client.get(f"/setup/events/{job_id}",buffered=False)
            self.assertIn(b'"connected":true',next(iter(response.response)))
            response.close()
        finally:
            lock.release()

    def test_download_failure_is_visible_and_lock_is_released(self):
        from src.utils.network import DownloadError
        self.authenticate()
        with patch("src.controllers.setup.controller.Generated") as generator:
            generator.return_value.run.side_effect=DownloadError("SIDRA: tempo de espera excedido")
            with self.assertLogs(self.app.logger,level="ERROR"):
                response=self.post()
        job_id=response.json["job_id"]
        job=self.client.get(f"/setup/jobs/{job_id}").json
        self.assertEqual(job["status"],"failed")
        self.assertIn("tempo de espera excedido",job["error"])
        self.assertEqual(job["last_event"]["phase"],"error")
        lock=generation_lock(); lock.acquire(); lock.release()

    def test_public_pages_and_file_routes(self):
        for route in ("/","/login","/interactive_maps","/static_maps","/dashboard_cow"):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code,200)
        self.assertEqual(self.client.get("/mapas/missing.html").status_code,404)
        self.assertEqual(self.client.get("/poster/missing.png").status_code,404)
        self.assertEqual(self.client.get("/mapas/../app.py").status_code,404)


if __name__=="__main__":
    unittest.main()
