# 👟 Caça-tênis

Monitor de preço e estoque de tênis em lojas oficiais e autorizadas. Ele te avisa no **Telegram** e/ou no **WhatsApp** quando aparece um preço bom **no seu tamanho**.

Roda sozinho no GitHub Actions, de graça. Não depende do seu computador ligado.

## Como funciona

- **Quando verifica:** as lojas são verificadas **3 vezes por dia**, por volta de **8h, 14h e 20h**.
- **Resumo do dia:** chega uma vez por dia, na verificação da noite. Ele traz o melhor preço atual de cada tênis no seu tamanho, as quedas de preço do dia e as promoções da Nike divulgadas no Promobit.
- **Aviso na hora:** só para **promoção ótima**, ou seja, preço pelo menos **35% abaixo** do preço cheio do próprio produto. O aviso traz link, preço e os cupons recentes daquela loja.
- **Novo menor preço:** o histórico passa a valer depois de 6 leituras, uns 2 dias. Um novo menor preço que não seja "ótimo" entra no resumo do dia em vez de te interromper.
- **Lojas lidas direto, com estoque do seu número verificado:** Artwalk, Authentic Feet, Magic Feet, Ostore (multimarcas), New Balance, Fila, Mizuno e Olympikus.
- **Lojas lidas via Promobit:** Nike, Centauro, Netshoes, Zattini, Dafiti, Adidas, Puma, Vans e outras da lista `lojas_permitidas`. Essas lojas bloqueiam acessos do GitHub, então o monitor busca as promoções ativas publicadas pela comunidade do **Promobit**. Nesses casos o estoque do seu número não é verificado, e o aviso diz isso. Marketplaces como Amazon, Mercado Livre e Shopee ficam de fora por causa de vendedores terceiros.
- **Testar se uma loja nova funciona:** use **Actions → Diagnóstico de lojas**.
- **Sem repetição:** o mesmo par não é avisado de novo, a não ser que o preço caia mais ou que passe uma semana.

## Instalação (uma vez só)

### 1. Configure onde quer receber os avisos

Configure pelo menos um canal. Se os dois estiverem configurados, ele manda nos dois.

**Telegram (recomendado, funciona na hora)**
1. No Telegram, abra o **@BotFather**, mande `/newbot` e escolha um nome (ex.: `Caça-tênis do Gabriel`) e um usuário terminado em `bot`.
2. O BotFather te responde com um **token** (algo como `123456:ABC-...`). Guarde.
3. Abra a conversa com o seu bot novo e mande qualquer mensagem (ex.: `oi`).
4. No navegador, abra `https://api.telegram.org/botSEU_TOKEN/getUpdates` (troque `SEU_TOKEN` pelo token). Procure `"chat":{"id":` e anote o número que vem logo depois. Esse é o seu **chat id**.

**WhatsApp (via CallMeBot, quando houver vaga)**
1. Abra <https://www.callmebot.com/blog/free-api-whatsapp-messages/> e salve nos contatos o número indicado lá.
2. Mande para esse contato a mensagem que a página pede (`I allow callmebot to send me messages`).
3. Você recebe de volta uma **apikey**.

### 2. Suba o projeto no GitHub
Crie um repositório **privado** (ex.: `caca-tenis`) e envie estes arquivos. A pasta `.github/` é obrigatória: é ela que agenda o monitor.

```bash
cd caca-tenis
git init && git add . && git commit -m "caça-tênis"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/caca-tenis.git
git push -u origin main
```

### 3. Cadastre os segredos
No repositório: **Settings → Secrets and variables → Actions → New repository secret**

| Nome | Valor |
|---|---|
| `TELEGRAM_TOKEN` | o token do BotFather |
| `TELEGRAM_CHAT_ID` | o seu chat id |
| `WHATSAPP_PHONE` | (opcional) seu número com DDI, ex.: `+5511999998888` |
| `CALLMEBOT_APIKEY` | (opcional) a apikey do CallMeBot |

### 4. Primeira rodada
**Actions → Monitor de preços → Run workflow.** Em ~1 minuto chega a mensagem "Caça-tênis ligado!". Depois disso ele roda sozinho.

## Adicionar ou remover tênis

**Pelo Telegram (mais fácil):** use o menu de comandos do seu bot, no botão `/` ou `☰` ao lado do campo de texto.

| Comando | O que faz |
|---|---|
| `/novo Air Jordan 5 Retro` | adiciona e já te manda os preços dele |
| `/novo` | o bot pergunta qual tênis |
| `/remover 2` ou `/remover` | remove pelo número da lista, ou o bot pergunta qual |
| `/lista` | mostra o que está sendo monitorado |
| `/resumo` | manda o resumo de preços agora |

O bot confere seus comandos **a cada 5 minutos**. Em horários de pico o GitHub às vezes atrasa um pouco o agendamento. Só mensagens do seu chat (`TELEGRAM_CHAT_ID`) são aceitas.

**Pelo GitHub:** vá em **Actions → Gerenciar lista de tênis → Run workflow**. Por lá também dá para informar palavras a excluir da busca, ex.: `low,se`.

## Ajustes (`config.yaml`)

- `tamanho`: seu número.
- `alerta.desconto_otimo_pct`: o desconto que conta como promoção ótima e é avisado na hora (padrão 35%).
- `resumo_diario.hora`: a partir de que hora sai o resumo do dia (padrão 19, ou seja, na verificação das 20h).
- `incluir_feminino`: incluir modelos femininos.
- `excluir_sempre`: palavras que eliminam produtos. Por padrão já elimina RM, infantil, GS etc.
- `lojas`: liga e desliga lojas. Qualquer loja na plataforma VTEX entra com `tipo: vtex` e o `dominio`.

## Como acompanhar

- **Cada rodada:** a aba **Actions** mostra uma tabela com tudo o que foi encontrado, com preço, loja e se tem o seu tamanho.
- **Histórico completo:** fica em `dados/historico.csv`, e você pode abrir no Excel ou Google Sheets.
- **Se todas as lojas falharem numa rodada:** o job fica vermelho e o GitHub te manda e-mail.

## Rodar no seu computador

```bash
pip install -r requirements.txt
python monitor.py --sem-envio   # imprime as mensagens em vez de mandar
python monitor.py --resumo      # manda o resumo atual (com as variáveis de ambiente dos canais)
```
