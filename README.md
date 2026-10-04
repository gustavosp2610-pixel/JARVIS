# J.A.R.V.I.S.

Assistente pessoal no estilo do JARVIS do Homem de Ferro. Você chama ele pelo nome, fala o que quer e ele faz no seu computador, no Gmail e na Google Agenda, respondendo em voz alta. Quem pensa por trás é o Claude (Anthropic).

Ao ligar, abre uma **tela estilo HUD** no navegador: o reator arc no centro reage quando ele ouve, pensa e fala; nas laterais ficam o estado do PC (CPU, memória, bateria, disco), sua agenda de hoje, os e-mails não lidos e o que ele lembra sobre você. Ações sensíveis aparecem num aviso de **Autorização necessária**, que você aprova com um clique ou dizendo "sim".

```
Você:   "Jarvis, abre o Spotify e coloca o volume em 30."
JARVIS: "Spotify aberto e volume em trinta por cento, senhor."

Você:   "Jarvis, tenho algum compromisso amanhã?"
JARVIS: "Apenas a reunião com a equipe às dez, senhor."

Você:   "Manda um e-mail pro João dizendo que vou me atrasar."
JARVIS: "Antes, preciso da sua autorização para enviar email... Posso prosseguir?"
Você:   "Pode."
```

## O que ele consegue fazer

| Área | Exemplos de pedidos |
|---|---|
| Programas e sites | "abre o Chrome", "fecha o Word", "abre o youtube.com", "pesquisa receita de bolo" |
| Música e mídia | "toca Back in Black no YouTube", "pausa", "próxima música", "volume em 40", "muta" |
| Arquivos | "o que tem na pasta Downloads?", "procura meu currículo", "abre o PDF da fatura", "cria uma nota com minha lista de compras", "manda esse arquivo pra lixeira" |
| Sistema | "como tá a bateria?", "tira um print", "bloqueia o PC", "desliga o computador em 30 minutos" |
| Gmail | "tenho e-mails não lidos?", "lê o último e-mail do banco", "responde pro Carlos dizendo que topo" |
| Agenda | "o que tenho hoje?", "marca dentista sexta às 15h" |
| Internet | "qual a previsão do tempo?", "quais as notícias de hoje?", "quanto tá o dólar?" |
| Qualquer pergunta | "como funciona um buraco negro?", "me explica juros compostos", "escreve um código em Python que…", "me ajuda a estudar para a prova de história" |
| Memória | "lembra que minha academia é às 7h", "o que você lembra sobre mim?", "esquece isso da academia" |
| Timers | "me lembra de tirar o bolo do forno em 40 minutos" |
| Avançado | "roda um comando do PowerShell que mostre meu IP" |

### Segurança

- Ações que mudam ou apagam algo (**enviar e-mail, criar evento, apagar/mover/escrever arquivo, fechar programa, desligar o PC, rodar comando**) só acontecem depois que você diz **"sim"**.
- Arquivos apagados vão para a **Lixeira**, então dá para recuperar.
- O acesso a arquivos fica restrito à sua pasta de usuário (`C:\Users\voce`). Se quiser liberar outras pastas, use `JARVIS_PASTAS_PERMITIDAS` no `.env`.
- Ele não segue instruções escritas dentro de e-mails, arquivos ou páginas da web.
- A tela só funciona no seu próprio computador (`localhost`) e usa uma senha nova a cada vez que liga, então outros sites ou pessoas na sua rede não conseguem dar ordens a ele.
- Sua chave e o login do Google ficam só no seu PC (`.env` e `dados/`), e esses arquivos nunca vão para o Git.

## Instalação no Windows (passo a passo)

### 1. Instale o Python
Baixe o **Python 3.11 ou mais novo** em https://www.python.org/downloads/. Na instalação, marque **"Add python.exe to PATH"**.

### 2. Baixe o projeto
```powershell
git clone https://github.com/gustavosp2610-pixel/JARVIS.git
cd JARVIS
```
(ou baixe o ZIP pelo GitHub e extraia)

### 3. Crie um ambiente e instale as dependências
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
> Se o `PyAudio` der erro, rode `pip install pipwin` e depois `pipwin install pyaudio`, ou baixe a versão pronta do PyAudio para a sua versão do Python.

