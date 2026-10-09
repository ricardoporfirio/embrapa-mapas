# src/utils/get_available_years.py
import requests
import geobr
import re


class AvailableYears:
    """Classe para consultar anos disponíveis em comum entre IBGE (SIDRA) e geobr."""

    def __init__(self, ibge_table_code: int):
        """
        Parameters
        ----------
        ibge_table_code : int
            Código da tabela no sistema do IBGE (SIDRA).
        """
        self.ibge_table_code = ibge_table_code

    def get(self) -> dict[str, list[int]]:
        """Retorna os anos disponíveis em comum entre IBGE e geobr.

        Returns
        -------
        list of int
            Lista de anos disponíveis em ambas as fontes. Retorna lista vazia
            se não houver interseção ou se ocorrer erro em uma das consultas.
        """
        ibge_years = self.__ibge_years(self.ibge_table_code)

        if not ibge_years:
            return {"ibge": [], "shapes": []}

        availables = list(set(map(int, ibge_years)))

        ys = {
            "ibge": [ano for ano in availables if ano >= 2000],
            "shapes": self.__geobr_years(),
        }

        return ys

    def __geobr_years(self):
        try:
            geobr.read_region(year=1)
        except Exception as e:
            msg = str(e)

            years = re.findall(r"\b\d{4}\b", msg)
            return sorted(set(map(int, years)))
        return []

    def __ibge_years(self, ibge_table_code: int) -> list[int] | None:
        """Busca anos disponíveis de uma tabela do IBGE (API SIDRA)."""
        api_url = f"https://servicodados.ibge.gov.br/api/v3/agregados/{ibge_table_code}/periodos"
        try:
            response = requests.get(api_url, timeout=30)
            response.raise_for_status()
            json_data = response.json()
            return [int(item["id"]) for item in json_data]
        except (requests.exceptions.RequestException, ValueError):
            return None
