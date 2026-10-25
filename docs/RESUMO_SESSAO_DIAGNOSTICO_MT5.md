# Sessão de Diagnóstico MT5 (BTG) — Resumo Sinótico

Data: 2026-10-25 · Branch: `claude/mt5-api-diagnostico-wr8skf` · Commit: `bcf4991`

## 1. Objetivo
Determinar o que o BTG entrega de fato via API Python do MT5 para WIN e WDO: profundidade e frequência do book, flags de agressor nos ticks, latência, volume real e dados de sessão/contrato.

## 2. Estado atual

| Item | Status |
|---|---|
| Leitura de `docs/SESSOES.md` (ABERTURA) e `docs/PROBLEMAS_CONHECIDOS.md` | **Não realizada**: os arquivos não existem no repositório (só `.gitkeep`, em todas as branches) |
| Script `diagnostico_mt5.py` | **Criado e publicado** na branch |
| Teste do script | Apenas com módulo MT5 simulado (Linux); lógica, JSON e resumo validados |
| Execução com MT5/BTG real | **Pendente** (requer Windows, MT5 aberto e logado, pregão aberto) |
| `results/diagnostico_mt5.json` | **Não existe ainda**: é gerado na primeira execução real |
| Dados reais do BTG | **Nenhum até o momento** |

## 3. O que o script mede (WIN e WDO)
1. **Contrato ativo**: vencimento mais próximo ainda não expirado; lista os candidatos encontrados.
2. **Níveis de book**: `market_book_get()`, níveis de compra, venda e total (mín/mediana/máx) e o book mais profundo visto.
3. **Frequência do book**: polling por N segundos (padrão 30), mudanças/s e intervalo entre mudanças (média, mediana, p95).
4. **Flags de agressor**: `TICK_FLAG_BUY/SELL` (e BID/ASK/LAST/VOLUME) nos ticks dos últimos 30 min e nos ticks ao vivo.
5. **Latência**: `time_msc` do tick vs `datetime.now()`, bruta e corrigida pelo fuso estimado.
6. **Volume real**: `volume_real` nos ticks e `real_volume` nas barras M1, comparado ao `tick_volume`.
7. **`symbol_info()`**: dump completo (vencimento, path, trade_mode, session_deals, session_volume, tick size etc.).

Saída: `results/diagnostico_mt5.json` + resumo no terminal com ✔ ENTREGA / ✘ NÃO-FRACO por ativo.

## 4. Como executar
```
pip install MetaTrader5
python diagnostico_mt5.py            # opções: --segundos N, --saida CAMINHO
```

## 5. Limitações metodológicas
- `market_book_get()` é um snapshot por polling: a frequência medida é de mudanças observadas, não a taxa real do feed.
- A latência é medida por polling (~1 ms de resolução). Depende do relógio do PC estar sincronizado, e o fuso do servidor é estimado em horas inteiras.
- A API Python não expõe os horários da sessão de negociação, só vencimento e campos `session_*`.
- Fora do pregão, book e ticks vêm vazios ou congelados e serão classificados como "não entrega".
- Critérios do veredito (ajustáveis no código): book ≥ 10 níveis; ≥ 5 mudanças/s; BUY+SELL > 0; `volume_real` > 0; latência mediana < 500 ms.

## 6. Próximos passos
1. Rodar `diagnostico_mt5.py` no Windows, com pregão aberto.
2. Enviar `results/diagnostico_mt5.json` (e este resumo) ao Claude.
3. Comparar o resultado com `PROBLEMAS_CONHECIDOS.md` quando esse arquivo estiver disponível e consolidar o quadro "entrega vs não entrega".