### 4. Pegue sua chave do Claude
1. Crie uma conta em https://console.anthropic.com e adicione créditos (é cobrado por uso, normalmente centavos por conversa).
2. Em **API Keys**, crie uma chave.
3. Copie `.env.example` para `.env` e cole a chave em `ANTHROPIC_API_KEY=`. Aproveite e coloque seu nome e cidade.

### 5. Ligue o JARVIS
Dê dois cliques em **`iniciar_jarvis.bat`** (ou rode `python -m jarvis`). A tela abre sozinha no navegador em `http://localhost:8765`. Deixe a janela preta aberta, porque é ela que executa as ordens no seu PC.

Na tela:
- **Clique no reator ou no microfone** e fale um pedido. Também dá para digitar.
- **Sempre ouvindo**: ele fica escutando e responde quando você diz "Jarvis, ...". Depois de cada resposta, você pode continuar falando por alguns segundos sem repetir o nome.
- **Sem voz**: ele responde só por escrito.
- Use o **Chrome ou o Edge** (o reconhecimento de voz funciona neles). Na primeira vez, permita o acesso ao microfone.

Outros modos, sem a tela:
```powershell
python -m jarvis --voz             # só voz, no terminal
python -m jarvis --texto           # conversa digitando no terminal
python -m jarvis --texto --falar   # digita e ele responde falando
```

## Conectar Gmail e Agenda (opcional, uma vez só)

1. Acesse https://console.cloud.google.com e crie um projeto (ex.: "Jarvis").
2. Em **APIs e serviços → Biblioteca**, ative **Gmail API** e **Google Calendar API**.
3. Em **APIs e serviços → Tela de consentimento OAuth**, escolha **Externo**, preencha o nome do app e, em **Usuários de teste**, adicione o seu próprio e-mail.
4. Em **APIs e serviços → Credenciais → Criar credenciais → ID do cliente OAuth**, escolha **App para computador**. Baixe o JSON.
5. Renomeie o arquivo para `credentials.json` e coloque na pasta `dados/` do projeto.
6. Rode:
   ```powershell
   python -m jarvis --google
   ```
   O navegador vai abrir para você fazer login e autorizar. Pronto, o JARVIS já pode ler e enviar e-mails e mexer na sua agenda.

## Personalizando

Tudo fica no `.env`:

| Variável | Para que serve |
|---|---|
| `JARVIS_NOME_USUARIO` | Como ele te chama ("senhor", "Gustavo", "chefe"...) |
| `JARVIS_VOZ` | Voz da fala. Ex.: `pt-BR-AntonioNeural`, `pt-BR-FranciscaNeural`, `en-GB-RyanNeural` (sotaque britânico como no filme) |
| `JARVIS_PALAVRA_ATIVACAO` | A palavra que acorda o assistente |
| `JARVIS_ESFORCO` | `medium` (padrão) equilibra rapidez e qualidade; `low` responde mais rápido e gasta menos; `high` pensa mais nas perguntas difíceis |
| `JARVIS_PESQUISA_WEB` | `false` desliga a pesquisa na internet |

A personalidade está em `jarvis/personality.py`.

### Criando novas habilidades

Qualquer função vira uma ferramenta do JARVIS com o decorador `@ferramenta`. Crie um arquivo em `jarvis/tools/`, importe ele em `carregar_todas()` (`jarvis/tools/__init__.py`) e pronto:

```python
from jarvis.tools import CONFIRMAR, ferramenta

@ferramenta(
    "acender_luz",
    "Acende a luz de um cômodo.",
    {"comodo": {"type": "string"}},
    ["comodo"],
    risco=CONFIRMAR,   # opcional: pede "sim" antes de executar
)
def acender_luz(comodo: str) -> str:
    ...
    return f"Luz da {comodo} acesa."
```

## Estrutura

```
iniciar_jarvis.bat clique duas vezes para ligar (Windows)
jarvis/
  main.py          escolhe o modo (tela, voz ou texto)
  web/             a tela HUD (index.html) e o servidor local que a conecta ao PC
  brain.py         conversa com o Claude e executa as ferramentas (com confirmação)
  personality.py   personalidade do JARVIS
  memory.py        memória de longo prazo (dados/memoria.json)
  config.py        lê o .env
  voice/           microfone (SpeechRecognition) e fala (edge-tts / pyttsx3)
  tools/           computador, Gmail e Agenda
tests/             testes automáticos (python -m pytest)
```
