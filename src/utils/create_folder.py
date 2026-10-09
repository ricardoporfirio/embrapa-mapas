from pathlib import Path


class FolderCreator:
    """Classe para criação de pastas relativas à raiz do projeto."""

    def __init__(self, steps: int = 2):
        """
        Parameters
        ----------
        steps : int, default=2
            Quantos níveis subir a partir do diretório atual para
            localizar a raiz da aplicação.
        """
        self.steps = steps
        self.project_root = self._get_project_root()

    def _get_project_root(self) -> Path:
        """Retorna o caminho da raiz do projeto baseado em `steps`."""
        root = Path(__file__).resolve().parent
        for _ in range(self.steps):
            root = root.parent
        return root

    def create_folder(self, path: str) -> Path:
        """Cria uma pasta relativa à raiz do projeto.

        Parameters
        ----------
        path : str
            Caminho relativo a partir da raiz do projeto.

        Returns
        -------
        pathlib.Path
            Objeto ``Path`` para a pasta criada ou já existente.
        """
        target = self.project_root / path
        target.mkdir(parents=True, exist_ok=True)
        return target
