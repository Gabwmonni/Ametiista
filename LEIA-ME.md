# Projeto Ametista 💜 v3.0

Assistente de IA que vive no seu Windows, **por cima de qualquer programa**, num cantinho da tela: ela inteira, a ilustração da ficha de personagem, **viva** (pisca, fala, sorri, respira e os cristais brilham). Ela:

- conversa por voz de verdade: começa a falar antes de terminar de pensar, pode ser **interrompida**, mantém a **conversa** sem você repetir o nome e entende pedidos incompletos ("abre de novo", "desfaz", "mais alto");
- reconhece **quem está falando** e só obedece as vozes que você cadastrou;
- **lembra** das conversas, tem um **caderno** com os seus projetos e acha os seus **arquivos** pelo nome;
- controla o PC: programas, janelas, mouse e teclado, a tela, Steam, Spotify, agenda e casa;
- **lê, cria e edita arquivos**, abre **blocos de notas**, mostra o que está pesando no PC, **limpa temporários** e **manda arquivos para o celular**, de perto ou de longe;
- percebe quando você **troca os estudos por distração** e chama você de volta, com calma;
- pensa **no próprio PC** (Ollama), com as mesmas ferramentas, e pode falar com uma **voz clonada no próprio PC**;
- faz **tarefas grandes sozinha** (modo agente), mostrando o plano e o andamento;
- tem **rotinas** ("bom dia", "vou dormir", "modo filme"), lembretes inteligentes e iniciativa com limite;
- mostra **tudo o que fez**, com **desfazer**, e pede confirmação antes do que é arriscado;
- tem um **app no celular** que recebe avisos mesmo fechado.

Ela liga junto com o PC e fica quietinha no ícone 💎 perto do relógio.

---

## O que mudou da 2.0 para a 3.0

| Área | Novidade |
|---|---|
| Arquivos | Ler (texto, Word, Excel, PowerPoint, PDF e imagens), criar, editar, listar, mover, copiar e apagar (vai para a Lixeira), de perto ou pelo celular, com confirmação e **desfazer** |
| Blocos de notas | *"anota isso num bloco de notas"*, *"acrescenta na lista de compras"*, *"me manda a conversa de hoje num bloco de notas"* |
| O PC por dentro | O que está aberto e quanto pesa (memória e CPU), espaço nos discos, fechar à força um programa travado, **limpar temporários** e cache |
| Celular | *"me manda o PDF da aula"*: o arquivo chega no app (com o app fechado, chega um aviso e ele é entregue quando você abrir) |
| Estudos | **Foco nos estudos**: sessões ("vou estudar cálculo por uma hora"), horários fixos, chamados quando a distração passa do limite, pausas e relatório da semana |
| Cérebro local | O **Ollama** agora usa as ferramentas (arquivos, notas, programas, foco, lembretes, música...) e pode ser o cérebro principal |
| Voz | **Voz clonada no próprio PC** num Python separado (placa NVIDIA, incluindo as RTX 50), fluida, sem pesar o resto; o `clonar_voz.bat` escolhe sozinho os melhores trechos das gravações |
| Aparência | **Ela em 3D**, na barra do PC e no celular: uma malha feita no Blender, **editável e animável**, desenhada em estilo anime; pisca, olha em volta, fala com a boca (a, e, i, o, u), sorri, vira e inclina a cabeça, o cabelo balança e os cristais brilham |
| Barra | No **canto esquerdo de baixo** (não tapa mais o meio da tela) e **arrastável** pelo rosto; lembra onde você a deixou |
| Ouvido | **Entende mais rápido**: transcreve já na pausa do fim da fala, identifica a voz ao mesmo tempo, Whisper aquecido e na placa NVIDIA quando funciona; nada se perde depois de um "Ametista" sozinho |

## O que mudou da 1.0 para a 2.0

