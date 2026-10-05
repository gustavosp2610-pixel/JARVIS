# J.A.R.V.I.S.

Assistente pessoal no estilo do JARVIS do Homem de Ferro. Você chama ele pelo nome, fala o que quer e ele faz no seu computador, no Gmail e na Google Agenda, respondendo em voz alta. Quem pensa por trás é o Google Gemini (grátis) ou, se você preferir, o Claude (Anthropic).

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
| Tarefas e lembretes | "coloca pagar a luz na minha lista", "me lembra de tirar o bolo em 40 minutos", "todo dia às 7h me lembra da academia", "o que tenho pendente?" |
| Ver a tela | "o que é isso na minha tela?", "me ajuda com esse erro que apareceu" |
| Mouse e teclado | "abre o bloco de notas e escreve um poema", "entra no YouTube e coloca o último vídeo do canal X" (ele pede autorização uma vez e faz tudo sozinho) |
| WhatsApp | "salva o número do João: 11 98765-4321", "manda no WhatsApp pro João que chego em 10 minutos" |
| Rotinas | "bom dia", "modo trabalho", "modo foco" (botões na tela), "cria a rotina modo jogo: abrir a Steam, abrir o Discord e volume em 70" |
| Estudos | "resume o PDF da aula que está em Downloads", "faz 10 flashcards desse PDF e salva como anotação", "resume esse artigo: <link>", "começa um pomodoro de 4 ciclos", "traduz o texto que eu copiei" |
| Anotações | "anota: ideia para o projeto…", "o que eu anotei sobre história?" |
| Dinheiro | "gastei 45 reais no mercado", "recebi 500 do freela", "quanto gastei esse mês?", "quanto tá o dólar e o bitcoin?" |
| Dia a dia | "vai chover amanhã?", "previsão para o fim de semana em Santos", "quais as notícias de hoje?", "notícias do Flamengo" |
| Organizar o PC | "analisa minha pasta Downloads", "organiza meus Downloads" (mostra o plano e pede autorização), "quais arquivos grandes eu tenho?", "limpa os arquivos temporários", "esvazia a lixeira" |
| Avançado | "roda um comando do PowerShell que mostre meu IP" |

### Segurança

- Ações que mudam ou apagam algo (**enviar e-mail ou WhatsApp, criar evento, apagar/mover/escrever arquivo, fechar programa, desligar o PC, rodar comando**) só acontecem depois que você diz **"sim"**.
- Para usar **mouse e teclado**, ele pede autorização **uma vez por pedido** e depois trabalha sozinho até terminar. Para interromper a qualquer momento: botão **Parar** na tela, ou jogue o mouse no **canto superior esquerdo** da tela.
- Ele só fala quando você chama. A única exceção são os lembretes que você mesmo pediu.
- Arquivos apagados vão para a **Lixeira**, então dá para recuperar.
- O acesso a arquivos fica restrito à sua pasta de usuário (`C:\Users\voce`). Se quiser liberar outras pastas, use `JARVIS_PASTAS_PERMITIDAS` no `.env`.
- Ele não segue instruções escritas dentro de e-mails, arquivos ou páginas da web.
- A tela só funciona no seu próprio computador (`localhost`) e usa uma senha nova a cada vez que liga, então outros sites ou pessoas na sua rede não conseguem dar ordens a ele.
- Sua chave e o login do Google ficam só no seu PC (`.env` e `dados/`), e esses arquivos nunca vão para o Git.

## Instalação no Windows

**Passo a passo completo e simples: [COMO_INSTALAR.md](COMO_INSTALAR.md).** Em resumo:

1. Baixe o ZIP do projeto e extraia.
2. Dê dois cliques em **`instalar_jarvis.bat`**. Ele instala o Python (se faltar) e as bibliotecas, pede sua **chave grátis do Gemini** e testa a voz.
3. Ligue pelo atalho **JARVIS** na Área de Trabalho (ou `iniciar_jarvis.bat`). A tela abre no navegador em `http://localhost:8765`.

### Quanto custa?

**Nada.** O cérebro padrão é o **Google Gemini** no plano gratuito: só precisa de uma conta Google, sem cartão. O plano grátis tem limite de pedidos por minuto e por dia, suficiente para uso pessoal. A voz (Microsoft Edge) e o reconhecimento de voz (navegador) também são grátis.

Opcional e pago por uso: dá para trocar o cérebro pelo **Claude** (`JARVIS_IA=claude` e `ANTHROPIC_API_KEY` no `.env`). Com o Claude, o controle de mouse e teclado é mais preciso.

