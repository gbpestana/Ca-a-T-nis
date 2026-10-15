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


def main() -> int:
    if not (os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")):
        print("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID não configurados.")
        return 0
    meu_chat = str(os.environ["TELEGRAM_CHAT_ID"]).strip()
    est = json.loads(ESTADO_BOT.read_text()) if ESTADO_BOT.exists() else {}
    offset = est.get("offset", 0)
    aguardando = est.get("aguardando")

    if est.get("comandos_v") != VERSAO_MENU:  # registra menu e botões no Telegram
        api("setMyCommands", commands=COMANDOS)
        responder("🆕 Agora tem botões fixos aqui embaixo, inclusive o *🔄 Atualizar*.\n\n" + AJUDA)
        est["comandos_v"] = VERSAO_MENU

    novos: list[str] = []
    pedir_resumo = False
    for up in api("getUpdates", offset=offset, timeout=0, allowed_updates=["message"]):
        offset = up["update_id"] + 1
        msg = up.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != meu_chat:
            continue  # ignora qualquer outra pessoa
        texto = (msg.get("text") or "").strip()
        if not texto:
            continue
        texto = BOTOES.get(texto, texto)
        print(f"> {texto}")

        if texto.startswith("/"):
            cmd, _, arg = texto.partition(" ")
            cmd = cmd[1:].split("@")[0].lower()
            arg = arg.strip()
            aguardando = None
            if cmd in ("start", "ajuda", "help"):
                responder(AJUDA)
            elif cmd == "lista":
                responder(texto_lista(gerenciar.carregar()))
            elif cmd == "novo":
                if arg:
                    if (n := adicionar(arg)):
                        novos.append(n)
                else:
                    aguardando = "novo"
                    responder("Qual tênis você quer monitorar?\nEx.: *Air Jordan 5 Retro*")
            elif cmd == "remover":
                if arg:
                    remover(arg)
                else:
                    alvos = gerenciar.carregar()
                    if alvos:
                        aguardando = "remover"
                        responder(texto_lista(alvos) + "\n\nQual remover? Mande o número.")
                    else:
                        responder(texto_lista(alvos))
            elif cmd in ("resumo", "atualizar", "refresh"):
                pedir_resumo = True
                responder("⏳ Verificando as lojas, já te mando os preços...")
            elif cmd == "cancelar":
                responder("Ok, cancelado.")
            else:
                responder("Não conheço esse comando.\n\n" + AJUDA)
        elif aguardando == "novo":
            aguardando = None
            if (n := adicionar(texto)):
                novos.append(n)
        elif aguardando == "remover":
            aguardando = None
            remover(texto)
        else:
            responder("Use o menu de comandos (botão / ou ☰ ao lado do campo de texto).\n\n" + AJUDA)

    est.update(offset=offset, aguardando=aguardando)
    monitor.DADOS.mkdir(exist_ok=True)
    ESTADO_BOT.write_text(json.dumps(est, ensure_ascii=False, indent=2))

    if pedir_resumo:
        monitor.executar(forcar_resumo=True, titulo="🔄 *Preços atualizados agora*")
    elif novos:
        monitor.executar(forcar_resumo=True, somente=novos, titulo="🆕 *Preços do que você adicionou:*")
    return 0


if __name__ == "__main__":
    sys.exit(main())
