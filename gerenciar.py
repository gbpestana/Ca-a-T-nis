#!/usr/bin/env python3
"""
Adiciona, remove ou lista os tênis monitorados (alvos.yaml).

  python gerenciar.py listar
  python gerenciar.py adicionar "Air Jordan 5 Retro"
  python gerenciar.py adicionar "Air Jordan 11 Retro" --busca "air jordan 11 retro" --excluir low
  python gerenciar.py remover "Air Jordan 3 Retro"
"""
import argparse
import sys
from pathlib import Path

import yaml

ARQ = Path(__file__).resolve().parent / "alvos.yaml"


def carregar() -> list[dict]:
    if not ARQ.exists():
        return []
    return (yaml.safe_load(ARQ.read_text(encoding="utf-8")) or {}).get("alvos") or []


def salvar(alvos: list[dict]) -> None:
    ARQ.write_text(yaml.safe_dump({"alvos": alvos}, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="acao", required=True)
    sub.add_parser("listar")
    a = sub.add_parser("adicionar")
    a.add_argument("nome")
    a.add_argument("--busca", help="termo usado na busca das lojas (padrão: o próprio nome)")
    a.add_argument("--excluir", default="", help="palavras extras para ignorar, separadas por vírgula")
    r = sub.add_parser("remover")
    r.add_argument("nome")
    args = ap.parse_args()

    alvos = carregar()
    chave = lambda s: " ".join(s.lower().split())

    if args.acao == "listar":
        if not alvos:
            print("(lista vazia)")
        for i, al in enumerate(alvos, 1):
            extra = f"  [exclui: {', '.join(al['excluir'])}]" if al.get("excluir") else ""
            print(f"{i}. {al['nome']}  (busca: \"{al['busca']}\"){extra}")
        return 0

    if args.acao == "adicionar":
        if any(chave(x["nome"]) == chave(args.nome) for x in alvos):
            print(f"'{args.nome}' já está na lista.")
            return 0
        novo = {"nome": args.nome.strip(), "busca": (args.busca or args.nome).strip().lower()}
        exc = [e.strip() for e in args.excluir.split(",") if e.strip()]
        if exc:
            novo["excluir"] = exc
        alvos.append(novo)
        salvar(alvos)
        print(f"Adicionado: {novo['nome']}")
        return 0

    restantes = [x for x in alvos if chave(x["nome"]) != chave(args.nome)]
    if len(restantes) == len(alvos):
        print(f"'{args.nome}' não está na lista. Use 'listar' para ver os nomes.")
        return 1
    salvar(restantes)
    print(f"Removido: {args.nome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
