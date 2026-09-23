# Projeto Ametista 💜 v1.0

Assistente de IA que vive no seu Windows, **por cima de qualquer programa**. Ela:

- reconhece **quem está falando** e só obedece as vozes que você cadastrou;
- **fala com uma voz clonada**;
- vê a sua tela;
- controla o PC, a Steam, o Spotify e as suas agendas do Google e do Outlook;
- tem um **app no celular**, que mostra se o PC está ligado e deixa você falar com ela de qualquer lugar.

Ela liga junto com o PC e fica quietinha no ícone 💎 perto do relógio.

---

## 1. Instalação (uma vez)

1. Instale o **Python 3.11 ou 3.12** em python.org. **Marque "Add Python to PATH".**
2. Descompacte a pasta num lugar fixo (ex.: `C:\Ametista`). Não deixe em Downloads.
3. Dois cliques em **`instalar.bat`**. Ele:
   - instala tudo e baixa os modelos de voz offline (cerca de 550 MB);
   - liga o "Iniciar com o Windows";
   - abre o `.env` para você colar a **ANTHROPIC_API_KEY** (a chave é criada em console.anthropic.com).
4. Dois cliques em **`iniciar.bat`**.
5. **Cadastre a sua voz:** botão direito no 💎 → **Vozes → Cadastrar a minha voz**, depois leia as 7 frases que aparecem na tela.

> Enquanto ninguém estiver cadastrado, ela atende qualquer voz. Depois do primeiro cadastro, passa a atender **só** as vozes cadastradas.

Se algo não funcionar, use o **`depurar.bat`**, que mostra os erros. O histórico fica em `dados/ametista.log`.

---

## 2. Como chamar

| Jeito | O que acontece |
|---|---|
| **"Ametista, …"** | Palavra de ativação, 100% offline |
| **Ctrl + Shift + Espaço** | Abre ouvindo e com a caixa de texto pronta |
| Depois da resposta | Continua ouvindo por 6 s, sem precisar repetir o nome |
| **Esc** | Cala e esconde |
| **App do celular** | Texto ou áudio, de qualquer lugar |

---

## 3. Vozes e permissões

Cada pessoa cadastrada tem um nível:

| Nível | Pode |
|---|---|
| **dono** | Tudo |
| **família** | Quase tudo. **Não pode:** desligar o PC, fechar programas, instalar jogos, ver a tela, mexer na agenda nem cadastrar vozes |
| **visitante** | Conversar, música, volume, clima, timers e pesquisas |

- **Cadastrar alguém:** 💎 → Vozes → Cadastrar outra pessoa. Ou diga: *"Ametista, cadastra a voz da Maria como família"*.
- **Remover ou mudar o nível:** *"Ametista, apaga a voz da Maria"* ou *"a Maria agora é visitante"*.
- **Voz desconhecida:** ela ignora e mostra "Não reconheci essa voz". Com `MODO_VOZ=misto`, desconhecidos viram visitantes.
- **Privacidade:** a "impressão vocal" fica só no seu PC (`dados/pessoas.json`).
- **Não é uma trava de segurança:** uma gravação da sua voz pode enganá-la. Serve para ninguém mais mandar nela no dia a dia.
- **Se ela te recusar às vezes:** diminua o `LIMIAR_VOZ` no `.env` (ex.: 0.55) ou refaça o cadastro no lugar onde você costuma falar com ela.

O texto digitado no PC e o celular pareado contam como o dono.

---

## 4. Voz clonada 🎙️

> **Só clone a voz de alguém com autorização dessa pessoa.**

1. Grave de **1 a 3 minutos** da pessoa falando naturalmente: frases variadas, sem música nem eco.
   Pode ser vários arquivos (mp3, wav, m4a, gravação do WhatsApp…).
2. Coloque os arquivos em **`voz\amostras`**.
3. Dois cliques em **`clonar_voz.bat`** e escolha:

| Opção | Qualidade | Custo | Observação |
|---|---|---|---|
| **1. ElevenLabs** (recomendado) | Excelente em português | Plano Starter, a partir de ~US$ 5/mês | Crie a conta em elevenlabs.io e cole a API key em `ELEVENLABS_API_KEY` no `.env` antes |
| **2. No próprio PC** (XTTS-v2) | Boa | Grátis | Baixa ~2 GB. Com placa NVIDIA fala em 1 a 2 s; sem ela, pode levar 10 s ou mais |

O script cria a voz, salva tudo no `.env` e gera um `voz\teste.mp3` para você ouvir.
Se a voz clonada falhar (sem internet, por exemplo), ela usa a voz padrão para não ficar muda.

---

## 5. App do celular 📱

O app mostra **se o PC está ligado, desde quando** ou **quando foi visto pela última vez**, com CPU, memória, música tocando e a janela aberta. Nele você pode:

- conversar com a Ametista por **texto ou áudio**;
- **ver a tela do PC**;
- usar atalhos: pausar música, bloquear o PC, status, agenda;
- receber **avisos**, como "Elden Ring terminou de instalar" e lembretes.

