# Projeto Ametista 💜 v2.0

Assistente de IA que vive no seu Windows, **por cima de qualquer programa**, com um rosto animado. Ela:

- conversa por voz de verdade: começa a falar antes de terminar de pensar, pode ser **interrompida**, mantém a **conversa** sem você repetir o nome e entende pedidos incompletos ("abre de novo", "desfaz", "mais alto");
- reconhece **quem está falando** e só obedece as vozes que você cadastrou;
- **lembra** das conversas, tem um **caderno** com os seus projetos e acha os seus **arquivos** pelo nome;
- controla o PC: programas, janelas, mouse e teclado, a tela, Steam, Spotify, agenda e casa;
- faz **tarefas grandes sozinha** (modo agente), mostrando o plano e o andamento;
- tem **rotinas** ("bom dia", "vou dormir", "modo filme"), lembretes inteligentes e iniciativa com limite;
- mostra **tudo o que fez**, com **desfazer**, e pede confirmação antes do que é arriscado;
- tem um **app no celular** que recebe avisos mesmo fechado.

Ela liga junto com o PC e fica quietinha no ícone 💎 perto do relógio.

---

## O que mudou da 1.0 para a 2.0

| Área | Novidade |
|---|---|
| Conversa | Fala em trechos (começa a responder antes de terminar de pensar), interrupção por voz, conversa contínua, "obrigado" encerra |
| Cérebro | Escolhe sozinha entre o modelo rápido e o forte; reserva automática se o modelo forte estiver sobrecarregado |
| Voz | Voz expressiva (risadas, suspiros, pausas) com a ElevenLabs v3; velocidade ajustável |
| Personalidade | Documento editável `IDENTIDADE_DA_AMETISTA.md` |
| Memória | Histórico de conversas com busca ("o que eu te pedi ontem?"), caderno pessoal, busca por significado, "não guarde isso" |
| Segurança | Botão **parar tudo**, histórico de ações com **desfazer**, níveis de confirmação, **modo privado**, diagnóstico |
| PC | Clicar, teclar, rolar, controlar janelas, apontar na tela onde clicar, achar e abrir arquivos |
| Agente | Tarefas de vários passos com plano, barra de progresso e cancelamento |
| Rotinas e avisos | Rotinas, resumo do dia, lembretes recorrentes e por condição, aniversários, iniciativa com limite por hora |
| Interface | Rosto com novos estados e movimentos de cabeça, barra expansível (conversa, tarefas, avisos, histórico), **painel de configurações** |
| Celular | Avisos com o app fechado (push), atalhos no ícone, parar tudo, confirmar pelo celular |

---

## 1. Instalação (primeira vez)

1. Instale o **Python 3.12** (ou 3.11) em python.org. **Marque "Add Python to PATH".**
2. Descompacte num lugar fixo (ex.: `C:\Ametista`). Não deixe em Downloads.
3. Dois cliques em **`instalar.bat`**. Ele:
   - instala tudo e baixa os modelos offline (ouvir, reconhecer quem fala, transcrever e a busca por significado: cerca de 800 MB);
   - liga o "Iniciar com o Windows".
4. Dois cliques em **`iniciar.bat`**. Na primeira vez, o **painel de configurações** abre no navegador:
   cole a **chave da Anthropic** em **Cérebro** (a chave é criada em console.anthropic.com) e clique em **Salvar**.
5. **Cadastre a sua voz:** botão direito no 💎 → **Vozes → Cadastrar a minha voz**, depois leia as 7 frases que aparecem na tela.

> Enquanto ninguém estiver cadastrado, ela atende qualquer voz. Depois do primeiro cadastro, passa a atender **só** as vozes cadastradas.

Se algo não funcionar: dois cliques em **`diagnostico.bat`** (confere cada peça e diz o que está errado). O `depurar.bat` abre a Ametista com a janela de mensagens, para ver erros. O histórico fica em `dados/ametista.log`.

## 2. Atualizar da 1.0

Nada do que ela aprendeu se perde: o `.env`, as vozes cadastradas, a memória e os modelos ficam onde estão.

