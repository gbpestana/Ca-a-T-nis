#!/usr/bin/env python3
"""
Testa, a partir de onde está rodando (ex.: GitHub Actions), quais lojas respondem:
  - lojas VTEX: API pública de catálogo
  - Promobit: página de ofertas da loja
Resultado em dados/diagnostico.json. Rode pelo workflow "Diagnóstico de lojas".

  python diagnostico.py vtex www.vans.com.br www.fila.com.br
  python diagnostico.py promobit centauro netshoes
  python diagnostico.py            # usa a lista padrão abaixo
"""
import json
import sys
from urllib.parse import quote

import monitor

VTEX = [
    "www.vans.com.br", "www.newbalance.com.br", "www.fila.com.br", "br.puma.com",
    "www.centauro.com.br", "www.netshoes.com.br", "www.dafiti.com.br", "www.zattini.com.br",
    "www.adidas.com.br", "www.asics.com.br", "www.mizuno.com.br", "www.olympikus.com.br",
    "www.converse.com.br", "www.ostore.com.br", "www.overcome.com.br", "www.gdlp.com.br",
    "www.maze.com.br", "www.lojavirus.com.br",
]
PROMOBIT = [
    "centauro", "netshoes", "dafiti", "zattini", "puma", "adidas", "new-balance",
    "newbalance", "vans", "fila", "asics", "mizuno", "olympikus", "artwalk", "authentic-feet",
]


def testar_vtex(dom: str) -> dict:
    try:
        r = monitor.baixar(f"https://{dom}/api/catalog_system/pub/products/search?ft={quote('tenis')}"
                           "&_from=0&_to=4", json_=True, tentativas=1)
        if isinstance(r, list) and r and "productName" in r[0]:
            com_tam = any(i.get("Tamanho") for p in r for i in p.get("items", []))
            return {"ok": True, "exemplo": r[0]["productName"], "tem_campo_tamanho": com_tam}
        return {"ok": False, "erro": f"resposta inesperada: {str(r)[:80]}"}
    except Exception as e:
        return {"ok": False, "erro": str(e)[-120:]}


def testar_promobit(slug: str) -> dict:
    try:
        d = monitor.next_data(monitor.baixar(f"https://www.promobit.com.br/cupons/loja/{slug}/",
                                             tentativas=1))
        pp = d["props"]["pageProps"]
        ofs = (pp.get("serverOffers") or {}).get("offers") or []
        lojas = sorted({o.get("storeName") for o in ofs if o.get("storeName")})
        return {"ok": bool(ofs), "ofertas": len(ofs), "lojas": lojas[:3],
                "cupons": len((pp.get("serverCoupons") or {}).get("coupons") or [])}
    except Exception as e:
        return {"ok": False, "erro": str(e)[-120:]}


def main():
    args = sys.argv[1:]
    vtex = PROMOBIT_ = None
    if args and args[0] in ("vtex", "promobit"):
        vtex = args[1:] if args[0] == "vtex" else []
        PROMOBIT_ = args[1:] if args[0] == "promobit" else []
    vtex = VTEX if vtex is None else vtex
    promo = PROMOBIT if PROMOBIT_ is None else PROMOBIT_
    res = {"vtex": {}, "promobit": {}}
    for d in vtex:
        res["vtex"][d] = testar_vtex(d)
        print("vtex", d, res["vtex"][d])
    for s in promo:
        res["promobit"][s] = testar_promobit(s)
        print("promobit", s, res["promobit"][s])
    monitor.DADOS.mkdir(exist_ok=True)
    (monitor.DADOS / "diagnostico.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