**Como funciona:** o app fica hospedado de graça na sua conta Cloudflare. O PC abre uma conexão de saída até lá, então não precisa mexer no roteador. Tudo passa por conexão criptografada:

- o PC usa uma chave secreta só dele;
- cada celular recebe um token no pareamento.

**Publicar (uma vez):**

1. Instale o **Node.js LTS** (nodejs.org).
2. Dois cliques em **`publicar_celular.bat`**. Na primeira vez, o navegador abre para você entrar na Cloudflare (a conta gratuita serve).
   O script publica o app, cria a chave secreta e grava o endereço no `.env`.
3. Reinicie a Ametista.

**Parear o celular:**

1. 💎 → **Celular → Parear celular** → aponte a câmera para o QR code (o código vale 10 minutos e só uma vez).
2. No celular, "Adicionar à tela inicial": vira um app com o ícone da gema.

Perdeu o celular? 💎 → Celular → **Desconectar todos os celulares**.

**Limites de hoje:**

- os avisos aparecem quando você abre o app (ainda não chegam com o app fechado);
- ela **não liga** o PC que estiver desligado. Isso é possível no futuro com Wake-on-LAN e um aparelho que fique ligado em casa.

---

## 6. Steam 🎮

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

## 7. Agenda (Google + Outlook) 📅

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
5. Copie o **ID do aplicativo (cliente)** para `MS_CLIENT_ID` no `.env` e reinicie a Ametista.
6. 💎 → Conectar contas → **Outlook** → entre com a sua conta.

> A conta do trabalho (ex.: @fjengenharia.com) pode exigir que o TI da empresa aprove o app. Com a conta pessoal (Outlook.com/Hotmail), funciona direto.

Na hora de criar um compromisso, ela usa a agenda definida em `AGENDA_PADRAO` (google ou outlook), a não ser que você diga outra.

---

## 8. O que ela vê na tela 👀

Ela sempre sabe **qual janela está em primeiro plano**, por exemplo "AutoCAD – Planta Jundiaí.dwg". Assim entende pedidos como "salva isso" ou "que atalho faz isso aqui?".

Quando precisa ver de verdade, ela tira um print e analisa:

- *"que erro é esse?"*, *"resume essa página"*, *"o que tem na minha tela?"*;
- *"olha as duas telas"*, para monitores duplos;
- pelo celular: botão **Ver tela**.

A própria sobreposição não aparece nos prints. Só o dono pode pedir para ela ver a tela.

---

## 9. PC, Spotify e casa

- **PC:** volume, mídia, abrir e fechar programas, sites e pastas, pesquisar, bloquear, minimizar tudo, ditar texto e área de transferência. Para desligar ou reiniciar, ela sempre pergunta antes.
- **Spotify Premium:**
  1. Crie um app em developer.spotify.com.
  2. Em Redirect URI, coloque `http://127.0.0.1:8765/spotify/callback`.
  3. Copie o Client ID para `SPOTIFY_CLIENT_ID` no `.env`.
  4. 💎 → Conectar contas → Spotify.
- **Casa inteligente:** pelo Home Assistant.
  - Kit inicial sugerido: tomada Wi-Fi (R$ 40 a 80), lâmpada Wi-Fi (R$ 40 a 90) e controle infravermelho Wi-Fi (R$ 70 a 150) para ar-condicionado e TV, tudo compatível com Tuya/Smart Life.
  - Preencha `HA_URL` e `HA_TOKEN` no `.env`.

---

## 10. Ajustes (`.env`)

| Problema | Ajuste |
|---|---|
| Ela não percebe quando falo baixo | `LIMIAR_MIN=200` |
| Acorda sozinha com barulho | `LIMIAR_MIN=600` |
| Às vezes não me reconhece | `LIMIAR_VOZ=0.55` ou refaça o cadastro |
| Reconhece gente demais | `LIMIAR_VOZ=0.70` |
| Transcrição lenta | `WHISPER_MODELO=base`. Com NVIDIA: `WHISPER_DISPOSITIVO=cuda` |
| Não quero mostrar a janela aberta no celular | `NUVEM_MOSTRAR_JANELA=0` |
| Aviso da agenda com outra antecedência | `AVISO_AGENDA_MIN=15` (0 desliga) |

---

## 11. Estrutura

```
ametista/
  desktop.py        sobreposição, bandeja, atalho, QR code
  ouvido.py         microfone, palavra de ativação, transcrição, cadastro de voz
  identidade.py     quem está falando + permissões
  cerebro.py        roteador local + Claude + Ollama, personalidade
  voz.py            fala (ElevenLabs / XTTS / edge), com reserva automática
  pc.py             Windows: volume, programas, tela, janela ativa
  steam.py          jogos, unidades, instalação, aviso ao terminar
  agenda.py         Google + Outlook
  spotify.py        Spotify Premium
  nuvem.py          ligação com o app do celular
celular/            app do celular (PWA) + ponte na Cloudflare
web/                a sobreposição do PC
```
