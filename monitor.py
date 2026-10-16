#!/usr/bin/env python3
"""
Caça-tênis: monitora preço e estoque de tênis em lojas confiáveis
e avisa no Telegram e/ou WhatsApp quando aparece um preço bom no seu tamanho.

Uso:
  python monitor.py              # rodada normal (só avisa se tiver oferta boa)
  python monitor.py --resumo     # manda o melhor preço atual de cada alvo
  python monitor.py --sem-envio  # roda tudo mas só imprime as mensagens (teste)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import yaml

RAIZ = Path(__file__).resolve().parent
DADOS = RAIZ / "dados"
HISTORICO = DADOS / "historico.csv"
ESTADO = DADOS / "estado.json"
FUSO = timezone(timedelta(hours=-3))  # São Paulo

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------- HTTP

try:  # curl_cffi imita o "jeito" do Chrome e passa melhor por proteções anti-bot
    from curl_cffi import requests as _http  # type: ignore

    _KW = {"impersonate": "chrome"}
except Exception:  # pragma: no cover
    import requests as _http  # type: ignore

    _KW = {}

_sessao = _http.Session()


def baixar(url: str, json_: bool = False, tentativas: int = 2):
    ultimo = None
    for i in range(tentativas):
        try:
            r = _sessao.get(
                url,
                headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"},
                timeout=25,
                **_KW,
            )
            if r.status_code in (200, 206):
                return r.json() if json_ else r.text
            ultimo = f"HTTP {r.status_code}"
        except Exception as e:  # rede, timeout, JSON inválido...
            ultimo = f"{type(e).__name__}: {e}"
        time.sleep(2 + i * 3)
    raise RuntimeError(f"{url} -> {ultimo}")


def next_data(html: str) -> dict:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("página sem __NEXT_DATA__ (layout mudou ou acesso bloqueado)")
    return json.loads(m.group(1))


# ---------------------------------------------------------------- texto


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def palavras(s: str) -> set[str]:
    return set(normalizar(s).split())


def corresponde(nome_produto: str, alvo: dict, cfg: dict) -> bool:
    """O produto bate com o alvo? Todas as palavras relevantes da busca precisam
    aparecer no nome, e nenhuma palavra proibida pode aparecer."""
    nome = palavras(nome_produto)
    excluir = set(cfg.get("excluir_sempre", [])) | set(alvo.get("excluir", []))
    if not cfg.get("incluir_feminino"):
        excluir |= {"feminino", "women", "wmns"}
    if nome & {normalizar(x) for x in excluir}:
        return False
    if alvo.get("padrao"):
        return re.search(alvo["padrao"], normalizar(nome_produto)) is not None
    opcionais = set(cfg.get("palavras_opcionais", []))
    exigidas = palavras(alvo["busca"]) - opcionais
    return exigidas <= nome


def brl(v: float | None) -> str:
    if v is None:
        return "-"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


# ---------------------------------------------------------------- ofertas


@dataclass
class Oferta:
    alvo: str
    loja: str
    produto: str
    apelido: str
    url: str
    preco: float  # melhor preço (Pix, quando a loja informa)
    preco_cheio: float | None
    tem_tamanho: bool | None  # None = loja não informa estoque por tamanho

    @property
    def desconto_pct(self) -> float:
        if self.preco_cheio and self.preco_cheio > self.preco:
            return 100 * (1 - self.preco / self.preco_cheio)
        return 0.0


def coletar_vtex(nome_loja: str, loja: dict, alvo: dict, cfg: dict) -> list[Oferta]:
    dom = loja["dominio"]
    termo = quote(alvo["busca"])
    try:
        produtos = baixar(
            f"https://{dom}/api/catalog_system/pub/products/search?ft={termo}&_from=0&_to=49",
            json_=True,
        )
    except RuntimeError:  # algumas lojas VTEX só respondem pela busca nova
        dados = baixar(
            f"https://{dom}/api/io/_v/api/intelligent-search/product_search/?query={termo}&count=50",
            json_=True,
        )
        produtos = dados.get("products", [])

    tam = str(cfg["tamanho"])
    ofertas = []
    for p in produtos:
        nome = p.get("productName", "")
        if not corresponde(nome, alvo, cfg):
            continue
        precos, preco_tam, cheio_tam = [], None, None
        for item in p.get("items", []):
            ofs = [s.get("commertialOffer", {}) for s in item.get("sellers", [])]
            com_estoque = [o for o in ofs if (o.get("AvailableQuantity") or 0) > 0 and o.get("Price")]
            for o in com_estoque:
                precos.append((o["Price"], o.get("ListPrice")))
            if com_estoque and _item_tamanho(item) == tam:
                melhor = min(com_estoque, key=lambda o: o["Price"])
                preco_tam, cheio_tam = melhor["Price"], melhor.get("ListPrice")
        if preco_tam is None and not precos:
            continue  # esgotado em tudo
        preco, cheio = (preco_tam, cheio_tam) if preco_tam is not None else min(precos)
        cor = (p.get("Cor") or [""])[0] if isinstance(p.get("Cor"), list) else ""
        link = p.get("link") or f"https://{dom}/{p.get('linkText', '')}/p"
        ofertas.append(
            Oferta(alvo["nome"], nome_loja, nome.strip(), cor, link, float(preco),
                   float(cheio) if cheio else None, preco_tam is not None)
        )
    return ofertas


def _item_tamanho(item: dict) -> str | None:
    if isinstance(item.get("Tamanho"), list) and item["Tamanho"]:
        return str(item["Tamanho"][0]).strip()
    for v in item.get("variations", []) or []:
        if isinstance(v, dict) and normalizar(v.get("name", "")) == "tamanho" and v.get("values"):
            return str(v["values"][0]).strip()
    m = re.search(r"[-\s](\d{2}(?:[.,]5)?)\s*$", item.get("name", ""))
    return m.group(1).replace(",", ".") if m else None


def coletar_nike(nome_loja: str, loja: dict, alvo: dict, cfg: dict) -> list[Oferta]:
    base = "https://www.nike.com.br"
    html = baixar(f"{base}/busca?term={quote(alvo['busca'])}")
    produtos = next_data(html)["props"]["pageProps"]["data"]["products"]
    tam = str(cfg["tamanho"])
    ofertas = []
    for p in produtos:
        d = p.get("details", {}) or {}
        nome = (p.get("name") or "").strip()
        if not corresponde(nome, alvo, cfg) or p.get("status") != "available":
            continue
        if d.get("ageRange") and d["ageRange"] != "Adulto":
            continue
        generos = d.get("genders") or []
        if generos and not cfg.get("incluir_feminino") and not {"Masculino", "Unissex"} & set(generos):
            continue
        preco = p.get("price")
        pix = ((p.get("variations") or [{}])[0] or {}).get("pixDiscount") or {}
        if pix.get("price"):
            preco = pix["price"]
        cheio = p.get("oldPrice") or p.get("price")
        url = base + p["url"] if p.get("url", "").startswith("/") else p.get("url", "")

        tem_tam = False
        try:  # estoque por tamanho fica na página do produto
            prod = next_data(baixar(url))["props"]["pageProps"]["product"]
            for s in prod.get("sizes", []):
                if str(s.get("description", "")).strip() == tam:
                    tem_tam = bool(s.get("hasStock") and s.get("isAvailable", True))
        except Exception as e:
            print(f"  ! nike: não consegui ler tamanhos de {url}: {e}")
        time.sleep(1)
        ofertas.append(
            Oferta(alvo["nome"], nome_loja, nome, (d.get("nickname") or "").strip(), url,
                   float(preco), float(cheio) if cheio else None, tem_tam)
        )
    return ofertas


def coletar_promobit(nome_loja: str, loja: dict, alvo: dict, cfg: dict) -> list[Oferta]:
    """Promoções da loja publicadas pela comunidade do Promobit. Não informa
    estoque por tamanho (tem_tamanho=None): o aviso pede para conferir o número."""
    slug = loja["promobit"]
    dados = next_data(baixar(f"https://www.promobit.com.br/cupons/loja/{slug}/"))
    brutos = dados["props"]["pageProps"]["serverOffers"]["offers"]
    limite = datetime.now(FUSO) - timedelta(days=loja.get("dias", 2))
    ofertas = []
    for of in brutos:
        titulo = of.get("offerTitle", "")
        if not corresponde(titulo, alvo, cfg) or not of.get("offerPrice"):
            continue
        if any(x in (of.get("offerStatusName") or "").upper() for x in ("EXPIR", "ENCERR", "FINISH")):
            continue
        try:
            pub = datetime.strptime(of["offerPublished"], "%Y-%m-%dT%H:%M:%S%z")
        except Exception:
            continue
        if pub < limite:
            continue
        url = f"https://www.promobit.com.br/oferta/{of.get('offerSlug', of.get('offerId'))}/"
        ofertas.append(Oferta(alvo["nome"], nome_loja, titulo.strip(), "", url,
                              float(of["offerPrice"]),
                              float(of["offerOldPrice"]) if of.get("offerOldPrice") else None,
                              None))
    return ofertas


_promobit_slug: dict[str, str] = {}  # "promobit:Netshoes" -> "netshoes" (para buscar cupons)


def coletar_promobit_busca(nome_loja: str, loja: dict, alvo: dict, cfg: dict) -> list[Oferta]:
    """Busca o termo no Promobit e fica só com promoções ATIVAS de lojas da lista
    `lojas_permitidas`. Cobre lojas que bloqueiam o GitHub (Nike, Centauro, Netshoes...).
    Não informa estoque por tamanho (tem_tamanho=None)."""
    d = baixar(f"https://api.promobit.com.br/search?q={quote(alvo['busca'])}", json_=True)
    permitidas = {normalizar(x) for x in loja.get("lojas_permitidas", [])}
    limite = datetime.now(FUSO) - timedelta(days=loja.get("dias", 3))
    ofertas = []
    for of in d.get("active_offers") or []:
        loja_nome = (of.get("store_name") or "").strip()
        titulo = of.get("offer_title") or ""
        if normalizar(loja_nome) not in permitidas or not of.get("offer_price"):
            continue
        if not corresponde(titulo, alvo, cfg):
            continue
        if any(x in (of.get("offer_status_name") or "").upper() for x in ("EXPIR", "ENCERR", "FINISH")):
            continue
        try:
            pub = datetime.strptime(of["offer_published"], "%Y-%m-%dT%H:%M:%S%z")
        except Exception:
            continue
        if pub < limite:
            continue
        chave_loja = f"promobit:{loja_nome}"
        if of.get("store_param"):
            _promobit_slug[chave_loja] = of["store_param"]
        url = f"https://www.promobit.com.br/oferta/{of.get('offer_slug') or of.get('offer_id')}/"
        ofertas.append(Oferta(alvo["nome"], chave_loja, titulo.strip(), "", url,
                              float(of["offer_price"]),
                              float(of["offer_old_price"]) if of.get("offer_old_price") else None,
                              None))
    return ofertas


COLETORES = {"vtex": coletar_vtex, "nike": coletar_nike, "promobit": coletar_promobit,
             "promobit_busca": coletar_promobit_busca}

# ---------------------------------------------------------------- cupons

_cache_cupons: dict[str, list[dict]] = {}


def cupons(slug: str | None, cfg: dict) -> list[dict]:
    """Cupons recentes publicados no Promobit para a loja. São sugestões:
    a loja decide no carrinho se o cupom vale para aquele produto."""
    if not slug:
        return []
    if slug in _cache_cupons:
        return _cache_cupons[slug]
    lista = []
    try:
        dados = next_data(baixar(f"https://www.promobit.com.br/cupons/loja/{slug}/"))
        brutos = dados["props"]["pageProps"]["serverCoupons"]["coupons"]
        limite = datetime.now(FUSO) - timedelta(days=cfg["cupons"]["dias"])
        for c in brutos:
            codigo = (c.get("couponCode") or "").strip()
            if not codigo or "link" in codigo.lower():
                continue
            try:
                pub = datetime.strptime(c["couponPublished"], "%Y-%m-%dT%H:%M:%S%z")
            except Exception:
                continue
            if pub < limite:
                continue
            lista.append({"codigo": codigo, "titulo": c.get("couponTitle", ""),
                          "obs": c.get("couponInstructions", ""), "pub": pub})
        lista.sort(key=lambda c: c["pub"], reverse=True)
        lista = lista[: cfg["cupons"]["maximo"]]
    except Exception as e:
        print(f"  ! cupons {slug}: {e}")
    _cache_cupons[slug] = lista
    return lista


# ---------------------------------------------------------------- estado / histórico


def carregar_estado() -> dict:
    est = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    est.setdefault("esgotados", {})
    est.setdefault("iniciado", False)
    est.setdefault("alvos", {})
    est.setdefault("alertas", {})
    est.setdefault("pendentes", [])   # destaques guardados para o resumo do dia
    est.setdefault("ultimo_resumo", None)
    return est


def salvar(estado: dict, ofertas: list[Oferta], agora: datetime) -> None:
    DADOS.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2))
    novo = not HISTORICO.exists()
    with HISTORICO.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["data", "alvo", "loja", "produto", "apelido", "preco",
                        "preco_cheio", "tem_tamanho", "url"])
        for o in ofertas:
            w.writerow([agora.isoformat(timespec="minutes"), o.alvo, o.loja, o.produto,
                        o.apelido, f"{o.preco:.2f}",
                        f"{o.preco_cheio:.2f}" if o.preco_cheio else "",
                        "" if o.tem_tamanho is None else int(o.tem_tamanho), o.url])


# ---------------------------------------------------------------- decisão


def decidir(ofertas: list[Oferta], estado: dict, cfg: dict, agora: datetime,
            alvos: list[dict] | None = None):
    """Separa o que é urgente do que pode esperar o resumo do dia.

    - imediatos: promoção ÓTIMA (desconto >= desconto_otimo_pct sobre o preço
      cheio do próprio produto, ou sobre o `preco_referencia` do alvo, se houver).
      Vai na hora para o Telegram.
    - destaques: novo menor preço do histórico (sem ser ótimo). Fica guardado em
      estado["pendentes"] e sai no resumo diário.
    """
    a = cfg["alerta"]
    pct_otimo = a["desconto_otimo_pct"]
    ref_alvo = {x["nome"]: x.get("preco_referencia") for x in (alvos or [])}
    imediatos = []

    por_alvo: dict[str, list[Oferta]] = {}
    for o in ofertas:
        por_alvo.setdefault(o.alvo, []).append(o)

    for nome_alvo, lista in por_alvo.items():
        info = estado["alvos"].setdefault(nome_alvo, {"leituras": 0, "minimo": None})
        minimo_ant = info["minimo"]
        historico_ok = info["leituras"] >= a["leituras_minimas_historico"]
        esgotados = estado.setdefault("esgotados", {})  # url -> preço quando estava sem o número
        for o in sorted(lista, key=lambda o: o.preco):
            if o.tem_tamanho is False:
                esgotados[o.url] = {"preco": o.preco, "alvo": o.alvo,
                                    "desde": esgotados.get(o.url, {}).get("desde",
                                                                          agora.isoformat(timespec="minutes"))}
                continue
            ref = ref_alvo.get(o.alvo) or o.preco_cheio
            # Voltou o seu número num par que estava mais barato que as opções com estoque?
            antes = esgotados.pop(o.url, None) if o.tem_tamanho else None
            com_tam = [x.preco for x in lista if x.tem_tamanho and x.url != o.url]
            if antes and o.desconto_pct >= a.get("desconto_volta_pct", 20) \
                    and (not com_tam or o.preco < min(com_tam) - 0.01):
                estado["alertas"][o.url] = {"preco": o.preco, "data": agora.isoformat()}
                imediatos.append((o, [f"voltou o {cfg['tamanho']} neste par com "
                                      f"{o.desconto_pct:.0f}% de desconto"]))
                continue
            otimo = bool(ref) and o.preco <= ref * (1 - pct_otimo / 100)
            recorde = (o.tem_tamanho and a["bater_minimo_historico"] and historico_ok
                       and minimo_ant is not None and o.preco < minimo_ant - 0.01)
            if not (otimo or recorde) or not _deve_avisar(o, estado, agora):
                continue
            estado["alertas"][o.url] = {"preco": o.preco, "data": agora.isoformat()}
            if otimo:
                pct = 100 * (1 - o.preco / ref)
                motivos = [f"{pct:.0f}% abaixo do preço cheio ({brl(ref)})"]
                if recorde:
                    motivos.append(f"menor preço já registrado (antes: {brl(minimo_ant)})")
                imediatos.append((o, motivos))
            else:
                d = asdict(o)
                d["motivo"] = f"novo menor preço (antes: {brl(minimo_ant)})"
                d["quando"] = agora.isoformat(timespec="minutes")
                estado["pendentes"].append(d)
        verificadas = [o.preco for o in lista if o.tem_tamanho]
        if verificadas and (info["minimo"] is None or min(verificadas) < info["minimo"]):
            info["minimo"], info["minimo_em"] = min(verificadas), agora.isoformat(timespec="minutes")
        info["leituras"] += 1
    return imediatos


def _deve_avisar(o: Oferta, estado: dict, agora: datetime) -> bool:
    ant = estado["alertas"].get(o.url)
    if not ant:
        return True
    if o.preco < ant["preco"] - 0.01:  # caiu mais desde o último aviso
        return True
    return agora - datetime.fromisoformat(ant["data"]) > timedelta(days=7)


def hora_do_resumo(estado: dict, cfg: dict, agora: datetime) -> bool:
    """Um resumo por dia: na primeira rodada a partir de resumo_diario.hora que
    ainda não mandou o resumo de hoje."""
    hoje = agora.date().isoformat()
    return agora.hour >= cfg["resumo_diario"]["hora"] and estado.get("ultimo_resumo") != hoje


# ---------------------------------------------------------------- mensagens


def _nome_loja(o, cfg) -> str:
    chave = o if isinstance(o, str) else o.loja
    if chave.startswith("promobit:"):
        return f"{chave.split(':', 1)[1]} (via Promobit)"
    return cfg["lojas"].get(chave, {}).get("nome", chave)


def _slug_cupons(chave: str, cfg) -> str | None:
    if chave.startswith("promobit:"):
        return _promobit_slug.get(chave)
    return cfg["lojas"].get(chave, {}).get("cupons_promobit")


def msg_alerta(o: Oferta, motivos: list[str], cfg: dict) -> str:
    titulo = o.produto + (f' "{o.apelido}"' if o.apelido else "")
    tam = (f"📏 Tamanho {cfg['tamanho']} disponível" if o.tem_tamanho
           else f"📏 Estoque do {cfg['tamanho']} não verificado — confira na loja")
    voltou = any(m.startswith("voltou o") for m in motivos)
    linhas = [
        f"🔔 *VOLTOU O SEU NÚMERO*" if voltou else f"🚨 *PROMOÇÃO*",
        f"👟 *{titulo}*",
        f"🏬 {_nome_loja(o, cfg)}",
        f"💰 *{brl(o.preco)}*" + (f" (de {brl(o.preco_cheio)}, -{o.desconto_pct:.0f}%)"
                                 if o.desconto_pct >= 1 else ""),
        tam,
        "🔥 " + "; ".join(motivos),
        f"🔗 {o.url}",
    ]
    linhas += _linhas_cupons(_slug_cupons(o.loja, cfg), cfg)
    return "\n".join(linhas)


def _linhas_cupons(slug, cfg) -> list[str]:
    cs = cupons(slug, cfg)
    if not cs:
        return []
    return ["🎟️ Cupons recentes p/ testar no carrinho:",
            *[f"   • *{c['codigo']}* – {c['titulo'][:70]}" for c in cs]]


def msg_resumo(ofertas: list[Oferta], alvos: list[dict], estado: dict, cfg: dict,
               titulo: str) -> str:
    tam = cfg["tamanho"]
    linhas = [titulo, f"Tamanho {tam} · melhor preço de cada um agora:", ""]
    for alvo in alvos:
        com = sorted([o for o in ofertas if o.alvo == alvo["nome"] and o.tem_tamanho],
                     key=lambda o: o.preco)
        sem = sorted([o for o in ofertas if o.alvo == alvo["nome"] and o.tem_tamanho is False],
                     key=lambda o: o.preco)
        if not com:
            linhas.append(f"• *{alvo['nome']}*: nada no {tam} agora")
        else:
            o = com[0]
            ap = f' "{o.apelido}"' if o.apelido else ""
            desc = f" (-{o.desconto_pct:.0f}%)" if o.desconto_pct >= 1 else ""
            linhas.append(f"• *{alvo['nome']}*{ap} – {brl(o.preco)}{desc} na {_nome_loja(o, cfg)}"
                          f" · {len(com)} opç{'ão' if len(com) == 1 else 'ões'} no {tam}")
            linhas.append(f"  {o.url}")
        if sem and (not com or sem[0].preco < com[0].preco - 0.01):
            x = sem[0]
            ap = f' "{x.apelido}"' if x.apelido else ""
            desc = f" (-{x.desconto_pct:.0f}%)" if x.desconto_pct >= 1 else ""
            linhas.append(f"  💤 Mais barato, mas *sem o {tam}*:{ap} {brl(x.preco)}{desc} na "
                          f"{_nome_loja(x, cfg)} — te aviso se o {tam} voltar")
            linhas.append(f"  {x.url}")

    nomes = {a["nome"] for a in alvos}
    pend = [p for p in estado.get("pendentes", []) if p["alvo"] in nomes]
    if pend:
        linhas += ["", "🔻 *Quedas de preço desde o último resumo:*"]
        for p in sorted(pend, key=lambda p: p["preco"]):
            ap = f' "{p["apelido"]}"' if p["apelido"] else ""
            linhas.append(f"• {p['produto']}{ap} – {brl(p['preco'])} na "
                          f"{_nome_loja(p['loja'], cfg)} ({p['motivo']})")
            linhas.append(f"  {p['url']}")

    sem_tam = sorted([o for o in ofertas if o.tem_tamanho is None], key=lambda o: o.preco)
    if sem_tam:
        linhas += ["", "📣 *Promoções divulgadas no Promobit* (confira o seu número):"]
        for o in sem_tam[:6]:
            desc = f" (-{o.desconto_pct:.0f}%)" if o.desconto_pct >= 1 else ""
            linhas.append(f"• {o.produto} – {brl(o.preco)}{desc} na {_nome_loja(o, cfg)}")
            linhas.append(f"  {o.url}")
    return "\n".join(linhas)


# ---------------------------------------------------------------- envio


def _telegram(texto: str, token: str, chat_id: str, teclado: dict | None = None) -> None:
    # *negrito* (formato do WhatsApp) -> <b>negrito</b> (HTML do Telegram)
    html = texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = re.sub(r"\*([^*\n]+)\*", r"<b>\1</b>", html)
    r = _sessao.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": html, "parse_mode": "HTML",
              "disable_web_page_preview": True,
              **({"reply_markup": teclado} if teclado else {})},
        timeout=25,
        **_KW,
    )
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")


def _whatsapp(texto: str, fone: str, chave: str) -> None:
    baixar("https://api.callmebot.com/whatsapp.php?"
           f"phone={quote(fone)}&text={quote(texto)}&apikey={quote(chave)}")
    time.sleep(4)  # o CallMeBot não gosta de rajadas


def enviar(texto: str, sem_envio: bool = False) -> bool:
    """Manda a mensagem em todos os canais configurados (Telegram e/ou WhatsApp).
    Devolve True se chegou em pelo menos um."""
    canais = []
    if os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        canais.append(("Telegram", lambda: _telegram(texto, os.environ["TELEGRAM_TOKEN"],
                                                     os.environ["TELEGRAM_CHAT_ID"])))
    if os.getenv("WHATSAPP_PHONE") and os.getenv("CALLMEBOT_APIKEY"):
        canais.append(("WhatsApp", lambda: _whatsapp(texto, os.environ["WHATSAPP_PHONE"],
                                                     os.environ["CALLMEBOT_APIKEY"])))
    if sem_envio or not canais:
        motivo = "--sem-envio" if sem_envio else "nenhum canal configurado nos secrets"
        print(f"\n----- mensagem (não enviada: {motivo}) -----\n{texto}\n")
        return False
    ok = False
    for nome, mandar in canais:
        try:
            mandar()
            print(f"  → {nome} enviado")
            ok = True
        except Exception as e:
            print(f"  ! falha ao enviar {nome}: {e}")
    return ok


def resumo_actions(ofertas: list[Oferta], erros: list[str], imediatos) -> None:
    caminho = os.getenv("GITHUB_STEP_SUMMARY")
    if not caminho:
        return
    out = ["## Caça-tênis", ""]
    if erros:
        out += ["**Falhas:**", *[f"- {e}" for e in erros], ""]
    out += [f"**Alertas imediatos:** {len(imediatos)}", "",
            "| Alvo | Loja | Produto | Preço | Cheio | No tamanho |", "|---|---|---|---|---|---|"]
    for o in sorted(ofertas, key=lambda o: (o.alvo, not o.tem_tamanho, o.preco)):
        nome = o.produto + (f" ({o.apelido})" if o.apelido else "")
        tam = {True: "✅", False: "—", None: "?"}[o.tem_tamanho]
        out.append(f"| {o.alvo} | {o.loja} | [{nome}]({o.url}) | {brl(o.preco)} | "
                   f"{brl(o.preco_cheio)} | {tam} |")
    with open(caminho, "a", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


# ---------------------------------------------------------------- execução


def carregar_config() -> tuple[dict, list[dict]]:
    cfg = yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))
    alvos = (yaml.safe_load((RAIZ / "alvos.yaml").read_text(encoding="utf-8")) or {}).get("alvos") or []
    return cfg, alvos


def executar(forcar_resumo: bool = False, somente: list[str] | None = None,
             sem_envio: bool = False, titulo: str | None = None) -> int:
    """Uma rodada completa. `somente` restringe a alguns alvos (usado pelo /novo
    do Telegram) — nesse caso o resumo é só desses alvos e não conta como o diário."""
    cfg, alvos = carregar_config()
    if somente:
        chave = lambda s: " ".join(s.lower().split())
        alvos = [a for a in alvos if chave(a["nome"]) in {chave(x) for x in somente}]
    if not alvos:
        print("Nenhum alvo para monitorar.")
        if forcar_resumo:
            enviar("📭 A lista está vazia. Use /novo para adicionar um tênis.", sem_envio)
        return 0

    agora = datetime.now(FUSO)
    estado = carregar_estado()
    ofertas: list[Oferta] = []
    erros: list[str] = []

    for alvo in alvos:
        for nome_loja, loja in cfg["lojas"].items():
            if not loja.get("ativa", True):
                continue
            print(f"[{alvo['nome']}] {nome_loja}...")
            try:
                achadas = COLETORES[loja["tipo"]](nome_loja, loja, alvo, cfg)
                print(f"  {len(achadas)} produto(s), {sum(bool(o.tem_tamanho) for o in achadas)} "
                      f"com tamanho {cfg['tamanho']} confirmado")
                ofertas += achadas
            except Exception as e:
                erros.append(f"{nome_loja} / {alvo['nome']}: {e}")
                print(f"  ! erro: {e}")
            time.sleep(1.5)

    imediatos = decidir(ofertas, estado, cfg, agora, alvos)

    # 1) promoção ótima: avisa na hora
    for o, motivos in imediatos:
        enviar(msg_alerta(o, motivos, cfg), sem_envio)

    # 2) resumo: pedido, de boas-vindas ou o diário
    inicial = not estado.get("iniciado")
    diario = not somente and hora_do_resumo(estado, cfg, agora)
    if forcar_resumo or inicial or diario:
        if titulo is None:
            titulo = ("✅ *Caça-tênis ligado!*" if inicial else
                      "📊 *Resumo do dia — caça-tênis*" if diario else "📋 *Resumo agora*")
        if enviar(msg_resumo(ofertas, alvos, estado, cfg, titulo), sem_envio):
            estado["iniciado"] = True  # só conta como "ligado" se a mensagem chegou
            if diario:  # boas-vindas e /resumo não substituem o resumo do dia
                estado["ultimo_resumo"] = agora.date().isoformat()
                estado["pendentes"] = []

    salvar(estado, ofertas, agora)
    (DADOS / "ultima_execucao.json").write_text(json.dumps({
        "data": agora.isoformat(timespec="minutes"),
        "ofertas": len(ofertas),
        "por_loja": {l: sum(1 for o in ofertas if o.loja == l)
                     for l in sorted({o.loja for o in ofertas} | set(cfg["lojas"]))},
        "imediatos": len(imediatos),
        "pendentes_para_resumo": len(estado["pendentes"]),
        "erros": erros,
    }, ensure_ascii=False, indent=2))
    resumo_actions(ofertas, erros, imediatos)
    print(f"\nFim: {len(ofertas)} ofertas lidas, {len(imediatos)} alerta(s) imediato(s), "
          f"{len(erros)} erro(s).")
    # Falha o job só se NENHUMA loja respondeu (assim o GitHub te avisa por e-mail).
    return 1 if erros and not ofertas else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resumo", action="store_true", help="manda o resumo agora")
    ap.add_argument("--alvo", action="append", help="roda só para este alvo (pode repetir)")
    ap.add_argument("--sem-envio", action="store_true", help="não manda mensagem, só imprime")
    args = ap.parse_args()
    return executar(forcar_resumo=args.resumo, somente=args.alvo, sem_envio=args.sem_envio)


if __name__ == "__main__":
    sys.exit(main())