1. Feche a Ametista: botão direito no 💎 → **Sair**.
2. Abra o zip da 2.0, entre na pasta `ametista` de dentro dele e copie **tudo o que está lá** para a pasta onde a 1.0 está (ex.: `C:\Ametista`), escolhendo **substituir** os arquivos.
3. Dois cliques em **`instalar.bat`** (instala as bibliotecas novas e baixa o modelo da busca por significado).
4. Dois cliques em **`iniciar.bat`**.
5. Se você usa o app do celular: dois cliques em **`publicar_celular.bat`** para atualizar o app (mesma conta e mesmo endereço; os celulares pareados continuam pareados). Depois abra o app no celular e toque em **Ativar avisos**.

Na primeira vez, ela traz os fatos e lembretes da 1.0 para a memória nova (o arquivo antigo vira `dados/memoria_v1_migrada.json`).
As configurações novas começam no padrão; confira no painel (botão direito no 💎 → **Configurações…**).

---

## 3. Conversando com ela

| Jeito | O que acontece |
|---|---|
| **"Ametista, …"** | Palavra de ativação, 100% offline |
| **Ctrl + Shift + Espaço** | Abre ouvindo e com a caixa de texto pronta |
| Logo depois da resposta | Por 8 s você fala **sem repetir o nome** |
| Conversa contínua | Por mais 3 min ela continua atenta, mas só responde o que for claramente para ela (vozes desconhecidas são ignoradas) |
| **"Obrigado", "valeu", "tchau"** | Encerra a conversa |
| **"Ametista"** ou **"para"** enquanto ela fala | Interrompe na hora |
| **Ctrl + Shift + Backspace** ou o botão **■** | **Parar tudo** (veja abaixo) |
| **Esc** | Cala e esconde |
| **App do celular** | Texto ou áudio, de qualquer lugar |

**Parar tudo** é o botão de emergência: cala a Ametista, cancela o que ela estiver fazendo (inclusive tarefas do modo agente e confirmações pendentes), pausa a música e cancela um desligamento agendado. Funciona pelo atalho, pelo botão ■ na barra, pelo menu do 💎 e pelo celular.

**Pedidos incompletos:** ela sabe o que fez por último. *"Abre de novo"*, *"desfaz"*, *"não esse, o outro"*, *"mais alto"* funcionam.

**Pedidos difíceis:** ela começa a falar logo, com o modelo rápido. Se o pedido pedir mais (uma análise, uma explicação longa, olhar a tela, uma tarefa grande), ela passa para o modelo forte sozinha.

---

## 4. A barra na tela, o menu e o painel

A barra fica no canto da tela e some sozinha. Nela:

- **■ Parar tudo**, **🔒 Modo privado** e **⤢ Expandir**;
- **Sim / Não** quando ela pede confirmação;
- a barrinha de progresso quando o modo agente está trabalhando.

**Expandida**, ela mostra quatro abas:

- **Conversa**: a conversa de agora;
- **Tarefas**: o plano e o andamento de cada tarefa do modo agente;
- **Avisos**: lembretes e sugestões dela;
- **Histórico**: tudo o que ela fez, com o botão **Desfazer**.

**Menu do 💎** (botão direito): chamar, parar tudo, modo privado, não perturbe, microfone, **Configurações…**, diagnóstico, vozes, celular, contas e "Iniciar com o Windows".

**Painel de configurações** (💎 → Configurações…): tudo o que antes era no `.env`, com explicação em cada item:

- cidade (com busca), modelos, voz (com botão **Ouvir** para testar), microfone, sensibilidade, iniciativa, memória;
- pessoas cadastradas, contas, parear o celular;
- editor da **Personalidade** e das **Rotinas**;
- **Memória e lembretes**, **Histórico** de ações e conversas por dia;
- **Diagnóstico** e **Registro (log)**.

Algumas opções pedem para reiniciar; o painel avisa e tem o botão **Reiniciar agora**.

---

## 5. Personalidade

O jeito dela está no arquivo **`IDENTIDADE_DA_AMETISTA.md`**: quem ela é, como fala, o que evita, as regras de voz. Edite no painel (**Personalidade**) ou no Bloco de Notas; vale no próximo pedido, sem reiniciar.

- `{nome}` e `{dono}` são trocados pelos nomes do `.env`.
- Linhas que começam com `>` são notas para você e não vão para ela.

---

## 6. Cérebro e custos

| Modelo | Quando entra |
|---|---|
| **Claude Haiku 4.5** (dia a dia) | A maioria dos pedidos: rápido e barato, o melhor para voz |
| **Claude Opus 5** (forte) | Explicações, análises, cálculos, ver a tela, modo agente |
| **Ollama** (opcional, no PC) | Reserva quando a internet cai |