| Área | Novidade |
|---|---|
| Conversa | Fala em trechos (começa a responder antes de terminar de pensar), interrupção por voz, conversa contínua, "obrigado" encerra |
| Cérebro | Escolhe sozinha entre o modelo rápido e o forte; reserva automática se o modelo forte estiver sobrecarregado |
| Voz | Mais leve, calma e acolhedora por padrão; tom e velocidade ajustáveis com prévia antes de salvar; fala em trechos com entonação contínua; voz expressiva (risadas, suspiros, pausas) com a ElevenLabs v3 |
| Personalidade | Documento editável `IDENTIDADE_DA_AMETISTA.md` |
| Memória | Histórico de conversas com busca ("o que eu te pedi ontem?"), caderno pessoal, busca por significado, "não guarde isso" |
| Segurança | Botão **parar tudo**, histórico de ações com **desfazer**, níveis de confirmação, **modo privado**, diagnóstico |
| PC | Clicar, teclar, rolar, controlar janelas, apontar na tela onde clicar, achar e abrir arquivos |
| Agente | Tarefas de vários passos com plano, barra de progresso e cancelamento |
| Rotinas e avisos | Rotinas, resumo do dia, lembretes recorrentes e por condição, aniversários, iniciativa com limite por hora |
| Aparência | **Nova identidade visual**: ela de corpo inteiro é a ilustração da ficha de personagem (no painel e no ícone do celular); o rosto animado mostra só o essencial (olhos de cristal, monóculo, boca e metal líquido iridescente), com piscadas, olhar, fala e emoções; cores lilás, azul-cristal e rosa em toda a interface |
| Interface | Rosto com novos estados e movimentos de cabeça, barra expansível (conversa, tarefas, avisos, histórico), **painel de configurações** |
| Celular | Avisos com o app fechado (push), atalhos no ícone, parar tudo, confirmar pelo celular, respostas só em texto (🔇), abre na hora e gasta pouca bateria e dados |

---

## 1. Instalação (primeira vez)