Na tela:
- **Clique no reator ou no microfone** e fale um pedido. Também dá para digitar.
- **Sempre ouvindo**: ele fica escutando e responde quando você diz "Jarvis, ...". Depois de cada resposta, você pode continuar falando por alguns segundos sem repetir o nome.
- **Sem voz**: ele responde só por escrito.
- Use o **Chrome ou o Edge** (o reconhecimento de voz funciona neles). Na primeira vez, permita o acesso ao microfone.

Para mudar nome, cidade ou a chave depois: `python -m jarvis --configurar`.

> Nos comandos deste README, `python` é o Python do JARVIS: abra o PowerShell na pasta do projeto e use `.venv\Scripts\python.exe` no lugar de `python` (ex.: `.venv\Scripts\python.exe -m jarvis --configurar`).

Outros modos, sem a tela (o modo `--voz` precisa de `pip install -r requirements-opcional.txt`):
```powershell
python -m jarvis --voz             # só voz, no terminal
python -m jarvis --texto           # conversa digitando no terminal
python -m jarvis --texto --falar   # digita e ele responde falando
```

## Conectar o Gmail (2 minutos)

Para o JARVIS ler e enviar seus e-mails ("manda um e-mail pro meu pai dizendo que está tudo bem"):

1. Sua conta Google precisa estar com a **verificação em duas etapas** ligada (myaccount.google.com → Segurança).
2. Dê dois cliques em **`conectar_gmail.bat`**, na pasta do JARVIS. O instalador também oferece esse passo.
3. Ele abre https://myaccount.google.com/apppasswords. Em "Nome do app" digite **JARVIS**, clique em **Criar** e copie a senha de 16 letras.
4. Cole a senha. Ele testa envio e leitura na hora e só salva se funcionar. Se o Google recusar, ele explica as causas comuns e deixa tentar de novo.
5. Reinicie o JARVIS.

Antes de enviar, ele sempre mostra o e-mail pronto (**para, assunto e texto**) e só envia quando você autoriza. Para não ditar endereços toda vez: "o e-mail do meu pai é anderson@gmail.com". Depois é só dizer "manda um e-mail pro meu pai…".

**Gmail recusou a senha?** Quase sempre é a senha normal da conta colada no lugar da senha de app, ou a senha de app copiada pela metade. Crie uma nova em myaccount.google.com/apppasswords e dê dois cliques em `conectar_gmail.bat`.

## Conectar a Google Agenda (opcional, mais trabalhoso)

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

## Atualizações automáticas

Toda vez que você abre o JARVIS pelo atalho, ele confere no GitHub se existe uma versão nova. Se existir, baixa e aplica sozinho, depois abre já atualizado. Você vê "Baixando atualização: …" na janela preta.

- Seu `.env` (chave do Gemini, senha do Gmail), a pasta `dados/` (tarefas, gastos, rotinas, memórias) e as bibliotecas (`.venv`) **nunca são trocados**.
- Se a atualização trouxer bibliotecas novas, ele instala sozinho.
- Sem internet, ele só abre a versão que já tem.
- Para desligar: `JARVIS_ATUALIZAR_SOZINHO=false` no `.env`.

## Se o Gemini falhar

O plano grátis às vezes fica sobrecarregado. O JARVIS tenta de novo sozinho (até 3 vezes) e, se continuar, usa o modelo reserva (`gemini-flash-lite-latest`). Se mesmo assim falhar, o erro exato aparece na janela preta e no **Registro de operações** da tela.

## A voz

O JARVIS usa vozes neurais da Microsoft (as mesmas do Edge), de graça. Clique em **Voz** na tela para escolher a voz e ajustar velocidade e tom. Depois clique em **Testar e salvar**. As vozes "Multilíngue" (ex.: Brian, Andrew) falam português com um leve sotaque estrangeiro, bem estilo filme.

Se a voz sair robótica, a voz neural falhou e ele usou a voz reserva. A tela avisa o motivo. Para diagnosticar:

```powershell
python -m jarvis --testar-voz
pip install -U edge-tts   # resolve a maioria dos casos
```

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
instalar_jarvis.bat instalador de 2 cliques (Windows)
iniciar_jarvis.bat clique duas vezes para ligar (Windows)
jarvis/
  main.py          escolhe o modo (tela, voz ou texto)
  web/             a tela HUD (index.html) e o servidor local que a conecta ao PC
  brain.py         cérebro com Claude + criar_cerebro() que escolhe Gemini ou Claude
  cerebro_gemini.py cérebro grátis com Google Gemini
  configurar.py    assistente de configuração (--configurar)
  personality.py   personalidade do JARVIS
  memory.py        memória de longo prazo (dados/memoria.json)
  config.py        lê o .env
  voice/           microfone (SpeechRecognition) e fala (edge-tts / pyttsx3)
  tools/           computador, Gmail e Agenda
tests/             testes automáticos (pip install -r requirements-dev.txt; python -m pytest)
```