- A escolha é automática (`MODELO_AUTOMATICO`). Desligada, ela usa sempre o modelo do dia a dia.
- O modelo forte custa bem mais por pedido. Se preferir gastar menos, troque por Sonnet 5 no painel.
- Se o modelo forte estiver sobrecarregado, a Anthropic responde com outro automaticamente.
- Se faltar crédito, bater no limite ou a chave estiver errada, ela diz exatamente isso em voz alta.
- **Sem internet:** hora, timers, volume, teclas de mídia, abrir programas e janelas continuam funcionando no próprio PC. Com o Ollama instalado, ela também conversa.

---

## 7. Memória e privacidade

- **Fatos:** *"lembra que eu prefiro café sem açúcar"*.
- **Conversas:** ela guarda o histórico (365 dias, ajustável). Pergunte: *"o que eu te pedi ontem?"*, *"o que falamos sobre o orçamento semana passada?"*.
- **Caderno pessoal:** projetos, equipamentos, arquivos, pessoas e lugares.
  *"Anota no caderno que a obra de Jundiaí fica na rua X"*; depois: *"onde fica a obra de Jundiaí?"*.
- **Busca por significado:** acha lembranças mesmo com outras palavras ("máquina do escritório" acha "notebook do trabalho"). Roda no PC.
- **Arquivos:** ela conhece os nomes dos arquivos da Área de Trabalho, Documentos e Downloads (mais as pastas que você colocar em `PASTAS_INDICE`). *"Abre a planilha do orçamento de Jundiaí"*, *"mostra na pasta o PDF do contrato"*. Programas (.exe) ela só abre depois de confirmar.
- **"Não guarde isso":** logo depois de uma conversa, apaga a última troca. No meio da frase (*"não guarde isso: estou planejando uma surpresa"*), ela responde mas não guarda.
- **"Nova conversa"** ou *"muda de assunto"*: começa do zero, sem apagar o histórico.
- **Modo privado** (botão 🔒, menu do 💎 ou celular): microfone desligado, nada é guardado e nenhuma iniciativa. Para sair, clique no 🔒 de novo; o microfone está desligado, então não dá para sair pela voz.
- **Apagar conversas:** pelo painel (**Memória e lembretes**) ou pedindo; é uma ação crítica, ela confirma antes.

Tudo fica só no seu PC, em `dados/`.

---

## 8. O que ela faz no PC (e quando pergunta antes)

Cada ação passa pelo mesmo caminho: permissão de quem pediu → nível de risco → registro → desfazer.

| Nível | Exemplos | Como funciona |
|---|---|---|
| **Livre** | Abrir programa, volume, música, timer, janela, lembrete | Faz na hora |
| **Confirmação** | Fechar programa, cancelar compromisso, apagar rotina ou item do caderno, abrir um .exe, instalar jogo reiniciando a Steam, **digitar num terminal ou na caixa Executar** | Pergunta; você diz **"sim"** ou toca em **Sim** |
| **Crítica** | Desligar, reiniciar ou suspender o PC, trancar fechadura, apagar conversas | Pergunta, **só o dono** confirma e nunca roda sozinha numa rotina agendada |

- A confirmação é do sistema, não da IA: mesmo que a IA insista, nada acontece sem o "sim".
- Só quem pediu (ou o dono) pode confirmar. A pergunta expira em 90 s (45 s nas críticas).
- **Histórico:** barra expandida → Histórico, ou *"o que você fez hoje?"*. Cada item diz o quê, quando, quem pediu e por quê.
- **Desfazer:** *"desfaz"*, *"volta como estava"*, ou o botão no Histórico. Volume, música, lembretes, fatos, caderno, compromissos da agenda, casa, janelas, rotinas e não perturbe têm desfazer. Um desligamento pode ser cancelado enquanto não acontece.
- **Janelas:** *"fecha essa janela"*, *"minimiza a janela"*, *"traz o Excel para frente"*.
- **Tela:** *"que erro é esse?"*, *"resume essa página"*, *"olha as duas telas"*. Ela sabe qual janela está aberta; quando precisa, tira um print. A barra dela não aparece nos prints.
- **Onde clico?** Ela mostra um **círculo piscando** no ponto certo. Se você pedir, ela mesma clica, digita ou rola.

---

## 9. Modo agente (tarefas grandes)

