#!/usr/bin/env python3
"""Diagnóstico do que o BTG entrega de verdade via API Python do MT5.

Rodar no Windows, com o MT5 (BTG) aberto e logado, de preferência com o
pregão aberto:

    pip install MetaTrader5
    python diagnostico_mt5.py [--segundos 30] [--saida results/diagnostico_mt5.json]

Mede, para WIN e WDO (contrato ativo):
  1. níveis de book em market_book_get()
  2. frequência de atualização do book (polling por N segundos)
  3. flags TICK_FLAG_BUY / TICK_FLAG_SELL nos ticks
  4. latência time_msc do tick vs datetime.now() do Python
  5. real_volume / volume_real preenchido ou zerado
  6. symbol_info(): sessão, contrato, vencimento

Grava tudo em results/diagnostico_mt5.json e imprime um resumo
"entrega vs não entrega".
"""
import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    import MetaTrader5 as mt5
except ImportError:
    sys.exit("Pacote MetaTrader5 não encontrado. Instale com: pip install MetaTrader5 (Windows apenas).")

ATIVOS = ("WIN", "WDO")
MESES_B3 = "FGHJKMNQUVXZ"
SAIDA_PADRAO = Path(__file__).resolve().parent / "results" / "diagnostico_mt5.json"

# Flags de tick (valores fixos da API do MT5)
FLAGS = {
    "BID": 2,
    "ASK": 4,
    "LAST": 8,
    "VOLUME": 16,
    "BUY": 32,
    "SELL": 64,
}


