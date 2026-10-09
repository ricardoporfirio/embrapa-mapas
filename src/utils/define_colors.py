import matplotlib.pyplot as plt
import matplotlib.colors as mcolors


class ColorPalette:
    """Classe para gerar paletas de cores hexadecimais a partir de colormaps do Matplotlib."""

    def __init__(self, color_code: str):
        """
        Parameters
        ----------
        color_code : str
            Nome do colormap registrado no Matplotlib
            (ex.: "viridis", "YlOrRd", "YlGnBu").
        """
        self.color_code = color_code

    def generate(self, n_classes: int) -> list[str]:
        """Gera uma paleta de cores em formato hexadecimal.

        Parameters
        ----------
        n_classes : int
            Número de classes desejado para a paleta.
            Será gerado um número de cores igual a ``n_classes``.

        Returns
        -------
        list of str
            Lista de cores em formato hexadecimal (ex.: "#aabbcc"),
            no total de ``n_classes``.
        """
        # Obter o colormap do Matplotlib com (n_classes) pontos
        cmap = plt.get_cmap(self.color_code, n_classes)

        # Extrair as cores do colormap
        colors = [cmap(i) for i in range(cmap.N)]

        # Converter as cores para o formato hexadecimal
        return [mcolors.rgb2hex(c) for c in colors]