*"Ametista, organiza a minha pasta Downloads por tipo de arquivo"*, *"pesquisa três orçamentos de betoneira e monta uma planilha"*.

1. Ela monta um **plano** (3 a 10 etapas) e mostra na aba **Tarefas**, com barra de progresso.
2. Trabalha sozinha, com mouse e teclado, vendo a tela.
3. Antes de algo sem volta (enviar, comprar, apagar, publicar), ela **pergunta**.
4. Termina com um resumo falado.

Segurança:

- **Se você mexer no mouse, ela para na hora.** O PC é seu.
- **Parar tudo** também cancela a tarefa.
- Ela **nunca digita senhas**, dados de cartão ou códigos de verificação: pede para você fazer essa parte.
- Uma tarefa por vez.

---

## 10. Rotinas

| Rotina | Frases | O que faz |
|---|---|---|
| **bom dia** | "bom dia", "começar o dia" | Resumo do dia (clima, agenda, lembretes) e 3 notícias |
| **vou dormir** | "vou dormir", "boa noite" | Pausa a música, volume em 20, apaga as luzes, não perturbe até 7h, conta o que tem amanhã, dá boa noite e **pergunta** se pode desligar o PC |
| **modo filme** | "modo filme", "vamos ver um filme" | Não perturbe por 3 h, apaga as luzes, volume em 70. **"Acabou o filme"** desfaz tudo |

- **Criar:** *"cria uma rotina 'chegando do trabalho' que acende a luz da sala e toca minha playlist"*. Pode ter horário e dias (*"todo dia útil às 7h"*).
- **Editar ou apagar:** no painel (**Rotinas**) ou pedindo.
- **Desfazer:** *"desfaz"* logo depois desfaz a rotina inteira.

---

## 11. Lembretes, aniversários e iniciativa

**Lembretes:**

- **Timer:** *"me avisa daqui a 20 minutos"*.
- **Data e hora:** *"me lembra amanhã às 9h de ligar para o engenheiro"*.
- **Recorrente:** *"todo dia útil às 8h"*, *"toda segunda"*, *"todo dia 5"*, *"todo ano em 10 de março"*.
- **Por condição:** *"quando eu ligar o PC"*, *"quando eu voltar para o computador"*, *"quando eu abrir o AutoCAD"*, *"na próxima vez que eu falar com você"*, *"quando eu chegar em casa"* (este precisa do Home Assistant com `HA_PESSOA`).
- **Aniversários:** *"o aniversário da Maria é 12 de agosto"*. Ela avisa no dia às 9h e, se quiser, na véspera.

**Iniciativa** (painel → **Proatividade**):

| Nível | Ela avisa sozinha |
|---|---|
| **0** | Nada: só fala quando chamada |
| **1** | Só o importante: bateria fraca, disco quase cheio, chuva chegando |
| **2** (padrão) | Também sugere pausa depois de 2 h direto no PC e faz o **resumo do dia** ao ligar o PC |

- Limites: no máximo 3 avisos por hora, com 20 min entre eles.
- Horário de silêncio: 22h às 7h.
- Ela não interrompe tela cheia (jogo, filme) nem fala quando você não está no PC.
- **Não perturbe:** *"não perturbe por 2 horas"*, *"desliga o não perturbe"*.
- Alarmes e lembretes que **você** pediu sempre tocam.

---

## 12. Vozes e permissões

Cada pessoa cadastrada tem um nível:

| Nível | Pode |
|---|---|
| **dono** | Tudo |
| **família** | Conversar, música, volume, clima, timers, lembretes, rotinas prontas, casa, pesquisas. **Não pode:** desligar ou bloquear o PC, fechar programas, mexer no mouse e teclado, ver a tela, instalar jogos, mexer na agenda, na memória, no caderno, nos arquivos, no modo agente, no histórico de ações nem cadastrar vozes |
| **visitante** | Conversar, música, volume, clima, timers e pesquisas |

- **Cadastrar alguém:** 💎 → Vozes → Cadastrar outra pessoa. Ou diga: *"Ametista, cadastra a voz da Maria como família"*.
- **Remover ou mudar o nível:** *"Ametista, apaga a voz da Maria"* ou *"a Maria agora é visitante"*. Também pelo painel (**Pessoas**).
- **Voz desconhecida:** ela ignora e mostra "Não reconheci essa voz". Com `MODO_VOZ=misto`, desconhecidos viram visitantes.
- **Privacidade:** a "impressão vocal" fica só no seu PC (`dados/pessoas.json`).
- **Não é uma trava de segurança:** uma gravação da sua voz pode enganá-la. Serve para ninguém mais mandar nela no dia a dia.
- **Se ela te recusar às vezes:** diminua o rigor no painel (**Pessoas**, ex.: 0.55) ou refaça o cadastro no lugar onde você costuma falar com ela.

