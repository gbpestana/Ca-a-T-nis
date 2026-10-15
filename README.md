# 👟 Caça-tênis

Monitor de preço e estoque de tênis em lojas oficiais e autorizadas (Nike, Artwalk, Authentic Feet, Magic Feet). Ele te avisa no WhatsApp quando aparece um preço bom **no seu tamanho**.

Roda sozinho no GitHub Actions, de graça, a cada 3 horas. Não depende do seu computador ligado.

## Como ele decide avisar

Um par só gera alerta se o seu tamanho estiver em estoque **e** pelo menos uma destas condições for verdadeira:

1. **Desconto real:** o preço está ≥ 35% abaixo do preço cheio de um Retro (R$ 1.799,99).
2. **Recorde do histórico:** é o menor preço já registrado para aquele tênis. Essa regra só começa a valer depois de 8 leituras, para o histórico ter alguma base.

O alerta traz link, preço, desconto e os cupons mais recentes daquela loja publicados no Promobit. Os cupons são para testar no carrinho, porque a loja decide se valem para o produto. O mesmo par não é avisado de novo, a não ser que o preço caia mais ou que passe uma semana.

Na **primeira rodada** você recebe uma mensagem "Caça-tênis ligado!" com o melhor preço atual de cada modelo.

## Instalação (uma vez só)

### 1. Ative o CallMeBot no seu WhatsApp
1. Abra <https://www.callmebot.com/blog/free-api-whatsapp-messages/> e salve nos contatos o número indicado lá.
2. Mande para esse contato a mensagem que a página pede (`I allow callmebot to send me messages`).
3. Você recebe de volta uma **apikey**. Guarde.

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
| `WHATSAPP_PHONE` | seu número com DDI, ex.: `+5511999998888` |
| `CALLMEBOT_APIKEY` | a apikey do passo 1 |

### 4. Primeira rodada
**Actions → Monitor de preços → Run workflow.** Em ~1 minuto chega a mensagem no WhatsApp. Depois disso ele roda sozinho a cada 3h.

## Adicionar ou remover tênis

**Pelo celular ou navegador:** vá em **Actions → Gerenciar lista de tênis → Run workflow** e preencha:

- **acao:** `adicionar`, `remover` ou `listar`
- **nome:** ex.: `Air Jordan 5 Retro`
- **busca** (opcional): o termo usado nas lojas, se for diferente do nome
- **excluir** (opcional): palavras que eliminam produtos, ex.: `low,se`

Depois de adicionar ou remover, ele já manda um resumo com os preços da lista nova.

**Pelo terminal:**
```bash
python gerenciar.py listar
python gerenciar.py adicionar "Air Jordan 11 Retro" --excluir low
python gerenciar.py remover "Air Jordan 3 Retro"
```

Também dá para editar `alvos.yaml` direto no GitHub.

## Ajustes (`config.yaml`)

- `tamanho`: seu número.
- `alerta.desconto_minimo_pct`: o desconto mínimo para avisar (padrão 35%).
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
python monitor.py --resumo      # manda o resumo atual no WhatsApp (com as variáveis de ambiente)
```