1. Instale o **Python 3.12** (ou 3.11) em python.org. **Marque "Add Python to PATH".**
2. Descompacte direto no `C:\` (fica `C:\ametista`). **Evite Documentos, Área de Trabalho e Downloads:** no Windows 11 eles costumam ficar dentro do **OneDrive**, e o caminho fica longo demais para o Windows aceitar todos os arquivos da instalação.
   Se esquecer, tudo bem: o `instalar.bat` percebe, explica e oferece copiar a Ametista para `C:\Ametista` e continuar de lá.
3. Dois cliques em **`instalar.bat`**. Ele:
   - instala tudo e baixa os modelos offline (ouvir, reconhecer quem fala, transcrever e a busca por significado: cerca de 800 MB);
   - liga o "Iniciar com o Windows".
4. Dois cliques em **`iniciar.bat`**. Na primeira vez, o **painel de configurações** abre no navegador:
   cole a **chave da Anthropic** em **Cérebro** (a chave é criada em console.anthropic.com) e clique em **Salvar**.
5. **Cadastre a sua voz:** botão direito no 💎 → **Vozes → Cadastrar a minha voz**, depois leia as 7 frases que aparecem na tela.

> Enquanto ninguém estiver cadastrado, ela atende qualquer voz. Depois do primeiro cadastro, passa a atender **só** as vozes cadastradas.

Se algo não funcionar: dois cliques em **`diagnostico.bat`** (confere cada peça e diz o que está errado). O `depurar.bat` abre a Ametista com a janela de mensagens, para ver erros. O histórico fica em `dados/ametista.log`.

## 2. Atualizar (da 1.0, da 2.0 ou de uma 3.0 anterior)

Nada do que ela aprendeu se perde: o `.env`, as vozes cadastradas, a memória e os modelos ficam onde estão.

1. Abra o zip novo, entre na pasta `ametista` de dentro dele e copie **tudo o que está lá** para a pasta onde a Ametista está (ex.: `C:\Ametista`), escolhendo **substituir** os arquivos. Descompactar em outra pasta (até no OneDrive) também serve: o instalador leva para o lugar certo.
2. Dois cliques em **`instalar.bat`**. Ele faz tudo sozinho:
   - **fecha a Ametista que estiver aberta** (senão a versão antiga continuaria rodando e você não veria nada de novo);
   - instala as bibliotecas novas e traz a memória, as vozes e as configurações de uma instalação em outra pasta;
   - se o app do celular já estava publicado, **publica a versão nova** (no celular, é só abrir o app: ele se atualiza sozinho);
   - se o **Ollama** estiver instalado, oferece baixar o modelo novo do cérebro local (o `qwen2.5:7b`) **em segundo plano**: a instalação termina na hora e o download acontece com a Ametista aberta, continuando de onde parou se a internet cair;
   - no fim, **abre a Ametista já na versão nova** e mostra "A Ametista 3.0 abriu".

Na primeira vez, ela traz os fatos e lembretes da 1.0 para a memória nova (o arquivo antigo vira `dados/memoria_v1_migrada.json`).
As configurações novas começam no padrão, e ajustes que mudaram de padrão entre as versões (como a velocidade da voz, agora mais calma, e o modelo do Ollama, agora o `qwen2.5:7b`) passam para o novo se você nunca tinha mexido neles. Confira no painel (botão direito no 💎 → **Configurações…**).

Para conferir se o celular está na versão nova: **Diagnóstico** no painel avisa quando o app publicado é de uma versão antiga.

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

**Ela entende rápido:** a transcrição começa já na pausa do fim da sua fala (se você continuar falando, ela descarta e espera), confere quem está falando ao mesmo tempo, e o Whisper roda na **placa NVIDIA** quando ela funciona (sozinho: na primeira vez a placa é testada à parte, com o processador já ouvindo). Se você disser só "Ametista" e fizer uma pausa, o que disser em seguida não se perde.

**Pedidos difíceis:** ela começa a falar logo, com o modelo rápido. Se o pedido pedir mais (uma análise, uma explicação longa, olhar a tela, uma tarefa grande), ela passa para o modelo forte sozinha.

---

## 4. A barra na tela, o menu e o painel

A barra fica no **canto esquerdo de baixo** da tela (no meio ela tapava o que você estava usando) e some sozinha. Para mudar de lugar, **arraste pelo rosto dela** ou pela linha de cima da barra: ela fica onde você deixar, até depois de reiniciar, e cresce (conversa aberta) sem sair do lugar. Para voltar ao canto: menu do 💎 → **Voltar a janela para o canto**. Nela:

- **■ Parar tudo**, **🔒 Modo privado** e **⤢ Expandir**;
- **Sim / Não** quando ela pede confirmação;
- a barrinha de progresso quando o modo agente está trabalhando.

**Expandida**, ela mostra quatro abas:

- **Conversa**: a conversa de agora;
- **Tarefas**: o plano e o andamento de cada tarefa do modo agente;
- **Avisos**: lembretes e sugestões dela;
- **Histórico**: tudo o que ela fez, com o botão **Desfazer**.

**Menu do 💎** (botão direito): chamar, parar tudo, modo privado, não perturbe, microfone, **Configurações…**, voltar a janela para o canto, diagnóstico, vozes, celular, contas e "Iniciar com o Windows".

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

**A aparência dela** vem da ficha de personagem. De corpo inteiro, ela é a própria ilustração (aparece no painel, em **Personalidade**, e no ícone e na tela de pareamento do celular): cabelo branco-prateado com reflexos iridescentes preso num coque meio bagunçado, olhos azul-cristal, **monóculo de cristal** sobre o olho direito, filigranas com gotas de cristal sob os olhos e brincos longos.

Na **barra do PC e no celular** ela é uma **malha 3D** (feita no Blender, em `modelo/ametista.blend`), desenhada em estilo anime: luz e sombra chapadas, contorno, olhos de cristal com a estrela na íris, monóculo de vidro iridescente, filigranas e brincos de cristal, cabelo branco-prateado com brilho e o coque com estrelas. Ela pisca (às vezes duas vezes), olha em volta, fala mexendo a boca nas vogais, sorri com os olhos (^^) quando está feliz, cora, arregala os olhos na surpresa, franze a testa brava, vira, acena e inclina a cabeça, respira, e o cabelo balança. As emoções (feliz, pensativa, surpresa, triste, brava) mudam a expressão, a luz e a cor. **Para editar a aparência ou as expressões**, veja `modelo/LEIA-ME-MODELO.md` (abrir no Blender, exportar, `modelo\aplicar_modelo.bat`). Num computador sem WebGL, entra o rosto de reserva (a ilustração animada). Cada estado tem um sinal: brilho azul quando ouve, laranja no alerta, olhos fechados no modo privado e dormindo, sem cor quando está sem internet, e um ícone no canto (✦ pensando, cristal girando trabalhando, ? esperando resposta, cadeado, nuvem riscada, zz).

---

## 6. Cérebro e custos

| Modelo | Quando entra |
|---|---|
| **Claude Haiku 4.5** (dia a dia) | A maioria dos pedidos: rápido e barato, o melhor para voz |
| **Claude Opus 5** (forte) | Explicações, análises, cálculos, ver a tela, modo agente |
| **Ollama** (opcional, no PC) | Reserva quando a internet cai, ou o cérebro principal, se você escolher |

- A escolha é automática (`MODELO_AUTOMATICO`). Desligada, ela usa sempre o modelo do dia a dia.
- O modelo forte custa bem mais por pedido. Se preferir gastar menos, troque por Sonnet 5 no painel.
- Se o modelo forte estiver sobrecarregado, a Anthropic responde com outro automaticamente.
- Se faltar crédito, bater no limite ou a chave estiver errada, ela diz exatamente isso em voz alta.
- **Sem internet:** hora, timers, volume, teclas de mídia, abrir programas e janelas continuam funcionando no próprio PC. Com o Ollama instalado, ela também conversa **e usa as ferramentas**.

### Cérebro no próprio PC (Ollama)

Com o Ollama, ela pensa no seu PC: as conversas não saem do computador e não gastam crédito. Ela usa as **mesmas ferramentas** do Claude (arquivos, notas, programas, limpeza, foco, lembretes, música, janelas); só ver a tela e o modo agente continuam precisando do Claude.

1. Instale o Ollama em **ollama.com** (ele fica perto do relógio).
2. Painel → **Cérebro** → **Ollama no PC** → **Baixar agora** (ou diga "sim" no `instalar.bat`). O modelo (`qwen2.5:7b`, 4,7 GB) baixa em segundo plano, com o andamento no painel; se a internet cair, continua de onde parou. Enquanto isso ela usa o Claude (ou um modelo menor que já esteja baixado).
3. Painel → **Cérebro**:
   - **Cérebro principal: Ollama no PC** para usar sempre o Ollama (o Claude só entra se o Ollama falhar);
   - ou deixe o Claude como principal e o Ollama fica de reserva sem internet.
   - O endereço padrão (`http://localhost:11434`) já serve.

