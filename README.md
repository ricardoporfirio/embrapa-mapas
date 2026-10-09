# Gerador de mapas — Embrapa

Aplicação Flask com dados SIDRA/IBGE, geometrias geobr, mapas interativos Folium e mapas estáticos Matplotlib.

## Instalação no Windows

Instale o [uv](https://docs.astral.sh/uv/getting-started/installation/). O projeto utiliza Python 3.13.13, definido em `.python-version`; o uv gerencia o Python e o ambiente `.venv`.

```powershell
uv sync --locked
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

Se `SECRET_KEY` estiver vazia, cole a chave gerada no arquivo `.env`. Não versione esse arquivo. Sem chave, o modo de desenvolvimento usa uma chave temporária e as sessões expiram ao reiniciar.

As dependências ficam no `pyproject.toml`, e o `uv.lock` registra a resolução exata. Versione ambos. Para adicionar ou remover dependências, use `uv add nome-do-pacote` ou `uv remove nome-do-pacote`. As versões anteriores foram preservadas nesta migração. O fluxo segue a [documentação de projetos do uv](https://docs.astral.sh/uv/guides/projects/).

## Execução

```powershell
uv run app.py
```

Abra http://127.0.0.1:5001. Faça login para acessar `/setup/`. `manager.py` usa a mesma aplicação e inicia o servidor de desenvolvimento na porta 5000, salvo `PORT` no ambiente. Para depuração, defina `FLASK_DEBUG=1` apenas no desenvolvimento.

Em produção, configure `APP_ENV=production`, uma `SECRET_KEY` persistente e HTTPS no proxy. Cookies de sessão tornam-se exclusivos de HTTPS. `HOST` e `PORT` configuram o endereço do servidor Waitress. O projeto Firebase atual é mantido como padrão; variáveis `FIREBASE_*` permitem substituí-lo. A configuração pública do Firebase não substitui regras de acesso no serviço. A sessão dura uma hora e não armazena o token Firebase no cookie.

## Servidor Linux via SSH

Com o uv instalado, envie o projeto ao servidor, incluindo `pyproject.toml`, `uv.lock` e `.python-version`. O ambiente `.venv` do Windows não deve ser enviado: o script cria o ambiente Linux com `uv sync --locked`.

```bash
bash servidor.sh start
bash servidor.sh status
bash servidor.sh logs
bash servidor.sh stop
bash servidor.sh restart
```

Após `start`, você pode fechar o SSH. `logs` acompanha a saída; Ctrl+C encerra apenas a visualização. O script usa `nohup` e uma sessão independente (`setsid`), com entrada desvinculada do terminal e saída em `runtime/server/server.log`. Ele impede inicializações duplicadas, registra o PID e verifica sua identidade antes de parar o processo. Execute os comandos com o mesmo usuário Linux.

Na primeira execução, se `.env` não existir, uma chave aleatória persistente é criada. O padrão é `HOST=127.0.0.1` e `PORT=5001`. Para acesso direto pelo IP do servidor, configure `HOST=0.0.0.0` no `.env` e permita a porta no firewall. Se usar um proxy HTTPS, mantenha `127.0.0.1` e configure `APP_ENV=production`. Reinicie após alterar o `.env`.

São necessários Bash, `nohup`, `setsid` e `flock` (os dois últimos normalmente fazem parte de `util-linux`). O script verifica o processo, mas não é um supervisor: não reinicia após falhas ou reboot. Em servidores que encerram todos os processos do usuário no logout, use um serviço systemd administrado pelo servidor.

## Geração e unidades

Na configuração, selecione cultura, indicador, anos, geometrias, cores e classes. A lista de anos usa a tabela do indicador; produtividade usa os anos comuns às duas tabelas.

- Produção: base de produção, em mil litros.
- Ordenha: base de ordenha, em cabeças.
- Densidade de produção: litros/km²; densidade de ordenha: cabeças/km².
- Produtividade: litros/cabeça, utilizando produção e ordenha do mesmo território e período.

As áreas são calculadas geodesicamente no elipsoide GRS80, após conversão das geometrias para SIRGAS 2000. Dados ausentes e produtividade com denominador zero permanecem sem informação; zero de produção com denominador positivo continua sendo zero.

Por padrão, os intervalos de legenda são calculados em conjunto para todos os anos selecionados. Desmarque a opção para calcular por ano. Limites manuais aceitam decimais com ponto, separados por vírgula, em ordem crescente. Os intervalos são limites superiores inclusivos, com uma última classe aberta. Sem informação aparece em cinza.

## Fundos dos mapas

O padrão **Sem fundo** exibe polígonos e limites sem solicitar blocos de imagem à CARTO. A alternativa **OpenStreetMap** mantém a atribuição e depende de conexão à internet. Mesmo sem fundo, Folium carrega bibliotecas JavaScript/CSS externas: isso não constitui uma solução completamente offline.

Respeite a [política de blocos do OpenStreetMap](https://operations.osmfoundation.org/policies/tiles/), incluindo atribuição visível, envio de Referer e ausência de download massivo. Os mapas devem ser servidos por HTTP/HTTPS. A opção `no-referrer` foi removida do iframe. Não há proxy nem cache de blocos no servidor.

## Arquivos e trabalhos

- `dataframes/<cultura>/<indicador>/<nível>/`: CSVs.
- `mapas/<cultura>/<indicador>/<ano>/`: HTMLs interativos.
- `imagens/<cultura>/<indicador>/<ano>/`: mapas estáticos.
- `poster/<cultura>/<indicador>/<ano>/`: pôsteres.
- `runtime/jobs.sqlite`: estado, parâmetros e eventos dos trabalhos.

A aplicação permite uma geração por vez, com bloqueio de arquivo compartilhado entre processos no mesmo computador. O progresso é persistido em SQLite e pode ser retomado via SSE após reconexão. `/setup/jobs/<id>` informa o estado somente ao dono do trabalho. Trabalhos interrompidos por queda são identificados ao consultar seu estado ou iniciar nova geração; a execução não é retomada automaticamente. Registros de mais de 30 dias são removidos ao iniciar uma nova geração.

Cada arquivo é gravado temporariamente e substituído após a gravação completa. O conjunto inteiro de mapas não é uma transação: se houver falha no meio, alguns arquivos poderão ter sido atualizados. Reexecute o trabalho para completar o conjunto. A geração informa erros sem anunciá-los como sucesso; detalhes técnicos ficam no log do servidor.

**Após estas correções, regenere os CSVs e mapas anteriores de produção, densidade e produtividade.** Arquivos existentes não são convertidos automaticamente. Faça a regeneração antes de comparar dados antigos com novos.

O cache de geometrias tem validade de sete dias. Os dados SIDRA possuem cache em memória; reiniciar a aplicação o limpa. Geometrias e consultas de anos exigem internet. Os pôsteres usam Arial quando disponível, Liberation Sans no Linux ou DejaVu Sans como alternativa. A composição A4 a 300 dpi segue as proporções do modelo QGIS: quadro horizontal, cabeçalho centralizado, créditos à esquerda e legenda à direita. Os textos dos títulos e a paleta escolhida são preservados. Os logotipos são dimensionados em caixas independentes, mantendo sua proporção.

## Testes

```powershell
uv run --locked python -m unittest discover -s tests -v
uv lock --check
uv pip check
```

Os testes utilizam dados sintéticos e simulam chamadas externas. Não autenticam usuários reais nem fazem downloads de séries completas do IBGE.

## Coordenadas e escala nos pôsteres

Os mapas estáticos são renderizados em SIRGAS 2000 (EPSG:4674). O PNG armazena seu enquadramento e a posição do eixo cartográfico; esses metadados permitem posicionar as coordenadas nas quatro bordas do pôster sem deduzir a localização a partir dos pixels dos polígonos. As marcas de latitude e longitude se ajustam ao recorte selecionado.

A barra de escala usa distância geodésica no elipsoide GRS80 e informa a latitude de referência, pois a escala varia com a latitude em coordenadas geográficas. O comprimento é escolhido automaticamente para Brasil, regiões e estados. Para adicionar esses elementos a arquivos antigos, regenere o mapa estático e o pôster; PNGs sem os metadados cartográficos continuam aceitos, mas não recebem coordenadas ou escala estimadas.

## Acompanhamento de downloads

O progresso mostra a preparação das bases de Brasil, regiões, estados e municípios e a renderização de cada mapa. Consultas SIDRA usam timeout de conexão de 10 segundos e de inatividade de leitura de 60 segundos, com até duas tentativas para falhas transitórias. O geobr usa os mesmos limites por fonte e tenta o espelho quando necessário. Esses limites não representam um prazo total para a geração ou para downloads que continuam transferindo dados.

O SSE confirma a conexão imediatamente. Após 15 segundos sem eventos de progresso, a interface informa o tempo de espera e consulta o estado do trabalho por HTTP. Falhas de download aparecem na interface; detalhes técnicos permanecem no log. Ao usar Nginx ou outro proxy, mantenha o buffering desabilitado para `/setup/events/` e permita conexões de longa duração.


### Presets de classes Cileite para bovinos

Na configuração de intervalos, selecione **Cileite**. O sistema escolhe as quebras do indicador, ano e UF publicados em https://www.cileite.com.br/content/leite-mapas. Brasil e as cinco macrorregiões usam os limites nacionais; cada estado usa os seus limites. Os mesmos limites alimentam o HTML, o PNG e a legenda do pôster. A paleta continua sendo escolhida separadamente.

O catálogo src/utils/cileite_bins.json registra as classes e a URL de cada imagem consultada. Para anos sem mapa publicado, usa-se a referência anterior mais recente daquele indicador e território; antes da primeira publicação, usa-se a primeira referência disponível. Isso inclui anos recentes posteriores à série publicada e Roraima antes de 2000. O modo Cileite substitui a opção de intervalos fixos entre anos.

As classes são limites superiores inclusivos, seguidos por uma classe aberta acima do último limite. Produção usa mil litros; densidade de produção usa litros/km²; produtividade usa litros/cabeça; ordenha usa cabeças e sua densidade usa cabeças/km². Textos antigos de legendas com limites inferiores arredondados são normalizados para intervalos contínuos, sem lacunas, preservando os limites superiores.

O levantamento de outubro de 2026 contém 671 referências: cinco indicadores, Brasil e 26 estados, com publicações de 1990, 2000, 2010, 2020 e 2022, além da produtividade nacional de 2021. Roraima começa em 2000. O catálogo preserva o texto extraído das legendas e registra em `notes` inconsistências da fonte: separadores, lacunas, classes fora de ordem e a legenda aberta de produção de Pernambuco em 1990–2010, que contradiz a quarta classe. Nesses casos os limites foram conferidos visualmente e normalizados, sem reproduzir sobreposições no sistema.

Referência nacional de 2022 (limites superiores; a quinta classe é aberta):

| Indicador | Limites |
| --- | --- |
| Produção, mil litros | 5.000; 10.000; 20.000; 50.000 |
| Vacas ordenhadas, cabeças | 2.000; 5.000; 15.000; 30.000 |
| Densidade de produção, L/km² | 5.000; 25.000; 60.000; 85.000 |
| Densidade de ordenha, cabeças/km² | 3; 8; 14; 23 |
| Produtividade, L/cabeça | 500; 1.500; 3.000; 4.000 |

### Presets pessoais

Na tela de configuração de um indicador, selecione **Meus presets**, ao lado de **Cileite**. Para criar, informe o nome e os limites superiores dos bins (por exemplo, `2000, 5000, 15000, 30000`) e clique em **Criar preset**. Ele aparece na lista e fica selecionado para gerar os mapas. Para reutilizar, escolha seu nome nessa lista; os limites aparecem logo abaixo. **Excluir** remove o preset salvo após confirmação.

Ao selecionar um preset existente, o nome e os limites são preenchidos para edição. Clique em **Salvar alterações** para atualizar o mesmo preset. **Novo preset** limpa a seleção e os campos para cadastrar outro. A geração usa os limites salvos: salve suas alterações antes de gerar mapas.

Cada conta vê somente seus próprios presets, separados por cultura e indicador. Novos presets guardam os limites informados como valores fixos, com uma classe aberta acima do último limite. Configurações de cálculo salvas anteriormente continuam disponíveis. Nomes duplicados no mesmo indicador e conta são rejeitados.

Os presets persistem em `runtime/jobs.sqlite` (ou no diretório definido por `RUNTIME_DIR`), junto aos trabalhos. Inclua esse arquivo no backup do servidor para preservar as configurações pessoais. A limpeza de trabalhos antigos não remove presets.
