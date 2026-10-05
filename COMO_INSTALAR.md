# Como instalar o JARVIS no seu PC (Windows) — grátis

São 3 passos. Leva uns 10 minutos, quase tudo esperando o download.

## 1. Baixe o JARVIS

1. Abra este link (precisa estar logado no seu GitHub):
   https://github.com/gustavosp2610-pixel/JARVIS/archive/refs/heads/claude/jarvis-iron-man-assistant-5dpk4u.zip
2. O arquivo `.zip` vai para a pasta **Downloads**.
3. Clique com o botão direito no `.zip` → **Extrair tudo…** → **Extrair**.
   Dica: mova a pasta extraída para um lugar fixo, como `Documentos\JARVIS`, antes de instalar.

## 2. Rode o instalador

1. Entre na pasta extraída e dê **dois cliques em `instalar_jarvis.bat`**.
2. Se aparecer **"O Windows protegeu o computador"**: clique em **Mais informações** → **Executar assim mesmo**.
   (Aparece porque o arquivo foi baixado da internet. O instalador é este mesmo, você pode abrir no Bloco de Notas para ler.)
3. O instalador faz sozinho:
   - instala o Python, se faltar. Nesse caso, ele pede para você **abrir o instalador de novo** no final;
   - instala tudo que o JARVIS precisa (alguns minutos);
   - abre a configuração.

## 3. Configure (o instalador pergunta)

1. **Como ele deve te chamar** e **sua cidade**.
2. **Chave grátis do Gemini**, que é o cérebro do JARVIS:
   - o navegador abre em https://aistudio.google.com/apikey (entre com sua conta Google);
   - clique em **Create API key / Criar chave de API** e copie a chave;
   - volte na janela preta e cole com **botão direito do mouse**, depois aperte **Enter**.
   O instalador testa a chave na hora e avisa se tiver algo errado.
3. **Gmail** (opcional): ele oferece conectar seu Gmail com uma "senha de app". Siga as instruções da janela, é rápido.
4. **Teste da voz**: você deve ouvir "Sistemas de voz online. Às suas ordens, senhor."

No final ele cria o atalho **JARVIS** na Área de Trabalho. É só dar dois cliques nele para ligar.

## Usando

- O atalho abre uma janela preta (deixe aberta, é ela que executa as ordens) e a tela do JARVIS no navegador.
- Use o **Chrome** ou o **Edge**. Na primeira vez, clique em **Permitir** quando ele pedir o microfone.
- Clique no reator (ou no microfone) e fale, ou digite.
- Ligue **Sempre ouvindo** para chamar dizendo "Jarvis, …".

## Deu problema?

| O que aparece | O que fazer |
|---|---|
| "Atingi o limite gratuito do Gemini" | O plano grátis tem limite por minuto e por dia. Espere alguns minutos. |
| "Minha chave do Gemini parece inválida" | Dê dois cliques em `instalar_jarvis.bat` de novo e cole outra chave. |
| Voz robótica | Na janela preta: feche, e rode `.venv\Scripts\python.exe -m jarvis --testar-voz` dentro da pasta para ver o motivo. |
| Microfone não funciona | Clique no cadeado ao lado do endereço `localhost:8765` e permita o microfone. |
| Qualquer outro erro | Copie a mensagem da janela preta e mande para o Claude. |