O texto digitado no PC e o celular pareado contam como o dono.

---

## 13. Voz clonada e voz expressiva 🎙️

> **Só clone a voz de alguém com autorização dessa pessoa.**

1. Grave de **1 a 3 minutos** da pessoa falando naturalmente: frases variadas, sem música nem eco.
   Pode ser vários arquivos (mp3, wav, m4a, gravação do WhatsApp…).
2. Coloque os arquivos em **`voz\amostras`**.
3. Dois cliques em **`clonar_voz.bat`** e escolha:

| Opção | Qualidade | Custo | Observação |
|---|---|---|---|
| **1. ElevenLabs** (recomendado) | Excelente em português | Plano Starter, a partir de ~US$ 5/mês | Crie a conta em elevenlabs.io e cole a chave no painel (**Voz**) antes |
| **2. No próprio PC** (XTTS-v2) | Boa | Grátis | Baixa ~2 GB. Com placa NVIDIA fala em 1 a 2 s; sem ela, pode levar 10 s ou mais |

O script cria a voz, salva tudo no `.env` e gera um `voz\teste.mp3` para você ouvir.

- **Voz expressiva:** com o modelo **ElevenLabs v3** (painel → Voz), ela ri, suspira e faz pausas de verdade. Nas outras vozes essas marcas são removidas.
- **Velocidade:** painel → Voz (vale para as vozes prontas).
- Se a voz clonada falhar (sem internet, por exemplo), ela usa a voz padrão para não ficar muda.

---

## 14. App do celular 📱

O app mostra **se o PC está ligado, desde quando** ou **quando foi visto pela última vez**, com CPU, memória, música tocando e a janela aberta. Nele você pode:

- conversar com a Ametista por **texto ou áudio**;
- **ver a tela do PC**;
- acompanhar a **tarefa** do modo agente e responder **Sim/Não** às confirmações;
- **⏹ Parar tudo** e ligar o **modo privado**;
- receber **avisos com o app fechado**: lembretes, "o jogo terminou de instalar", compromissos da agenda;
- segurar o ícone do app para os **atalhos**: Falar, Ver tela, Parar tudo.

**Como funciona:** o app fica hospedado de graça na sua conta Cloudflare. O PC abre uma conexão de saída até lá, então não precisa mexer no roteador. Tudo passa por conexão criptografada:

- o PC usa uma chave secreta só dele;
- cada celular recebe um token no pareamento;
- os avisos com o app fechado vão criptografados: o serviço de notificações do Google ou da Apple não consegue ler.

**Publicar (uma vez, e de novo a cada versão nova):**

1. Instale o **Node.js LTS** (nodejs.org).
2. Dois cliques em **`publicar_celular.bat`**. Na primeira vez, o navegador abre para você entrar na Cloudflare (a conta gratuita serve).
   O script publica o app, cria a chave secreta e grava o endereço no `.env`.
3. Reinicie a Ametista.

**Parear o celular:**

1. 💎 → **Celular → Parear celular** (ou painel → Celular) → aponte a câmera para o QR code. O código vale 10 minutos e só uma vez.
2. Instale na tela inicial:
   - **Android (Chrome):** menu ⋮ → "Adicionar à tela inicial" (ou "Instalar app").
   - **iPhone (iOS 16.4 ou mais novo):** no **Safari**, Compartilhar → **"Adicionar à Tela de Início"**. No iPhone, os avisos com o app fechado **só funcionam** abrindo pelo ícone da tela inicial.
3. Abra o app pelo ícone e toque em **Ativar avisos** → Permitir.

Perdeu o celular? 💎 → Celular → **Desconectar todos os celulares**.

---

## 15. Steam 🎮

Exemplo de conversa:

> **Você:** Ametista, abre a Steam e baixa o Elden Ring.
>
> **Ametista:** Achei o ELDEN RING, 274 reais, precisa de uns 60 GB. Ele não está instalado. No C: tem 45 GB livres e não cabe. No D: tem 380 GB livres e tem biblioteca da Steam. Em qual unidade eu instalo?
>
> **Você:** No D.
>
> **Ametista:** Para instalar direto no D: preciso reiniciar a Steam. Posso?
>
> **Você:** Pode. E me avisa quando terminar.
>
> *(… mais tarde, no PC e no celular)* **Ametista:** ELDEN RING terminou de instalar e já pode ser jogado!

Também funciona: *"o Elden Ring já está instalado?"*, *"quanto falta pro download?"*, *"quais discos têm espaço?"*.

**Como ela escolhe o disco:** se o disco escolhido já tem uma **biblioteca da Steam**, ela prepara a instalação lá e reinicia a Steam, que começa a baixar sozinha.

- Se o disco não tem biblioteca, ela abre a janela oficial de instalação para você escolher ou criar a biblioteca. Isso só precisa ser feito uma vez por disco.
- Se o jogo não estiver na sua conta, ela desfaz e abre a página oficial.

---

## 16. Agenda (Google + Outlook) 📅

*"O que tenho amanhã?"*, *"marca dentista quinta às 3 da tarde"*, *"passa a reunião da obra para as 16h"*, *"cancela o almoço de sexta"*.
Ela junta as duas agendas, confirma antes de cancelar e **avisa 10 minutos antes** de cada compromisso (no PC e no celular).

**Google Agenda** (uns 10 minutos, uma vez):

1. Entre em console.cloud.google.com e crie um projeto chamado "Ametista".
2. Em **APIs e serviços → Biblioteca**, ative a **Google Calendar API**.
3. Em **Tela de consentimento OAuth**:
   - escolha Externo;
   - preencha nome e e-mail;
   - adicione o seu e-mail em "Usuários de teste";
   - depois clique em **Publicar app**. Assim o acesso não expira a cada 7 dias. O Google vai avisar que o app não foi verificado; pode seguir, porque só você usa.
4. Em **Credenciais → Criar credenciais → ID do cliente OAuth**, escolha o tipo **App para computador** e baixe o JSON.
5. Salve o arquivo como **`dados\google_credenciais.json`**.
6. 💎 → Conectar contas → **Google Agenda** → autorize no navegador.

**Outlook / Microsoft 365** (uns 5 minutos, uma vez):

1. Entre em entra.microsoft.com → **Registros de aplicativo → Novo registro**.
2. Nome: "Ametista". Tipos de conta: **"Contas em qualquer diretório organizacional e contas Microsoft pessoais"**.
3. URI de redirecionamento: plataforma **"Cliente público/nativo (móvel e desktop)"**, com o endereço `http://localhost` → Registrar.
4. Em **Autenticação**, ative **"Permitir fluxos de clientes públicos"**.
5. Copie o **ID do aplicativo (cliente)** para o painel (**Agenda → ID do app do Outlook**) e reinicie a Ametista.
6. 💎 → Conectar contas → **Outlook** → entre com a sua conta.

> A conta do trabalho (ex.: @fjengenharia.com) pode exigir que o TI da empresa aprove o app. Com a conta pessoal (Outlook.com/Hotmail), funciona direto.

Na hora de criar um compromisso, ela usa a agenda padrão do painel (Google ou Outlook), a não ser que você diga outra.

---

## 17. Spotify e casa

- **Spotify Premium:**
  1. Crie um app em developer.spotify.com.
  2. Em Redirect URI, coloque `http://127.0.0.1:8765/spotify/callback`.
  3. Copie o Client ID para o painel (**Contas**).
  4. 💎 → Conectar contas → Spotify.
- **Casa inteligente:** pelo Home Assistant.
  - Kit inicial sugerido: tomada Wi-Fi (R$ 40 a 80), lâmpada Wi-Fi (R$ 40 a 90) e controle infravermelho Wi-Fi (R$ 70 a 150) para ar-condicionado e TV, tudo compatível com Tuya/Smart Life.
  - No painel (**Casa**): endereço e token do Home Assistant.
  - Para lembretes "quando eu chegar em casa", preencha também **Você no Home Assistant** (ex.: `person.gabriel`).
  - Trancar fechaduras e mexer no alarme são ações críticas: ela sempre pergunta.

---

## 18. Diagnóstico e ajustes