| Modelo | Para quem |
|---|---|
| `qwen2.5:7b` (padrão) | Placa de vídeo com 8 GB ou mais (uma RTX 5060 Ti responde na hora) |
| `qwen2.5:14b` | Placa com 12 GB ou mais: mais esperto, um pouco mais lento |
| `qwen2.5:3b` | PC sem placa de vídeo |

- Ela manda para o modelo só as ferramentas do assunto do pedido: modelos locais erram menos assim.
- O modelo fica carregado na placa por 30 minutos depois do último pedido, então as respostas seguintes saem rápido.
- Se o modelo escolhido não estiver baixado, ela usa o melhor que tiver, e o **diagnóstico** avisa.
- Modelos que não sabem usar ferramentas (como o gemma) só conversam; o diagnóstico também avisa.

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

## 9. Arquivos, blocos de notas e o PC por dentro 🗂️

Tudo pela voz, pelo texto ou **pelo celular, de longe**:

- **Ler:** *"lê o resumo.pdf da área de trabalho"*, *"o que tem na planilha do orçamento?"*, *"resume o Word do TCC"*. Ela lê texto, código, CSV, JSON, **Word, Excel, PowerPoint, PDF** e vê imagens. Textos longos ela lê em partes.
- **Ver pastas:** *"o que tem na minha pasta Downloads?"*, *"quais os arquivos mais recentes dos Documentos?"*.
- **Criar e editar** arquivos de texto (.txt, .md, .csv, .json, código...): *"cria um arquivo lista.txt com..."*, *"troca 'leite' por 'café' na lista de compras"*.
- **Mover, renomear, copiar, apagar:** *"move o PDF da aula para Documentos/Faculdade"*, *"renomeia para Aula 3.pdf"*, *"apaga o arquivo velho.txt"*.
- **Blocos de notas:** *"anota num bloco de notas: comprar filamento e ligar pro João"*, *"acrescenta 'pão' na lista de compras"*, *"lê a nota das ideias"*. As notas ficam em `Documentos\Ametista\Notas` e abrem no Bloco de Notas quando o pedido é no PC.
- **A conversa num bloco de notas:** *"me manda a nossa conversa de hoje num bloco de notas"* (hoje, ontem, semana ou uma data).
- **O que está pesando:** *"o que está usando mais memória?"*, *"o PC está lento, o que está aberto?"*, *"quanto espaço tem nos discos?"*. Os programas vêm agrupados (as dezenas de processos do Chrome viram uma linha só).
- **Fechar à força** um programa travado: *"fecha o Chrome à força"*. Processos do Windows e a própria Ametista ficam protegidos.
- **Limpeza:** *"quanto dá para limpar de temporários?"* e depois *"pode limpar"*: temporários do usuário e do Windows, cache dos navegadores, miniaturas e relatórios de erro (a Lixeira só se você pedir). Arquivos pessoais nunca entram.
- **Mandar para o celular:** *"me manda o PDF da aula"*, *"manda a pasta das fotos da obra"* (pastas viram .zip; até 25 MB). Veja a seção 16.

**Segurança:**

| O quê | Como funciona |
|---|---|
| Ler, listar, criar arquivo novo, mexer nas notas dela | Faz na hora |
| Mudar um arquivo que já existe, mover por cima de outro, apagar, fechar à força, limpar | Pergunta antes |
| Pastas do Windows, dos programas instalados, a raiz do disco e a pasta da Ametista | Nunca altera (só lê) |