# ----------------------------------------------------------------- utilidades
def jsonable(obj):
    """Converte recursivamente para algo serializável em JSON."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "item"):  # numpy scalar
        return obj.item()
    if isinstance(obj, float) and obj != obj:
        return None
    return obj


def nt_dict(nt):
    return jsonable(nt._asdict()) if nt is not None else None


def erro_mt5():
    code, msg = mt5.last_error()
    return {"codigo": code, "mensagem": msg}


def stats(valores):
    if not valores:
        return None
    v = sorted(valores)
    return {
        "n": len(v),
        "min": v[0],
        "media": statistics.fmean(v),
        "mediana": statistics.median(v),
        "p95": v[min(len(v) - 1, int(len(v) * 0.95))],
        "max": v[-1],
    }


# ------------------------------------------------------- resolução do contrato
def resolver_contrato(base):
    """Acha o contrato ativo de WIN/WDO: o vigente de menor vencimento ainda
    não expirado. Reporta todos os candidatos vistos."""
    padrao = re.compile(rf"^{base}[{MESES_B3}]\d{{2}}$")
    candidatos = []
    todos = mt5.symbols_get(group=f"{base}*") or []
    for s in todos:
        if padrao.match(s.name) or s.name in (f"{base}$N", f"{base}$", f"{base}FUT", f"{base}@N"):
            candidatos.append(s)

    agora = datetime.now()
    vigentes = []
    for s in candidatos:
        exp = datetime.fromtimestamp(s.expiration_time) if s.expiration_time else None
        if exp is None or exp >= agora - timedelta(days=1):
            vigentes.append((exp or datetime.max, s))
    vigentes.sort(key=lambda t: t[0])

    escolhido = None
    # Preferência: contrato com mês/ano (vencimento real) e menor vencimento.
    for _, s in vigentes:
        if padrao.match(s.name):
            escolhido = s.name
            break
    if escolhido is None and vigentes:
        escolhido = vigentes[0][1].name
    return {
        "escolhido": escolhido,
        "candidatos": [
            {
                "nome": s.name,
                "vencimento": datetime.fromtimestamp(s.expiration_time).isoformat() if s.expiration_time else None,
                "visivel": bool(s.visible),
                "path": s.path,
            }
            for s in candidatos
        ],
    }


# ---------------------------------------------------------------- symbol_info
def coletar_symbol_info(nome):
    info = mt5.symbol_info(nome)
    if info is None:
        return {"erro": erro_mt5()}
    d = nt_dict(info)
    # Campos de timestamp inteiro -> ISO legível (hora do servidor)
    for k in ("time", "start_time", "expiration_time"):
        if d.get(k):
            d[k + "_legivel"] = datetime.fromtimestamp(d[k]).isoformat()
    return d


# ----------------------------------------------------------------------- ticks
def analisar_ticks(ticks):
    if ticks is None or len(ticks) == 0:
        return {"n": 0}
    n = len(ticks)
    flags = ticks["flags"]
    contagem = {nome: int(((flags & bit) != 0).sum()) for nome, bit in FLAGS.items()}
    vol = ticks["volume"]
    vol_real = ticks["volume_real"] if "volume_real" in ticks.dtype.names else None
    ult = ticks["last"]
    return {
        "n": n,
        "primeiro": datetime.fromtimestamp(ticks["time_msc"][0] / 1000).isoformat(),
        "ultimo": datetime.fromtimestamp(ticks["time_msc"][-1] / 1000).isoformat(),
        "contagem_flags": contagem,
        "pct_flags": {k: round(100 * v / n, 2) for k, v in contagem.items()},
        "ticks_de_negocio_com_last": int((ult > 0).sum()),
        "ticks_com_buy_ou_sell": int((((flags & FLAGS["BUY"]) != 0) | ((flags & FLAGS["SELL"]) != 0)).sum()),
        "ticks_com_buy_e_sell": int((((flags & FLAGS["BUY"]) != 0) & ((flags & FLAGS["SELL"]) != 0)).sum()),
        "volume": {"nao_zero": int((vol > 0).sum()), "soma": int(vol.sum())},
        "volume_real": None if vol_real is None else {
            "nao_zero": int((vol_real > 0).sum()),
            "soma": float(vol_real.sum()),
        },
    }


def coletar_ticks_historicos(nome, tick_ref, minutos=30, max_ticks=200000):
    """Pega os ticks recentes ancorados no horário do último tick (hora do
    servidor), evitando problema de fuso entre PC e servidor."""
    if tick_ref is None:
        return {"n": 0, "erro": "sem tick de referência"}
    fim = datetime.fromtimestamp(tick_ref.time)
    ini = fim - timedelta(minutes=minutos)
    ticks = mt5.copy_ticks_range(nome, ini, fim + timedelta(seconds=1), mt5.COPY_TICKS_ALL)
    if ticks is None:
        return {"n": 0, "erro": erro_mt5()}
    if len(ticks) > max_ticks:
        ticks = ticks[-max_ticks:]
    res = analisar_ticks(ticks)
    res["janela_minutos"] = minutos
    # Amostra crua para inspeção manual
    amostra = []
    for t in ticks[-10:]:
        amostra.append({
            "time_msc": int(t["time_msc"]),
            "bid": float(t["bid"]), "ask": float(t["ask"]), "last": float(t["last"]),
            "volume": int(t["volume"]),
            "volume_real": float(t["volume_real"]) if "volume_real" in ticks.dtype.names else None,
            "flags": int(t["flags"]),
        })
    res["amostra_ultimos_10"] = amostra

    # Trades (só com last) isolados: o que interessa para agressão
    trades = mt5.copy_ticks_range(nome, ini, fim + timedelta(seconds=1), mt5.COPY_TICKS_TRADE)
    if trades is not None:
        res["ticks_trade"] = analisar_ticks(trades)
    return res


def coletar_rates(nome, tick_ref, n=60):
    """real_volume nas barras M1 recentes."""
    r = mt5.copy_rates_from(nome, mt5.TIMEFRAME_M1, datetime.fromtimestamp(tick_ref.time) if tick_ref else datetime.now(), n)
    if r is None or len(r) == 0:
        return {"n": 0, "erro": erro_mt5()}
    return {
        "n": len(r),
        "tick_volume_soma": int(r["tick_volume"].sum()),
        "real_volume_soma": int(r["real_volume"].sum()),
        "barras_com_real_volume": int((r["real_volume"] > 0).sum()),
        "ultima_barra": {k: (int(r[-1][k]) if k in ("time", "tick_volume", "spread", "real_volume") else float(r[-1][k]))
                         for k in r.dtype.names},
    }


# ------------------------------------------------------- amostragem ao vivo
class Amostra:
    def __init__(self, nome):
        self.nome = nome
        self.book_ok = False
        self.book_erro = None
        self.polls_book = 0
        self.book_vazio = 0
        self.ultimo_book = None
        self.t_mudancas = []          # perf_counter de cada mudança do book
        self.niveis_buy = []
        self.niveis_sell = []
        self.niveis_total = []
        self.book_exemplo = None
        self.tipos_vistos = set()
        self.volume_dbl_diferente = 0
        self.ultimo_tick_key = None
        self.ticks_vivos = 0
        self.flags_vivos = {k: 0 for k in FLAGS}
        self.delta_s = []             # now - time_msc, em segundos (bruto, inclui fuso)
        self.vol_real_nao_zero = 0
        self.tem_flags_no_tick = None

    def poll_book(self):
        book = mt5.market_book_get(self.nome)
        self.polls_book += 1
        if not book:
            self.book_vazio += 1
            return
        chave = tuple((b.type, b.price, b.volume) for b in book)
        buy = sum(1 for b in book if b.type in (mt5.BOOK_TYPE_BUY, mt5.BOOK_TYPE_BUY_MARKET))
        sell = sum(1 for b in book if b.type in (mt5.BOOK_TYPE_SELL, mt5.BOOK_TYPE_SELL_MARKET))
        for b in book:
            self.tipos_vistos.add(int(b.type))
            vd = getattr(b, "volume_dbl", None)
            if vd is not None and vd != b.volume:
                self.volume_dbl_diferente += 1
        if chave != self.ultimo_book:
            self.t_mudancas.append(time.perf_counter())
            self.ultimo_book = chave
            self.niveis_buy.append(buy)
            self.niveis_sell.append(sell)
            self.niveis_total.append(len(book))
            if self.book_exemplo is None or len(book) > len(self.book_exemplo):
                self.book_exemplo = [
                    {"tipo": int(b.type), "preco": b.price, "volume": int(b.volume),
                     "volume_dbl": getattr(b, "volume_dbl", None)}
                    for b in book
                ]

    def poll_tick(self):
        t = mt5.symbol_info_tick(self.nome)
        if t is None:
            return
        chave = (t.time_msc, t.bid, t.ask, t.last, t.volume)
        if chave == self.ultimo_tick_key:
            return
        self.ultimo_tick_key = chave
        agora = datetime.now()
        self.ticks_vivos += 1
        self.delta_s.append(agora.timestamp() - t.time_msc / 1000.0)
        flags = getattr(t, "flags", None)
        if flags is not None:
            self.tem_flags_no_tick = True
            for k, bit in FLAGS.items():
                if flags & bit:
                    self.flags_vivos[k] += 1
        vr = getattr(t, "volume_real", 0)
        if vr and vr > 0:
            self.vol_real_nao_zero += 1

    def resultado_book(self, duracao):
        tm = self.t_mudancas
        intervalos_ms = [(b - a) * 1000 for a, b in zip(tm, tm[1:])]
        return {
            "book_subscrito": self.book_ok,
            "erro_subscricao": self.book_erro,
            "polls": self.polls_book,
            "polls_por_segundo": round(self.polls_book / duracao, 1),
            "polls_book_vazio": self.book_vazio,
            "mudancas_de_book": len(tm),
            "mudancas_por_segundo": round(len(tm) / duracao, 2),
            "intervalo_entre_mudancas_ms": stats(intervalos_ms),
            "niveis_compra": stats(self.niveis_buy),
            "niveis_venda": stats(self.niveis_sell),
            "niveis_total": stats(self.niveis_total),
            "tipos_de_ordem_vistos": sorted(self.tipos_vistos),
            "book_mais_profundo_visto": self.book_exemplo,
        }

    def resultado_tick_vivo(self):
        delta = self.delta_s
        # Fuso: o servidor costuma reportar "hora local do servidor" como se
        # fosse UTC. Estimamos o offset em horas inteiras pela mediana.
        offset_h = None
        residual = None
        if delta:
            med = statistics.median(delta)
            offset_h = round(med / 3600)
            residual = [(d - offset_h * 3600) * 1000 for d in delta]
        return {
            "ticks_vivos_distintos": self.ticks_vivos,
            "flags_nos_ticks_vivos": self.flags_vivos,
            "symbol_info_tick_expoe_flags": bool(self.tem_flags_no_tick),
            "ticks_com_volume_real": self.vol_real_nao_zero,
            "latencia_bruta_s": stats(delta),
            "offset_fuso_estimado_h": offset_h,
            "latencia_ms_apos_corrigir_fuso": stats(residual) if residual else None,
            "obs": "Latência medida por polling: inclui até 1 ciclo do loop (~1-2 ms). "
                   "O offset de fuso é estimado pela mediana arredondada a horas inteiras; "
                   "se o relógio do PC estiver dessincronizado, o valor corrigido também estará.",
        }


def amostrar(nomes, segundos):
    amostras = {n: Amostra(n) for n in nomes}
    for n, a in amostras.items():
        if not mt5.symbol_select(n, True):
            a.book_erro = {"etapa": "symbol_select", **erro_mt5()}
            continue
        if mt5.market_book_add(n):
            a.book_ok = True
        else:
            a.book_erro = {"etapa": "market_book_add", **erro_mt5()}
    time.sleep(1.0)  # dá tempo do terminal assinar o book

    ativos = [a for a in amostras.values() if a.book_ok]
    ini = time.perf_counter()
    fim = ini + segundos
    ultimo_print = ini
    try:
        while time.perf_counter() < fim:
            for a in amostras.values():
                if a.book_ok:
                    a.poll_book()
                a.poll_tick()
            time.sleep(0.001)
            agora = time.perf_counter()
            if agora - ultimo_print >= 5:
                ultimo_print = agora
                msg = " | ".join(
                    f"{a.nome}: {len(a.t_mudancas)} mud. book, {a.ticks_vivos} ticks" for a in amostras.values()
                )
                print(f"  [{int(agora - ini):>2}s/{segundos}s] {msg}")
    finally:
        duracao = time.perf_counter() - ini
        for a in ativos:
            mt5.market_book_release(a.nome)
    return amostras, duracao


# ------------------------------------------------------------------- resumo
def montar_veredito(res):
    """Gera lista de (ok, texto) a partir dos resultados."""
    linhas = []
    for ativo, d in res["ativos"].items():
        nome = d["simbolo"]
        if not nome:
            linhas.append((False, f"{ativo}: contrato ativo não encontrado no terminal"))
            continue
        b = d["book"]
        if not b["book_subscrito"]:
            linhas.append((False, f"{nome}: market_book_add falhou ({b['erro_subscricao']})"))
        else:
            tot = b["niveis_total"]
            if not tot:
                linhas.append((False, f"{nome}: book assinado mas vazio (mercado fechado ou BTG não entrega book)"))
            else:
                linhas.append((tot["max"] >= 10, f"{nome}: book com no máx. {tot['max']:.0f} níveis totais "
                               f"(compra máx {b['niveis_compra']['max']:.0f} / venda máx {b['niveis_venda']['max']:.0f}), "
                               f"mediana {tot['mediana']:.0f}"))
            linhas.append((b["mudancas_por_segundo"] >= 5,
                           f"{nome}: book muda {b['mudancas_por_segundo']}x/s via polling "
                           f"({b['polls_por_segundo']} polls/s; é snapshot, não stream de eventos)"))

        t = d["ticks_historicos"]
        if t.get("n"):
            fl = t["contagem_flags"]
            tem_agressao = fl["BUY"] + fl["SELL"] > 0
            linhas.append((tem_agressao, f"{nome}: flags BUY/SELL nos ticks → BUY={fl['BUY']} SELL={fl['SELL']} "
                           f"de {t['n']} ticks ({t['ticks_com_buy_ou_sell']} com agressor)"))
            vr = t.get("volume_real")
            if vr is not None:
                linhas.append((vr["nao_zero"] > 0, f"{nome}: volume_real nos ticks não-zero em {vr['nao_zero']}/{t['n']}"))
        else:
            linhas.append((False, f"{nome}: sem ticks históricos recentes ({t.get('erro')})"))

        r = d["rates_m1"]
        if r.get("n"):
            linhas.append((r["real_volume_soma"] > 0,
                           f"{nome}: real_volume M1 = {r['real_volume_soma']} (tick_volume = {r['tick_volume_soma']})"))

        v = d["tick_vivo"]
        lat = v.get("latencia_ms_apos_corrigir_fuso")
        if lat:
            linhas.append((lat["mediana"] < 500,
                           f"{nome}: latência tick→Python mediana {lat['mediana']:.0f} ms, p95 {lat['p95']:.0f} ms "
                           f"(fuso estimado {v['offset_fuso_estimado_h']:+d}h)"))
        else:
            linhas.append((False, f"{nome}: nenhum tick novo durante a janela — latência não medida"))
    return linhas


def imprimir_resumo(res):
    print("\n" + "=" * 70)
    print("RESUMO — o que o MT5/BTG entrega de verdade")
    print("=" * 70)
    for ok, txt in res["veredito"]:
        print(f"  {'✔ ENTREGA ' if ok else '✘ NÃO/FRACO'}  {txt}")
    print("\nSessão / contrato (symbol_info):")
    for ativo, d in res["ativos"].items():
        si = d.get("symbol_info") or {}
        if si and "erro" not in si:
            print(f"  {d['simbolo']}: path={si.get('path')} | vencimento={si.get('expiration_time_legivel')} | "
                  f"trade_mode={si.get('trade_mode')} | session_deals={si.get('session_deals')} | "
                  f"session_volume={si.get('session_volume')} | tick_size={si.get('trade_tick_size')}")
    print(f"\nJSON completo: {res['_arquivo']}")


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--segundos", type=int, default=30, help="janela de amostragem ao vivo (padrão 30)")
    ap.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    ap.add_argument("--minutos-ticks", type=int, default=30, help="janela de ticks históricos (padrão 30)")
    args = ap.parse_args()

    if not mt5.initialize():
        sys.exit(f"mt5.initialize() falhou: {mt5.last_error()}. O MT5 está aberto e logado?")

    try:
        res = {
            "gerado_em": datetime.now().isoformat(),
            "versao_python_mt5": getattr(mt5, "__version__", None),
            "terminal": nt_dict(mt5.terminal_info()),
            "servidor": (nt_dict(mt5.account_info()) or {}).get("server"),
            "janela_amostragem_s": args.segundos,
            "ativos": {},
        }
        # Não grava login/nome da conta: só o servidor acima.

        nomes = {}
        for base in ATIVOS:
            c = resolver_contrato(base)
            res["ativos"][base] = {"simbolo": c["escolhido"], "resolucao_contrato": c}
            if c["escolhido"]:
                nomes[base] = c["escolhido"]
            print(f"{base}: contrato ativo = {c['escolhido']} (candidatos: {[x['nome'] for x in c['candidatos']]})")
        if not nomes:
            sys.exit("Nenhum contrato WIN/WDO encontrado no Market Watch/servidor.")

        print(f"\nAmostrando book e ticks ao vivo por {args.segundos}s...")
        amostras, duracao = amostrar(list(nomes.values()), args.segundos)

        for base, nome in nomes.items():
            a = amostras[nome]
            tick_ref = mt5.symbol_info_tick(nome)
            d = res["ativos"][base]
            d["symbol_info"] = coletar_symbol_info(nome)
            d["ultimo_tick"] = nt_dict(tick_ref)
            d["book"] = a.resultado_book(duracao)
            d["tick_vivo"] = a.resultado_tick_vivo()
            d["ticks_historicos"] = coletar_ticks_historicos(nome, tick_ref, args.minutos_ticks)
            d["rates_m1"] = coletar_rates(nome, tick_ref)
        for base in ATIVOS:
            d = res["ativos"][base]
            d.setdefault("book", {"book_subscrito": False, "erro_subscricao": "contrato não encontrado"})

        res["veredito"] = montar_veredito(res)
        res["avisos"] = [
            "market_book_get() é snapshot por polling: a 'frequência' medida é de mudanças observadas, limitada pelo polling.",
            "A API Python do MT5 não expõe sessões de negociação (horários) — só expiration_time, session_* e trade_mode em symbol_info().",
            "Rodar com pregão aberto; fora do horário book/ticks vêm vazios ou congelados.",
        ]

        args.saida.parent.mkdir(parents=True, exist_ok=True)
        res["_arquivo"] = str(args.saida)
        args.saida.write_text(json.dumps(jsonable(res), ensure_ascii=False, indent=2), encoding="utf-8")
        imprimir_resumo(res)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
