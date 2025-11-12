# Eos Cafés Especiais – Bot de Estoque no Telegram

Bem-vindo ao sistema conversacional que gerencia as entradas e saídas de estoque da Eos Cafés Especiais diretamente pelo Telegram. O bot entrega uma experiência amigável em português, usa a Groq para perguntas inteligentes e persiste todas as movimentações em um banco PostgreSQL.

## Principais Funcionalidades
- **Menu principal moderno**: `/start` abre um painel acolhedor com Entrada, Saída, Estoque, Histórico e IA organizados lado a lado.
- **/entrada**: seleciona categoria, produto e quantidade usando teclado rápido (1, 5, 10, 15, 30, 50 ou valor personalizado).
- **/saida**: mesma experiência guiada da entrada, com validação de estoque e registro de brindes opcionais.
- **/estoque**: exibe apenas os produtos e quantidades disponíveis, com botão para retornar ao menu principal.
- **/historico** / **/historicoSaida**: mostra as últimas saídas no formato “data • produto → quantidade” e inclui apenas o botão de retorno.
- **/IAEos**: abre um painel inteligente com sugestões automáticas, relatórios, resumo semanal e a possibilidade de perguntar em linguagem natural (modelo `llama-3-70b`).

## Arquitetura
- **Python 3.11+** com `asyncio` e `python-telegram-bot` v21.
- **PostgreSQL** para armazenar produtos e movimentações (`tb_produtos`, `tb_movimentacoes`).
- **psycopg** para acesso ao banco e criação automática das tabelas.
- **httpx** para a integração assíncrona com a API da Groq.
- Projeto organizado em módulos (`app/`) para facilitar manutenção e futuras integrações (ex.: dashboard web).

## Preparação do Ambiente
1. Crie um ambiente virtual e instale as dependências:
	```bash
	python -m venv .venv
	.venv\Scripts\activate  # Windows
	pip install -r requirements.txt
	```
2. Configure um banco PostgreSQL e garanta acesso ao usuário configurado.
3. Copie o arquivo `.env.example` para `.env` e preencha:
	```ini
	TOKEN_TELEGRAM=seu_token
	DB_USER=postgres
	DB_PASS=senha
	DB_HOST=localhost
	DB_PORT=5432
	DB_NAME=eos_cafes
	GROQ_API_KEY=sua_chave_groq
	```
4. Ao iniciar o bot, as tabelas são criadas automaticamente e os produtos padrão são cadastrados.

## Execução
```bash
python main.py
```
A aplicação inicia o polling do Telegram e registra todas as interações.

## Dashboard Web (Coffee Matrix)
Um painel premium focado em branding para a "Eos Cafés Especiais" com tema escuro, detalhes dourados e visual moderno para acompanhar o estoque e o histórico.

Recursos principais:
- Tema dark sofisticado com glassmorphism (backdrop-filter: blur(10px)) e animações suaves.
- Métricas no topo: Total de Itens, Valor Estimado, Movimentações recentes e Total de Brindes.
- Filtros dinâmicos: Tudo, Cafés, Embalagens e Brindes (afetam tabelas e gráficos).
- Gráficos (Chart.js):
	- Barra: Estoque atual por produto.
	- Pizza: Proporção de cafés por produto.
	- Linha: Série temporal de Entradas, Saídas e Brindes.
- Auto-atualização a cada 30s via AJAX (/api/data) e botão "Atualizar" com loading.
- Modo claro/escuro alternável e persistente (localStorage).

Como executar (2 terminais, PowerShell no Windows):
```powershell
# 1) Ative o ambiente virtual
.venv\Scripts\activate

# 2) Instale as dependências (se necessário)
pip install -r requirements.txt

# 3) Terminal A — Inicie o bot do Telegram
python main.py

# 4) Terminal B — Inicie o Dashboard Web
python dashboard.py
```
Acesse em: http://localhost:5000/dashboard

Endpoints do dashboard:
- /dashboard — interface HTML principal
- /api/data — dados em JSON (estoque, movimentos e séries para gráficos)

Tecnologias do dashboard:
- Flask (servidor e rotas)
- Bootstrap 5 (layout responsivo)
- Chart.js (gráficos de barra/pizza/linha)
- Vanilla JS (auto-refresh, filtros e tema)

Estrutura do dashboard:
```
dashboard.py              # Rotas /dashboard e /api/data
templates/
	dashboard.html          # Interface premium (tema escuro + dourado)
static/
	css/dashboard.css       # Estilos (glassmorphism, transições, tema)
	js/dashboard.js         # Lógica (gráficos, filtros, auto-refresh, tema)
```

Observação: existe um arquivo antigo `dashboard_server.py` utilizado como protótipo inicial. Use `dashboard.py` como servidor oficial do dashboard.

## Estrutura Resumida
```
app/
  bot.py          # Lógica do bot e fluxos conversacionais
  config.py       # Carregamento e validação de variáveis de ambiente
  database.py     # Acesso ao PostgreSQL e manipulação de estoque
  groq_client.py  # Cliente para a API Groq
  keyboards.py    # Construção dos menus interativos do Telegram
  products.py     # Lista inicial de produtos e matérias-primas
main.py           # Ponto de entrada da aplicação
.env.example      # Configurações necessárias
requirements.txt  # Dependências do projeto
 dashboard.py      # Servidor do dashboard / API JSON
 templates/dashboard.html
 static/css/dashboard.css
 static/js/dashboard.js
```

## Próximos Passos
- Expor APIs REST (Flask/FastAPI) para dashboards.
- Adicionar relatórios automáticos agendados no Telegram.
- Criar alertas de estoque mínimo usando a Groq.

Com isso, a equipe da Eos Cafés Especiais ganha um assistente digital elegante e inteligente para controlar o estoque em tempo real. ☕