- Antes de mudar um arquivo, ela guarda uma cópia (em `dados\copias`): **"desfaz"** devolve como estava. Mover, copiar e criar também têm desfazer.
- **Apagar** manda para a **Lixeira** do Windows: dá para restaurar por lá.
- Ao editar, o arquivo continua com a mesma codificação e as mesmas quebras de linha.
- Tudo isso é só do dono: vozes da família e visitantes não mexem em arquivos, notas nem programas.

---

## 10. Foco nos estudos 📚

Ela percebe quando você troca os estudos por distração e chama você de volta, com calma.

- **Começar:** *"vou estudar cálculo por uma hora"*, *"me ajuda a focar"*, *"vou estudar para a prova de química"*. Sem tempo, a sessão vai até você dizer *"terminei de estudar"* (no máximo 4 horas).
- **Durante a sessão:** a cada 15 segundos ela vê qual janela está na frente e separa em **estudo** (PDF, Word, AutoCAD, VS Code, aulas no YouTube, Moodle, Notion...), **distração** (YouTube que não é aula, Instagram, TikTok, Netflix, Discord, jogos...) ou **neutro**. Passou **3 minutos seguidos** numa distração, ela chama: *"Ei, Gabriel. Faz 4 minutos que você está no YouTube. Bora voltar para cálculo?"*. Não repete antes de 8 minutos, e o tom muda aos poucos.
- **Pausa:** *"pausa de 10 minutos"*: nada de chamados, e ela avisa quando a pausa acabar.
- **Fim:** um resumo falado: quanto estudou, quanto se distraiu e com o quê.
- **Relatório:** *"como foram meus estudos essa semana?"*, *"quanto eu estudei hoje?"*: sessões, horas de estudo, principais distrações, matérias e o melhor dia.
- **Horários fixos** (painel → **Foco**): por exemplo `seg-sex 19:00-22:00; sab 09:00-12:00`. Nesses horários a sessão começa sozinha.
- **Fora das sessões** (painel → Foco, ligado por padrão): se você estava estudando e caiu numa distração por 15 minutos, ela comenta uma vez (e segue os limites da Proatividade).
- **Do seu jeito:** painel → Foco → *Também conta como estudo* / *Também conta como distração* (palavras do título da janela ou programas) e os minutos de tolerância. A matéria que você disser também conta como estudo ("cálculo" no título do vídeo = aula).
- Se você sair do PC, isso não conta como distração. Lendo um PDF parado, ainda conta como estudo (até 20 minutos).

**Privacidade:** o histórico guarda só o nome da distração ("YouTube", o nome do jogo), nunca o título da janela. No **modo privado** ela não olha nada. O não perturbe segura os chamados.

---

## 11. Modo agente (tarefas grandes)

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

## 12. Rotinas

| Rotina | Frases | O que faz |
|---|---|---|
| **bom dia** | "bom dia", "começar o dia" | Resumo do dia (clima, agenda, lembretes) e 3 notícias |
| **vou dormir** | "vou dormir", "boa noite" | Pausa a música, volume em 20, apaga as luzes, não perturbe até 7h, conta o que tem amanhã, dá boa noite e **pergunta** se pode desligar o PC |
| **modo filme** | "modo filme", "vamos ver um filme" | Não perturbe por 3 h, apaga as luzes, volume em 70. **"Acabou o filme"** desfaz tudo |

- **Criar:** *"cria uma rotina 'chegando do trabalho' que acende a luz da sala e toca minha playlist"*. Pode ter horário e dias (*"todo dia útil às 7h"*).
- **Editar ou apagar:** no painel (**Rotinas**) ou pedindo.
- **Desfazer:** *"desfaz"* logo depois desfaz a rotina inteira.

---

## 13. Lembretes, aniversários e iniciativa

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

## 14. Vozes e permissões

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

## 15. A voz dela 🎙️

**Voz pronta (grátis, padrão):** Francisca, calma e com o tom um pouco mais leve, acolhedora sem ficar infantil.
No painel (**Voz**) dá para ajustar:

- **Voz pronta:** Francisca (leve e clara) ou Thalita (mais grave e muito natural; combine com um tom mais leve);
- **Velocidade:** de "bem devagar" a "rápida" (padrão: calma e atenciosa);
- **Tom:** de "mais grave" a "bem leve" (padrão: leve e acolhedora).

