# Biblioteca Rovuma

Biblioteca digital e catálogo do acervo físico da Universidade Rovuma. A aplicação reúne a pesquisa e a leitura de obras, a localização de exemplares e a gestão do acervo, dos documentos e do credenciamento de estudantes. O acesso é reservado a contas autorizadas.

**Ambiente de teste:** [Portal do leitor](https://biblioteca-web-teste.up.railway.app/portal/) · [Catálogo](https://biblioteca-web-teste.up.railway.app/catalogo/) · [Painel administrativo](https://biblioteca-web-teste.up.railway.app/admin/)

## O que foi implementado

O [PR #10](https://github.com/MergiorGoriate/Biblioteca-Rovuma/pull/10) integrou no ramo `main` a interface actualizada do painel administrativo, incluindo o tema escuro e a navegação adaptada a telemóvel.

### Portal e catálogo

- Pesquisa por título, subtítulo, autor, assunto, palavra-chave ou identificador. O catálogo tem filtros por tipo, idioma, ano e formato, incluindo obras digitais, físicas ou disponíveis nos dois formatos.
- Página inicial com obras em destaque e a secção **Continuar a ler**. A ficha de cada obra apresenta edições, identificadores, modalidades de acesso digital e, quando aplicável, exemplares para consulta local.
- O catálogo pode ser filtrado pelas colecções publicadas pela biblioteca. Na ficha da obra, é possível descarregar a referência de cada edição em RIS ou BibTeX. Os estudantes podem guardar obras digitais ou físicas em **Minhas leituras**.
- Inventário físico com unidade, sala, estante e prateleira. A contagem indica os exemplares registados para consulta local. A disponibilidade imediata confirma-se na biblioteca.
- Leitor de PDF no navegador com navegação por página, ajuste de largura, pesquisa no texto quando disponível, marcadores e retoma da última página. **Minhas leituras** reúne o progresso e os marcadores do estudante.
- No ambiente de teste, o portal e o painel têm uma interface adaptada a computador e telemóvel, com navegação por ícones e modos claro e escuro que guardam a preferência. As barras superiores de pesquisa ficam fixas durante a deslocação. No catálogo, os filtros ficam na barra superior e a barra de deslocação fica na extremidade direita da página.

### Painel administrativo

- Entrada própria em `/admin/entrar/` e painel em `/admin/`. As secções disponíveis dependem das permissões da conta. As ligações anteriores em `/gestao/` encaminham para o painel actual.
- Visão geral com contagens do acervo, da fila de documentos e do credenciamento. Os atalhos conduzem às listas correspondentes.
- Gestão de obras, edições, autores, assuntos, identificadores, capas, localizações e exemplares físicos. O inventário permite pesquisar por obra, localização ou número de inventário.
- Em **Obras e edições → Colecções**, a equipa bibliotecária pode criar e publicar colecções por curso ou disciplina. A associação é feita no formulário de cada obra.
- Pesquisa de obras pelo título, filtro por estado e acção **Nova obra**. A barra superior fixa no ambiente de teste mantém acessíveis a pesquisa, a mudança de tema, **Abrir portal** e **Sair**. Em telemóvel, os atalhos administrativos estão no **Menu administrativo**.
- Fila com estados de processamento e revisão, motivo de falha e opção de reagendar. O bibliotecário regista a autorização de uso, pré-visualiza o PDF, confirma a revisão e publica. Quando uma nova versão é publicada, a anterior passa para o histórico.

### Contas, acesso e auditoria

- Contas individuais para funcionários, com convites de activação e atribuição explícita de permissões editoriais, técnicas ou de correcção. Os estudantes entram com o número institucional, que é guardado como texto para preservar os zeros iniciais.
- Importação de estudantes por CSV com pré-visualização e erros por linha. O painel permite gerir a validade do credenciamento, emitir ligações de activação de uso único, suspender e reactivar contas. As correcções de número exigem permissão específica e justificação.
- Activação e alteração de palavra-passe, mensagens de validação nos formulários e recuperação pelo endereço previamente validado. A entrega de correio pode ser configurada por SMTP ou pela API do Resend. A alteração da palavra-passe e a suspensão invalidam sessões anteriores.
- Registo de acções administrativas e verificação da validade da conta e das permissões nos pedidos de leitura e descarregamento, incluindo pedidos parciais de PDF. No modo **Só leitura**, a aplicação bloqueia o descarregamento pela rota própria. Os bytes já entregues ao navegador podem ser copiados ou capturados.

### Documentos e infra-estrutura

- Carregamento de PDF, DOCX, ODT e TXT (UTF-8) em partes, com retoma de transferências e limpeza das transferências expiradas. Os ficheiros ficam em quarentena até à validação do formato e à análise antivírus. O processador converte DOCX, ODT e TXT em PDF para revisão.
- A aplicação usa Python 3.12 e Django, com SQLite em desenvolvimento local e PostgreSQL na instalação alojada. Os metadados ficam na base de dados e o acervo fica em armazenamento privado. O leitor usa PDF.js.
- A instalação via `compose.yaml` inclui PostgreSQL, Gunicorn, Caddy, um despachante e um processador sem rede. O ramo principal inclui também `compose.processor.yaml` para [instalar o processador num servidor separado](https://github.com/MergiorGoriate/Biblioteca-Rovuma/blob/main/docs/operacoes.md#processador-num-servidor-separado) e ligar o despachante a um gateway HTTPS autenticado. Nesse modo, o conversor trabalha sem rede e o actualizador de assinaturas ClamAV corre num contentor próprio.
- O procedimento de cópia e restauro inclui cópias encriptadas com Restic e recuperação conjunta da base de dados e dos ficheiros privados. O restauro local foi ensaiado com PostgreSQL e com verificação da integridade e leitura autorizada de um PDF.

## Obras de demonstração

O ambiente de teste tem quatro livros fictícios com capas próprias. Três têm PDF e dois têm exemplares fictícios no inventário.

| Obra | Acesso de teste |
| --- | --- |
| Métodos de investigação científica | Só leitura |
| Fundamentos de biologia | Leitura, descarregamento e consulta local |
| Ecologia e conservação | Só leitura |
| Escrita académica | Consulta local |

## Executar localmente

Clone o repositório e instale as dependências com Python 3.12. O ramo `main` já inclui a interface do painel integrada pelo PR #10.

```sh
git clone https://github.com/MergiorGoriate/Biblioteca-Rovuma.git
cd Biblioteca-Rovuma
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

Em Windows, active o ambiente com `.venv\Scripts\activate` ou execute `.venv\Scripts\python.exe` directamente. Abra o [portal local](http://127.0.0.1:8000/portal/) ou a [entrada administrativa local](http://127.0.0.1:8000/admin/entrar/).

Para experimentar com SQLite, defina `DEMO_STUDENT_PASSWORD` e `DEMO_STAFF_PASSWORD` no ambiente com palavras-passe escolhidas por si e execute `python manage.py demo_rovuma`. O comando cria as contas locais `000042` e `bibliotecario.demo` e uma obra fictícia adicional. No ambiente local de desenvolvimento, execute `python manage.py seed_sample_books --confirm-test-environment` para carregar os quatro livros da tabela.

Para ensaiar o processamento local, instale ClamAV com as respectivas assinaturas e LibreOffice Writer. Com o servidor de desenvolvimento activo, execute `python manage.py dispatch_documents` e `python -m documents.worker --spool var/spool` em terminais separados. Para ensaios locais com ficheiros fictícios, o processador aceita a opção `--development-no-antivirus`. Para uma instalação de uso real, siga o [procedimento de instalação e primeiro convite](docs/operacoes.md#produção). As migrações criam a estrutura de uma base vazia e a primeira conta de serviço é criada por convite.

## Testes

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

A suite verifica permissões, activação, recuperação da palavra-passe, importação, pesquisa, leitura de PDFs, transferência de documentos, publicação e auditoria. Para repetir a validação visual do ramo de teste, prepare as duas contas e as obras de demonstração, mantenha o servidor local activo e execute:

```sh
python -m pip install playwright
python -m playwright install chromium
python ops/browser_smoke.py
```

O ensaio em Chromium verifica a interface em dimensões de computador e telemóvel, incluindo as barras fixas, os filtros, a mudança de tema e o leitor. O processamento de documentos tem validação própria no GitHub Actions. O correio local é simulado em memória. A entrega a destinatários reais depende da configuração do remetente e do serviço de correio.

- [Validação da interface em computador e telemóvel](https://github.com/MergiorGoriate/Biblioteca-Rovuma/actions/runs/43934769411)
- [Resultados dos ensaios locais com SQLite, PostgreSQL e restauro](docs/resultados/)

## Estado da instalação

Na verificação de 17 de Novembro de 2026, o projecto tinha um ambiente `teste` no Railway. A aplicação Web e o PostgreSQL estavam activos e o [serviço de processamento](https://railway.com/project/d011fa3c-6791-4cff-a62f-be1a6eed3ff3/service/9d64126d-d2ae-439c-bcf6-2e0b949e34d7?environmentId=632543be-e6be-4848-b52b-0c0c4ba499c2) estava offline. A revisão publicada em teste era [`33685ef`](https://github.com/MergiorGoriate/Biblioteca-Rovuma/commit/33685efbcae5aa0a9de6a26b20ed35a6bf4342cd), do ramo `reconstrucao-modulos`. As obras fictícias já processadas continuam disponíveis para demonstração com contas autorizadas.

## O que falta para o piloto

- **Activar e validar o processador.** Ligar o despachante a um processador com capacidade suficiente, actualizar as assinaturas oficiais do ClamAV e ensaiar o percurso da quarentena à publicação com um PDF e um DOCX. Se o alojamento Web continuar no Railway, o [procedimento de instalação num servidor separado](docs/operacoes.md#processador-num-servidor-separado) descreve uma opção para o processador.
- **Preparar a instalação institucional.** Confirmar com a Universidade Rovuma o alojamento, o domínio com HTTPS, os responsáveis pela operação e a separação entre teste e produção.
- **Preparar as contas e o acervo inicial.** Seleccionar um curso ou uma faculdade para o piloto, registar as obras e localizações reais e documentar os direitos de consulta e descarregamento. Usar a importação CSV com uma lista institucional validada enquanto se avalia a ligação ao portal académico.
- **Validar o correio e as cópias externas.** Confirmar a entrega e o uso de uma ligação real de recuperação de palavra-passe. Agendar cópias encriptadas da base e dos ficheiros privados, testar o restauro conjunto num ambiente isolado e atribuir a alguém a resposta a falhas do processador e das cópias.
- **Testar com estudantes e bibliotecários.** Confirmar pesquisa, retoma de leitura, localização de exemplares físicos e publicação de uma obra. Incluir telemóveis e ligações móveis no ensaio.

## Recursos a adicionar

- **Importação do acervo em lote.** Importar obras, edições e exemplares por CSV, com pré-visualização, detecção de duplicados e erros por linha.
- **Referências em APA.** Acrescentar à ficha uma referência em APA, com metadados adequados a cada tipo de publicação.

## Recursos avançados propostos

- **Pesquisa no texto integral e OCR.** Indexar o texto dos PDFs autorizados para que as obras possam ser encontradas por termos do conteúdo. Aplicar reconhecimento óptico de caracteres às digitalizações que o precisem. A pesquisa e os excertos devem respeitar as permissões de cada obra.
- **Autenticação institucional.** Integrar o início de sessão com o portal académico e actualizar o credenciamento a partir de uma fonte oficial depois de a Universidade confirmar o fornecedor de identidade, o protocolo e as regras de acesso.
- **Integração com um repositório académico.** Permitir o intercâmbio de metadados de monografias e outras publicações autorizadas, de acordo com as regras institucionais de divulgação e embargo.
- **Indicadores de utilização do acervo.** Apresentar consultas e descarregamentos autorizados por colecção ou período, com dados agregados para apoiar decisões sobre o acervo.

## Documentação

- [Instalação, actualização e recuperação](docs/operacoes.md)
- [Manual do bibliotecário](docs/bibliotecario.md)
- [Arquitectura de referência](docs/arquitectura.md) e [diagrama técnico](docs/arquitectura.svg)
- [Modelo de dados](docs/modelo-de-dados.md)
- [Validação e dependências](docs/validacao.md)
