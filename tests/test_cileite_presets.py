import math
import unittest
from unittest.mock import patch
import pandas as pd
from src.utils.cileite_presets import catalog, preset_entry, preset_limits
from src.controllers.setup.validation import validate_payload
from src.core.generated import Generated


class CileitePresets(unittest.TestCase):
    def test_catalog_complete_and_valid(self):
        entries = catalog()["presets"]
        self.assertEqual(len(entries), 671)
        keys = {(p["indicator"], p["territory"], p["year"]) for p in entries}
        self.assertEqual(len(keys), len(entries))
        self.assertEqual(len({p["territory"] for p in entries}), 27)
        for p in entries:
            self.assertEqual(len(p["breaks"]), 4)
            self.assertTrue(all(math.isfinite(x) for x in p["breaks"]))
            self.assertEqual(p["breaks"], sorted(set(p["breaks"])))
            self.assertTrue(p["source"].startswith("https://www.cileite.com.br/"))

    def test_historical_density_and_state_decimals(self):
        self.assertEqual(preset_limits("production-density", 2010)[:-1], [10000,25000,60000,100000])
        self.assertEqual(preset_limits("production-density", 2022)[:-1], [5000,25000,60000,85000])
        self.assertEqual(preset_limits("milking-density", 2022, "AP")[:-1], [.01,.02,.04,.1])
        self.assertEqual(preset_limits("production", 2022, "AC")[:-1], [550,1100,2200,3000])
        self.assertEqual(preset_limits("production", 1990, "MT")[:-1], [1500,4500,8500,15500])
        self.assertEqual(preset_limits("productivity", 1990, "MS")[:-1], [1000,1500,2000,2500])

    def test_missing_year_and_macroregion_policy(self):
        self.assertEqual(preset_entry("production", 2025)["year"], 2022)
        self.assertEqual(preset_entry("production", 2005)["year"], 2000)
        self.assertEqual(preset_entry("production", 1980)["year"], 1990)
        self.assertEqual(preset_entry("production", 2022, "sul")["territory"], "brasil")

    def test_payload_and_generator_choose_state_preset(self):
        data = dict(culture="cow", type="milking", years=[2022], shapes_year=2022,
                    colormap="YlGnBu", bins={"mode":"cileite", "indicator":"production"})
        validated = validate_payload(data, "cow")
        self.assertEqual(validated["bins"], {"mode":"cileite", "indicator":"milking"})
        data["culture"] = "goat"
        with self.assertRaises(ValueError):
            validate_payload(data, "goat")
        generator = object.__new__(Generated)
        generator.bins = validated["bins"]
        self.assertEqual(generator.map_bins(None,2022,"AC")[:-1], [500,1500,3500,5000])
        generator.bins = {"mode":"manual"}
        self.assertEqual(generator.map_bins([1,2,float("inf")],2022,"AC"), [1,2,float("inf")])

    def test_all_output_types_receive_territory_classes(self):
        from src.core.sidra.enums import CultureStyle
        from src.models.cow_model import CowModel
        generator = Generated("vacas", "producao", [2022], 2022, CowModel(),
                              CultureStyle.PRODUCTION, {"mode":"cileite", "indicator":"production"},
                              1, fixed_bins=True)
        self.assertFalse(generator.fixed_bins)
        with patch.object(generator, "_save_database", return_value=pd.DataFrame({"value":[1]})), \
             patch("src.core.generated.FolderCreator"), \
             patch("src.core.generated.DynamicMap") as dynamic, \
             patch("src.core.generated.StaticMap") as static, \
             patch("src.core.generated.render_poster") as poster:
            generator.run()
        for calls in (dynamic.call_args_list,static.call_args_list):
            self.assertEqual(len(calls),32)
            for call in calls:
                territory=call.kwargs.get("state", "brasil")
                self.assertEqual(call.kwargs["bins"],preset_limits("production",2022,territory))
        self.assertEqual(len(poster.call_args_list),32)
        ac=next(c for c in poster.call_args_list if c.kwargs["subtitle"].startswith("AC "))
        self.assertEqual(ac.kwargs["bins"],preset_limits("production",2022,"AC"))