Toque em **Ouvir** para escutar a combinação escolhida **antes de salvar**, e compare à vontade.

Ela fala a primeira frase sozinha, para começar rápido, e junta as seguintes em trechos de duas ou três frases, para a entonação não recomeçar a cada frase.

### Voz clonada (no próprio PC ou na ElevenLabs) e voz expressiva

> **Só clone a voz de alguém com autorização dessa pessoa.** O `clonar_voz.bat` pergunta antes de começar.

1. Junte gravações da pessoa falando (1 a 3 minutos no total). Podem ser **áudios comuns**, como mensagens do WhatsApp, com pausas, barulho ou música em alguns trechos: ela escolhe sozinha os melhores pedaços.
2. Coloque os arquivos (mp3, wav, m4a, ogg...) em **`voz\amostras`**.
3. Dois cliques em **`clonar_voz.bat`** e escolha:

| Opção | Qualidade | Custo | Observação |
|---|---|---|---|
| **1. No próprio PC** (XTTS-v2, recomendado) | Muito boa, bem parecida | Grátis | Na primeira vez instala o necessário (~4 GB). Com placa NVIDIA cada frase sai em menos de 1 s; sem placa, alguns segundos |
| **2. ElevenLabs** | Excelente em português | Plano Starter, a partir de ~US$ 5/mês | Crie a conta em elevenlabs.io e cole a chave no painel (**Voz**) antes |

**Como ela escolhe os trechos** (opção 1): acha onde tem voz humana, descarta pedaços com música ou barulho de fundo, com outra pessoa falando, com som estourado ou com palavra cortada, confere pelo Whisper que é fala clara e junta uns 25 segundos dos melhores trechos em `voz\referencia`. As referências anteriores ficam guardadas em `voz\referencia_anterior`. No fim ela grava um `voz\teste.wav` para você ouvir.

**A voz no próprio PC, por dentro:**

- roda num **Python separado** (`voz_local`), instalado pelo `instalar_voz_local.bat` (o `clonar_voz.bat` chama sozinho na primeira vez): o PyTorch com CUDA ocupa uns 3 GB e fica longe do resto da Ametista, que continua leve;
- placas **RTX 50** (como a 5060 Ti) usam o PyTorch com CUDA 12.8, que já vem certo; sem placa NVIDIA, instala a versão para processador;
- abre junto com a Ametista e leva uns 20 segundos para carregar: nesse meio-tempo, ela fala com a voz pronta;
- divide frases longas nos pontos certos e tira silêncios e estalos das pontas, para a fala sair contínua;
- manda a fala em MP3 para o celular (6 vezes menor que o áudio cru);
- o modelo XTTS-v2 é da Coqui e usa a licença **CPML**: grátis para uso pessoal e **não comercial**. O instalador pergunta antes.

- **Voz expressiva:** com o modelo **ElevenLabs v3** (painel → Voz), ela ri, suspira e faz pausas de verdade. Nas outras vozes essas marcas são removidas.
- Se a voz clonada falhar, ela usa a voz pronta para não ficar muda. O **diagnóstico** diz se a voz local está instalada, se está na placa de vídeo e quanto demora.

---|---|---|---|
| **1. ElevenLabs** (recomendado) | Excelente em português | Plano Starter, a partir de ~US$ 5/mês | Crie a conta em elevenlabs.io e cole a chave no painel (**Voz**) antes |
| **2. No próprio PC** (XTTS-v2) | Boa | Grátis | Baixa ~2 GB. Com placa NVIDIA fala em 1 a 2 s; sem ela, pode levar 10 s ou mais |

O script cria a voz, salva tudo no `.env` e gera um `voz\teste.mp3` para você ouvir.

- **Voz expressiva:** com o modelo **ElevenLabs v3** (painel → Voz), ela ri, suspira e faz pausas de verdade. Nas outras vozes essas marcas são removidas.
- Se a voz clonada falhar (sem internet, por exemplo), ela usa a voz padrão para não ficar muda.

---

## 16. App do celular 📱

O app mostra **se o PC está ligado, desde quando** ou **quando foi visto pela última vez**, com CPU, memória, música tocando e a janela aberta. Nele você pode:

