// Caça-tênis — repassador instantâneo (Cloudflare Worker)
//
// O Telegram entrega cada mensagem sua aqui na hora (webhook). O Worker:
//   - responde na hora o que é simples (lista, ajuda, perguntas do /novo e /remover);
//   - para o que dá trabalho (atualizar, adicionar, remover), responde "⏳ Recebi"
//     e aciona o GitHub Actions imediatamente (repository_dispatch).
//
// Variáveis do Worker (Settings → Variables and Secrets):
//   TELEGRAM_TOKEN  (secret)  token do bot (BotFather)
//   GH_TOKEN        (secret)  token do GitHub com "Contents: Read and write" no repositório
//   CHAT_ID         (texto)   seu chat id do Telegram
//   GH_REPO         (texto)   gbpestana/Ca-a-T-nis

const BOTOES = {
  "🔄 Atualizar": "/atualizar",
  "📋 Lista": "/lista",
  "➕ Novo": "/novo",
  "🗑️ Remover": "/remover",
};
const TECLADO = {
  keyboard: [
    [{ text: "🔄 Atualizar" }, { text: "📋 Lista" }],
    [{ text: "➕ Novo" }, { text: "🗑️ Remover" }],
  ],
  resize_keyboard: true,
  is_persistent: true,
};
const PERGUNTA_NOVO = "Qual tênis você quer monitorar?";
const PERGUNTA_REMOVER = "Qual remover?";
const AJUDA =
  "👟 <b>Caça-tênis</b> — use os botões aqui embaixo:\n" +
  "🔄 <b>Atualizar</b> – verifica as lojas agora e manda os preços\n" +
  "📋 <b>Lista</b> – o que está sendo monitorado\n" +
  "➕ <b>Novo</b> – adicionar um tênis (ou /novo Air Jordan 5 Retro)\n" +
  "🗑️ <b>Remover</b> – remover um tênis (ou /remover 2)\n\n" +
  "Eu verifico as lojas de manhã, à tarde e à noite, mando <b>um resumo por dia</b> " +
  "e só aviso na hora se aparecer uma promoção ótima.";

export default {
  async fetch(req, env) {
    if (req.method !== "POST") return new Response("caça-tênis: repassador ok");
    if (req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== (await segredo(env.TELEGRAM_TOKEN))) {
      return new Response("forbidden", { status: 403 });
    }
    let up;
    try {
      up = await req.json();
    } catch {
      return new Response("ok");
    }
    const msg = up.message;
    if (!msg || String(msg.chat?.id) !== String(env.CHAT_ID).trim() || !msg.text) {
      return new Response("ok"); // ignora qualquer outra pessoa
    }
    try {
      await tratar(msg, env);
    } catch (e) {
      await enviar(env, "⚠️ Algo deu errado no repassador: " + esc(String(e).slice(0, 200)));
    }
    return new Response("ok"); // sempre 200, para o Telegram não reenviar
  },
};

async function tratar(msg, env) {
  const texto = BOTOES[msg.text.trim()] || msg.text.trim();
  const respostaA = msg.reply_to_message?.text || "";

  if (!texto.startsWith("/")) {
    if (respostaA.startsWith(PERGUNTA_NOVO)) {
      return despachar(env, texto, respostaA, `⏳ Adicionando <b>${esc(texto)}</b> e buscando os preços...`);
    }
    if (respostaA.includes(PERGUNTA_REMOVER)) {
      return despachar(env, texto, respostaA, "⏳ Removendo...");
    }
    return enviar(env, AJUDA);
  }

  const [primeira, ...resto] = texto.split(/\s+/);
  const cmd = primeira.slice(1).split("@")[0].toLowerCase();
  const arg = resto.join(" ").trim();

  switch (cmd) {
    case "start":
    case "ajuda":
    case "help":
      return enviar(env, AJUDA);
    case "lista":
      return enviar(env, textoLista(await lerLista(env)));
    case "novo":
      if (arg) return despachar(env, texto, "", `⏳ Adicionando <b>${esc(arg)}</b> e buscando os preços...`);
      return enviar(env, `${PERGUNTA_NOVO}\nEx.: <b>Air Jordan 5 Retro</b>`, { force_reply: true, input_field_placeholder: "Nome do tênis" });
    case "remover": {
      if (arg) return despachar(env, texto, "", "⏳ Removendo...");
      const lista = await lerLista(env);
      if (!lista.length) return enviar(env, textoLista(lista));
      return enviar(env, `${textoLista(lista)}\n\n${PERGUNTA_REMOVER} Responda com o número.`, { force_reply: true, input_field_placeholder: "Número" });
    }
    case "atualizar":
    case "resumo":
    case "refresh":
      return despachar(env, texto, "", "⏳ Verificando as lojas, os preços chegam em 1–2 minutos...");
    case "cancelar":
      return enviar(env, "Ok, cancelado.");
    default:
      return enviar(env, "Não conheço esse comando.\n\n" + AJUDA);
  }
}

// ---------------------------------------------------------------- GitHub

async function despachar(env, mensagem, respostaA, aviso) {
  const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/dispatches`, {
    method: "POST",
    headers: gh(env),
    body: JSON.stringify({ event_type: "telegram", client_payload: { mensagem, resposta_a: respostaA } }),
  });
  if (r.status !== 204) {
    throw new Error(`GitHub respondeu ${r.status}: ${(await r.text()).slice(0, 150)}`);
  }
  return enviar(env, aviso);
}

async function lerLista(env) {
  const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/contents/alvos.yaml`, {
    headers: { ...gh(env), Accept: "application/vnd.github.raw" },
  });
  if (!r.ok) throw new Error(`não consegui ler a lista (GitHub ${r.status})`);
  const yaml = await r.text();
  return [...yaml.matchAll(/^- nome:\s*(.+)$/gm)].map((m) => m[1].trim().replace(/^(['"])(.*)\1$/, "$2"));
}

function textoLista(nomes) {
  if (!nomes.length) return "📭 A lista está vazia. Toque em ➕ Novo para adicionar um tênis.";
  return "📋 <b>Monitorando agora:</b>\n" + nomes.map((n, i) => `${i + 1}. ${esc(n)}`).join("\n");
}

function gh(env) {
  return {
    Authorization: `Bearer ${env.GH_TOKEN}`,
    Accept: "application/vnd.github+json",
    "User-Agent": "caca-tenis-worker",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

// ---------------------------------------------------------------- Telegram

async function enviar(env, html, teclado = TECLADO) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: env.CHAT_ID,
      text: html,
      parse_mode: "HTML",
      disable_web_page_preview: true,
      reply_markup: teclado,
    }),
  });
  if (!r.ok) console.log("Telegram", r.status, await r.text());
}

// Segredo do webhook derivado do token (o workflow "Respostas instantâneas" usa a mesma conta).
async function segredo(token) {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(String(token).trim()));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
