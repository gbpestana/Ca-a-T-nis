#!/usr/bin/env python3
"""
Lê os comandos que você manda para o bot no Telegram e responde.

  /novo Air Jordan 5 Retro   -> adiciona à lista (e já manda os preços dele)
  /novo                      -> o bot pergunta qual tênis
  /remover 2   ou   /remover Air Jordan 3 Retro
  /remover                   -> o bot mostra a lista numerada e pergunta qual
  /lista                     -> mostra o que está sendo monitorado
  /atualizar (ou /resumo)    -> verifica as lojas agora e manda os preços
  Botões fixos no teclado: 🔄 Atualizar · 📋 Lista · ➕ Novo · 🗑️ Remover
  /cancelar                  -> cancela uma pergunta em aberto
  /ajuda

Só obedece mensagens do seu chat (TELEGRAM_CHAT_ID). Roda pelo GitHub Actions.
"""
from __future__ import annotations

import json
import os
import sys

import gerenciar
import monitor

ESTADO_BOT = monitor.DADOS / "telegram.json"

COMANDOS = [
    {"command": "novo", "description": "Adicionar um tênis à lista"},
    {"command": "remover", "description": "Remover um tênis da lista"},
    {"command": "lista", "description": "Ver o que está sendo monitorado"},
    {"command": "atualizar", "description": "Verificar as lojas agora e mandar os preços"},
    {"command": "cancelar", "description": "Cancelar a pergunta em aberto"},
    {"command": "ajuda", "description": "Como usar"},
]

AJUDA = (
    "👟 *Caça-tênis* — comandos:\n"
    "/novo – adicionar um tênis (ex.: /novo Air Jordan 5 Retro)\n"
    "/remover – remover um tênis (ex.: /remover 2)\n"
    "/lista – ver o que está sendo monitorado\n"
    "/atualizar – verificar as lojas agora e mandar os preços\n\n"
    "Ou use os botões fixos aqui embaixo 👇\n\n"
    "Eu verifico as lojas de manhã, à tarde e à noite, mando *um resumo por dia* "
    "e só aviso na hora se aparecer uma promoção ótima."
)


TECLADO = {
    "keyboard": [[{"text": "🔄 Atualizar"}, {"text": "📋 Lista"}],
                 [{"text": "➕ Novo"}, {"text": "🗑️ Remover"}]],
    "resize_keyboard": True,
    "is_persistent": True,
}
BOTOES = {"🔄 Atualizar": "/atualizar", "📋 Lista": "/lista",
          "➕ Novo": "/novo", "🗑️ Remover": "/remover"}
VERSAO_MENU = 2


def api(metodo: str, **dados):
    token = os.environ["TELEGRAM_TOKEN"]
    r = monitor._sessao.post(f"https://api.telegram.org/bot{token}/{metodo}",
                             json=dados, timeout=30, **monitor._KW)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"{metodo}: {j}")
    return j["result"]


def responder(texto: str) -> None:
    monitor._telegram(texto, os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_CHAT_ID"],
                      teclado=TECLADO)


def texto_lista(alvos: list[dict]) -> str:
    if not alvos:
        return "📭 A lista está vazia. Use /novo para adicionar um tênis."
    linhas = ["📋 *Monitorando agora:*"]
    linhas += [f"{i}. {a['nome']}" for i, a in enumerate(alvos, 1)]
    return "\n".join(linhas)


def adicionar(nome: str) -> str | None:
    nome = " ".join(nome.split())
    if not (3 <= len(nome) <= 60):
        responder("Nome muito curto ou muito longo. Ex.: /novo Air Jordan 5 Retro")
        return None
    alvos = gerenciar.carregar()
    if any(gerenciar.chave(a["nome"]) == gerenciar.chave(nome) for a in alvos):
        responder(f"*{nome}* já está na lista. 👍")
        return None
    alvos.append({"nome": nome, "busca": nome.lower()})
    gerenciar.salvar(alvos)
    responder(f"✅ Adicionado: *{nome}*\nJá vou buscar os preços dele...")
    return nome


def remover(arg: str) -> None:
    alvos = gerenciar.carregar()
    arg = arg.strip()
    alvo = None
    if arg.isdigit() and 1 <= int(arg) <= len(alvos):
        alvo = alvos[int(arg) - 1]
    else:
        alvo = next((a for a in alvos if gerenciar.chave(a["nome"]) == gerenciar.chave(arg)), None)
        if alvo is None:  # aceita parte do nome, se só um bater
            parecidos = [a for a in alvos if gerenciar.chave(arg) in gerenciar.chave(a["nome"])]
            alvo = parecidos[0] if len(parecidos) == 1 else None
    if alvo is None:
        responder(f"Não achei \"{arg}\" na lista.\n\n" + texto_lista(alvos)
                  + "\n\nMande o número, ex.: /remover 2")
        return
    gerenciar.salvar([a for a in alvos if a is not alvo])
    responder(f"🗑️ Removido: *{alvo['nome']}*\n\n" + texto_lista(gerenciar.carregar()))