- conversar com a Ametista por **texto ou áudio**;
- **ver a tela do PC**;
- acompanhar a **tarefa** do modo agente e responder **Sim/Não** às confirmações;
- **⏹ Parar tudo** e ligar o **modo privado**;
- receber **avisos com o app fechado**: lembretes, "o jogo terminou de instalar", compromissos da agenda;
- segurar o ícone do app para os **atalhos**: Falar, Ver tela, Parar tudo;
- tocar em **🔊** para receber as respostas **só em texto (🔇)**. Aí o PC nem gera o áudio, o que economiza dados e bateria;
- **receber arquivos do PC:** *"me manda o PDF da aula"*, *"puxa a planilha do orçamento"*, *"manda a nota das ideias"*. O arquivo aparece na conversa com **Abrir** e **Baixar** (fotos aparecem na hora). Com o app fechado, chega um aviso e o arquivo é entregue quando você abrir o app (ele espera até 7 dias). Limite de 25 MB; pastas viram .zip.

**Como funciona:** o app fica hospedado de graça na sua conta Cloudflare. O PC abre uma conexão de saída até lá, então não precisa mexer no roteador. Tudo passa por conexão criptografada:

- o PC usa uma chave secreta só dele;
- cada celular recebe um token no pareamento;
- os avisos com o app fechado vão criptografados: o serviço de notificações do Google ou da Apple não consegue ler.

**Leve de propósito:**

- o app abre na hora, com a cópia guardada no celular, mesmo sem internet;
- com ele aberto, o PC manda o status a cada 30 s;
- com ele fechado ou em segundo plano (depois de 20 s), o app desconecta e o PC só manda um "estou vivo" a cada 4 minutos;
- os avisos continuam chegando por notificação;
- o rosto só se mexe quando precisa e para quando o app some da tela;
- a conversa na tela guarda só as últimas 120 mensagens.

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

## 17. Steam 🎮

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

## 18. Agenda (Google + Outlook) 📅

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

## 19. Spotify e casa

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

## 20. Diagnóstico e ajustes

**Diagnóstico:** *"Ametista, faz um diagnóstico"*, 💎 → Fazer um diagnóstico, painel → Diagnóstico, ou `diagnostico.bat`.
Ela confere internet, Claude, Ollama (e se o modelo sabe usar as ferramentas), microfone, reconhecimento de voz, a voz (inclusive a clonada no PC: instalada, na placa de vídeo, tempo de resposta), contas, casa, celular, memória, disco e erros recentes. Depois fala um resumo e guarda o relatório em `dados/diagnostico.txt`.

| Problema | Ajuste (painel) |
|---|---|
| Ela não me ouve de jeito nenhum (o diagnóstico diz "sem áudio chegando") | Configurações do Windows → Privacidade e segurança → Microfone → ligue **"Permitir que aplicativos da área de trabalho acessem o microfone"**. Depois confira o microfone escolhido em Ouvido → Microfone |
| Ela não percebe quando falo baixo | Ouvido → Sensibilidade: 200 |
| Acorda sozinha com barulho | Ouvido → Sensibilidade: 600 |
| Às vezes não me reconhece | Pessoas → Rigor: 0.55, ou refaça o cadastro |
| Reconhece gente demais | Pessoas → Rigor: 0.70 |
| Transcrição lenta | Veja no diagnóstico se ela está transcrevendo na placa NVIDIA. Sem placa: Ouvido → Precisão: Rápida |
| Ela me corta antes de eu terminar | Fale sem pausas longas no meio; se continuar, Ouvido → Sensibilidade: 200 (ela passa a perceber a fala mais baixa como fala) |
| Responde conversa que não era para ela | Ouvido → Minutos de conversa contínua: 1 (0 desliga) |
| Ela me interrompe sozinha / se interrompe | Ouvido → Interromper pela voz: desligado |
| Voz fina ou grossa demais, rápida ou lenta demais | Voz → Tom e Velocidade (toque em Ouvir para comparar antes de salvar) |
| Fala demais sozinha | Proatividade → nível 1 ou 0 |
| Gasta demais | Cérebro → Modelo para pedidos difíceis: Sonnet 5, ou desligue a escolha automática |
| Não quero mostrar a janela aberta no celular | Celular → Mostrar a janela aberta: desligado |
| Ela me chama rápido demais quando me distraio | Foco → Minutos seguidos de distração: 5 ou mais |
| Um site que uso para estudar conta como distração | Foco → Também conta como estudo: o nome do site |
| O Ollama responde devagar | Cérebro → Modelo do Ollama: um menor (com placa de vídeo, o 7B já é rápido) |

Tudo isso também está no `.env` (o `.env.example` explica cada linha).

---

## 21. Leve para o PC