**Diagnóstico:** *"Ametista, faz um diagnóstico"*, 💎 → Fazer um diagnóstico, painel → Diagnóstico, ou `diagnostico.bat`.
Ela confere internet, Claude, Ollama, microfone, reconhecimento de voz, tempo da voz, contas, casa, celular, memória, disco e erros recentes. Depois fala um resumo e guarda o relatório em `dados/diagnostico.txt`.

| Problema | Ajuste (painel) |
|---|---|
| Ela não me ouve de jeito nenhum (o diagnóstico diz "sem áudio chegando") | Configurações do Windows → Privacidade e segurança → Microfone → ligue **"Permitir que aplicativos da área de trabalho acessem o microfone"**. Depois confira o microfone escolhido em Ouvido → Microfone |
| Ela não percebe quando falo baixo | Ouvido → Sensibilidade: 200 |
| Acorda sozinha com barulho | Ouvido → Sensibilidade: 600 |
| Às vezes não me reconhece | Pessoas → Rigor: 0.55, ou refaça o cadastro |
| Reconhece gente demais | Pessoas → Rigor: 0.70 |
| Transcrição lenta | Ouvido → Precisão: Rápida. Com NVIDIA: Transcrever com: Placa NVIDIA |
| Responde conversa que não era para ela | Ouvido → Minutos de conversa contínua: 1 (0 desliga) |
| Ela me interrompe sozinha / se interrompe | Ouvido → Interromper pela voz: desligado |
| Fala demais sozinha | Proatividade → nível 1 ou 0 |
| Gasta demais | Cérebro → Modelo para pedidos difíceis: Sonnet 5, ou desligue a escolha automática |
| Não quero mostrar a janela aberta no celular | Celular → Mostrar a janela aberta: desligado |

Tudo isso também está no `.env` (o `.env.example` explica cada linha).

---

## 19. Limites de hoje (honestamente)

- **Balão flutuante no celular** por cima de outros apps: precisa de um app nativo (Android), fora do escopo de um app web. No celular ela funciona como app e com avisos.
- Ela **não liga** o PC que estiver desligado. Isso é possível no futuro com Wake-on-LAN e um aparelho que fique ligado em casa.
- O **modo agente** é bom, mas não perfeito: em sites muito dinâmicos ele pode errar ou desistir. Ele sempre para se você mexer no mouse, e pergunta antes de qualquer coisa sem volta.
- O **reconhecimento de voz** não é uma trava de segurança (veja a seção 12).
- **Interromper pela voz** usa o próprio microfone: com caixas de som muito altas, ela pode demorar a perceber o "para". Use fone, o atalho ou o botão ■.
- No **iPhone**, os avisos com o app fechado só funcionam no iOS 16.4 ou mais novo, com o app na Tela de Início.

---

## 20. Estrutura

```
IDENTIDADE_DA_AMETISTA.md  a personalidade dela (editável)
ametista/
  desktop.py        sobreposição, bandeja, atalhos, apontador na tela
  servidor.py       servidor local (sobreposição, painel, API)
  nucleo.py         atende um pedido: confirmação, "não guarde isso", despedida, parar tudo
  ouvido.py         microfone, palavra de ativação, interrupção, conversa contínua, cadastro de voz
  identidade.py     quem está falando + permissões
  cerebro.py        roteador local + Claude (rápido/forte) + Ollama
  fala.py           fala em trechos (começa antes de terminar de pensar)
  voz.py            ElevenLabs / XTTS / edge, voz expressiva, reserva automática
  personalidade.py  carrega a IDENTIDADE_DA_AMETISTA.md
  acoes.py          registro, desfazer, níveis de confirmação
  ferramentas.py    tudo o que ela sabe fazer
  memoria.py        fatos, conversas, caderno, lembretes (SQLite)
  semantica.py      busca por significado (opcional)
  arquivos.py       índice de arquivos por nome
  pc.py, controle.py  Windows: volume, programas, tela, mouse, teclado, janelas
  agente.py         modo agente (tarefas grandes)
  rotinas.py        rotinas e modos
  proatividade.py   iniciativa, resumo do dia, lembretes por condição
  avisos.py         alertas no PC e no celular
  diagnostico.py    confere cada peça
  steam.py, agenda.py, spotify.py, nuvem.py
celular/            app do celular (PWA) + ponte na Cloudflare + avisos push
web/                sobreposição, rosto e painel de configurações
tests/              testes automáticos (rodam no GitHub a cada mudança)
```