PERGUNTA_NOVO = "Qual tênis você quer monitorar?"
PERGUNTA_REMOVER = "Qual remover?"


def tratar(texto: str, resposta_a: str, aguardando: str | None,
           acoes: dict) -> str | None:
    """Trata uma mensagem. Devolve o novo estado de 'aguardando'.
    `resposta_a` é o texto da mensagem do bot que você respondeu (se houver)."""
    texto = BOTOES.get(texto, texto)
    print(f"> {texto}")
    if not texto.startswith("/"):
        if resposta_a.startswith(PERGUNTA_NOVO) or aguardando == "novo":
            if (n := adicionar(texto)):
                acoes["novos"].append(n)
        elif PERGUNTA_REMOVER in resposta_a or aguardando == "remover":
            remover(texto)
        else:
            responder("Use os botões aqui embaixo ou o menu de comandos.\n\n" + AJUDA)
        return None

    cmd, _, arg = texto.partition(" ")
    cmd = cmd[1:].split("@")[0].lower()
    arg = arg.strip()
    if cmd in ("start", "ajuda", "help"):
        responder(AJUDA)
    elif cmd == "lista":
        responder(texto_lista(gerenciar.carregar()))
    elif cmd == "novo":
        if arg:
            if (n := adicionar(arg)):
                acoes["novos"].append(n)
        else:
            responder(f"{PERGUNTA_NOVO}\nEx.: *Air Jordan 5 Retro*")
            return "novo"
    elif cmd == "remover":
        if arg:
            remover(arg)
        else:
            alvos = gerenciar.carregar()
            if alvos:
                responder(texto_lista(alvos) + f"\n\n{PERGUNTA_REMOVER} Mande o número.")
                return "remover"
            responder(texto_lista(alvos))
    elif cmd in ("resumo", "atualizar", "refresh"):
        acoes["resumo"] = True
        if not acoes.get("silencioso"):
            responder("⏳ Verificando as lojas, já te mando os preços...")
    elif cmd == "cancelar":
        responder("Ok, cancelado.")
    else:
        responder("Não conheço esse comando.\n\n" + AJUDA)
    return None


def main() -> int:
    if not (os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")):
        print("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID não configurados.")
        return 0
    meu_chat = str(os.environ["TELEGRAM_CHAT_ID"]).strip()
    est = json.loads(ESTADO_BOT.read_text()) if ESTADO_BOT.exists() else {}
    aguardando = est.get("aguardando")
    acoes = {"novos": [], "resumo": False}

    msg_unica = os.getenv("MENSAGEM")  # veio do repassador (Cloudflare), já confirmada lá
    if msg_unica is not None:
        acoes["silencioso"] = True       # o repassador já respondeu "⏳ Recebi"
        aguardando = tratar(msg_unica.strip(), os.getenv("RESPOSTA_A", ""), None, acoes)
    else:
        if est.get("comandos_v") != VERSAO_MENU:  # registra menu e botões no Telegram
            api("setMyCommands", commands=COMANDOS)
            responder("🆕 Agora tem botões fixos aqui embaixo, inclusive o *🔄 Atualizar*.\n\n" + AJUDA)
            est["comandos_v"] = VERSAO_MENU
        try:
            updates = api("getUpdates", offset=est.get("offset", 0), timeout=0,
                          allowed_updates=["message"])
        except RuntimeError as e:
            if "409" in str(e) or "webhook" in str(e).lower():
                print("Respostas instantâneas (webhook) ativas: nada a fazer aqui.")
                return 0
            raise
        for up in updates:
            est["offset"] = up["update_id"] + 1
            msg = up.get("message") or {}
            if str(msg.get("chat", {}).get("id")) != meu_chat:
                continue  # ignora qualquer outra pessoa
            texto = (msg.get("text") or "").strip()
            if texto:
                resp = ((msg.get("reply_to_message") or {}).get("text") or "")
                aguardando = tratar(texto, resp, aguardando, acoes)

    est["aguardando"] = aguardando
    monitor.DADOS.mkdir(exist_ok=True)
    ESTADO_BOT.write_text(json.dumps(est, ensure_ascii=False, indent=2))

    if acoes["resumo"]:
        monitor.executar(forcar_resumo=True, titulo="🔄 *Preços atualizados agora*")
    elif acoes["novos"]:
        monitor.executar(forcar_resumo=True, somente=acoes["novos"],
                         titulo="🆕 *Preços do que você adicionou:*")
    return 0


if __name__ == "__main__":
    sys.exit(main())