- **Rosto 3D:** ~20 mil triângulos, sem texturas, desenhado por um motor WebGL próprio e pequeno (não usa bibliotecas 3D grandes); o modelo tem ~360 KB. A cada quadro só as partes que mexem (olhos, boca, sobrancelhas) são recalculadas, e só quando mudam. 24 quadros por segundo falando, 8 parada ou dormindo, e **zero** quando a barra está escondida.
- **Ouvido:** o Whisper é carregado e aquecido uma vez (a primeira frase já sai rápida), usa metade dos núcleos do processador (de 4 a 8) ou a placa NVIDIA, sem marcas de tempo e sem repetir a transcrição.
- **Palavra de ativação:** o reconhecedor descansa depois de 1,5 s de silêncio. No primeiro som ele volta, com o meio segundo anterior, para não perder o começo do "Ametista".
- **Busca por significado:** o modelo carrega em segundo plano e nunca atrasa uma resposta.
- **Celular:** sem ninguém olhando, nada de status, Spotify ou medição do PC.

## 22. Limites de hoje (honestamente)

- **Balão flutuante no celular** por cima de outros apps: precisa de um app nativo (Android), fora do escopo de um app web. No celular ela funciona como app e com avisos.
- Ela **não liga** o PC que estiver desligado. Isso é possível no futuro com Wake-on-LAN e um aparelho que fique ligado em casa.
- O **modo agente** é bom, mas não perfeito: em sites muito dinâmicos ele pode errar ou desistir. Ele sempre para se você mexer no mouse, e pergunta antes de qualquer coisa sem volta.
- O **reconhecimento de voz** não é uma trava de segurança (veja a seção 14).
- **Interromper pela voz** usa o próprio microfone: com caixas de som muito altas, ela pode demorar a perceber o "para". Use fone, o atalho ou o botão ■.
- No **iPhone**, os avisos com o app fechado só funcionam no iOS 16.4 ou mais novo, com o app na Tela de Início.
- **Arquivos:** ela edita só arquivos de texto. Word, Excel, PowerPoint e PDF ela lê, abre, move e manda para o celular, mas não altera por dentro.
- **Foco nos estudos:** ela vê o que está na tela do **PC**. O que você faz no celular fica de fora.
- **Ollama:** modelos locais são bons, mas menos espertos que o Claude em pedidos longos ou complicados. Ver a tela e o modo agente continuam precisando do Claude.

---

## 23. Estrutura

```
IDENTIDADE_DA_AMETISTA.md  a personalidade dela (editável)
ametista/
  desktop.py        sobreposição, bandeja, atalhos, apontador na tela
  servidor.py       servidor local (sobreposição, painel, API)
  nucleo.py         atende um pedido: confirmação, "não guarde isso", despedida, parar tudo
  ouvido.py         microfone, palavra de ativação, interrupção, conversa contínua, cadastro de voz
  identidade.py     quem está falando + permissões
  cerebro.py        roteador local + Claude (rápido/forte) + Ollama
  cerebro_local.py  Ollama com ferramentas
  fala.py           fala em trechos (começa antes de terminar de pensar)
  voz.py            ElevenLabs / XTTS / edge, voz expressiva, reserva automática
  voz_local.py      abre e usa o servidor da voz clonada no PC (voz_local_servidor.py, Python separado)
  clonar_voz.py     escolhe os trechos das gravações e clona a voz
  personalidade.py  carrega a IDENTIDADE_DA_AMETISTA.md
  acoes.py          registro, desfazer, níveis de confirmação
  ferramentas.py    tudo o que ela sabe fazer
  memoria.py        fatos, conversas, caderno, lembretes (SQLite)
  semantica.py      busca por significado (opcional)
  arquivos.py       índice de arquivos por nome
  arquivos_io.py    ler, criar, editar, mover, copiar e apagar arquivos (com desfazer)
  notas.py          blocos de notas e a conversa num bloco de notas
  sistema.py        programas abertos, discos, fechar à força, limpeza de temporários
  envio.py          arquivos do PC para o celular
  foco.py           foco nos estudos
  pc.py, controle.py  Windows: volume, programas, tela, mouse, teclado, janelas
  agente.py         modo agente (tarefas grandes)
  rotinas.py        rotinas e modos
  proatividade.py   iniciativa, resumo do dia, lembretes por condição
  avisos.py         alertas no PC e no celular
  diagnostico.py    confere cada peça
  steam.py, agenda.py, spotify.py, nuvem.py
celular/            app do celular (PWA) + ponte na Cloudflare + avisos push
web/                sobreposição, rosto 3D (rosto.js + ametista.glb) e painel de configurações
modelo/             ela em 3D para editar no Blender (ametista.blend), o script que a constrói e o aplicar_modelo.bat
tests/              testes automáticos (rodam no GitHub a cada mudança)
```
