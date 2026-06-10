#!/usr/bin/env node
type Universe = "etf" | "stock" | "all";
import fs from "node:fs/promises";
import path from "node:path";

type SymbolRow = {
  code: string;
  name: string;
  price: number;
  amount: number;
  assetType: "ETF" | "A股";
};

type Kline = {
  date: string;
  close: number;
  volume: number;
};

type ScanRow = {
  rank?: number;
  type: string;
  code: string;
  name: string;
  price: number;
  candidateScore: number;
  continuationScore: number;
  trendGrade: string;
  tradeSuggestion: string;
  sellSuggestion: string;
  actionNote: string;
  riskNote: string;
  ret5: number;
  ret10: number;
  ret20: number;
  upDays5: number;
  upDays10: number;
  consecutiveUpDays: number;
  ma20Slope5: number;
  drawdown20: number;
  rsi: number;
  volRatio: number;
};

const UNIVERSE_LABEL: Record<Universe, string> = {
  etf: "ETF",
  stock: "A股",
  all: "ETF + A股",
};
const DEFENSIVE_ETF_KEYWORDS = ["货币", "现金", "添益", "日利", "收益", "短债", "中短债", "信用债", "国债", "政金债", "城投债", "可转债"];

function parseArgs(argv: string[]) {
  const args = new Map<string, string | boolean>();
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (!item.startsWith("--")) continue;
    const key = item.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args.set(key, true);
    } else {
      args.set(key, next);
      i += 1;
    }
  }
  return {
    universe: String(args.get("universe") || "etf") as Universe,
    topN: Number(args.get("top-n") || 30),
    limit: Number(args.get("limit") || 20),
    workers: Number(args.get("workers") || 6),
    mode: String(args.get("mode") || "balanced"),
    includeDefensive: Boolean(args.get("include-defensive")),
  };
}

function secid(code: string): string {
  return code.startsWith("5") || code.startsWith("6") ? `1.${code}` : `0.${code}`;
}

async function fetchJson(url: string): Promise<any> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const response = await fetch(url, {
        headers: {
          Referer: "https://quote.eastmoney.com/",
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
          Accept: "application/json,text/plain,*/*",
        },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, 300 * (attempt + 1)));
    }
  }
  throw lastError;
}

async function fetchList(universe: "etf" | "stock"): Promise<SymbolRow[]> {
  const fs =
    universe === "etf"
      ? "b:MK0021,b:MK0022,b:MK0023,b:MK0024"
      : "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23";
  const params = new URLSearchParams({
    pn: "1",
    pz: "10000",
    po: "1",
    np: "1",
    ut: "bd1d9ddb04089700cf9c27f6f7426281",
    fltt: "2",
    invt: "2",
    fid: "f6",
    fs,
    fields: "f12,f14,f2,f3,f5,f6,f18,f20,f21",
  });
  const payload = await fetchJson(`https://push2.eastmoney.com/api/qt/clist/get?${params}`);
  const rows = payload?.data?.diff || [];
  const assetType = universe === "etf" ? "ETF" : "A股";
  return rows
    .map((row: any) => ({
      code: String(row.f12 || "").trim(),
      name: String(row.f14 || "").trim(),
      price: Number(row.f2),
      amount: Number(row.f6),
      assetType,
    }))
    .filter((row: SymbolRow) => row.code && row.name && Number.isFinite(row.price) && Number.isFinite(row.amount))
    .filter((row: SymbolRow) => universe === "etf" || /^(00|30|60|68)\d{4}$/.test(row.code));
}

async function fetchUniverse(universe: Universe, includeDefensive = false): Promise<SymbolRow[]> {
  let rows: SymbolRow[];
  try {
    if (universe === "all") {
      const [etfs, stocks] = await Promise.all([fetchList("etf"), fetchList("stock")]);
      rows = [...etfs, ...stocks];
    } else {
      rows = await fetchList(universe);
    }
  } catch {
    rows = await cachedUniverse(universe);
  }
  return rows.filter((row) => {
    if (row.assetType === "A股" && /ST|退/i.test(row.name)) return false;
    if (row.assetType === "ETF" && !includeDefensive && DEFENSIVE_ETF_KEYWORDS.some((word) => row.name.includes(word))) return false;
    return true;
  });
}

async function cachedUniverse(universe: Universe): Promise<SymbolRow[]> {
  const cacheDir = path.join(process.cwd(), "data", "cache", "generic");
  let names: string[] = [];
  try {
    names = await fs.readdir(cacheDir);
  } catch {
    return [];
  }
  const rows: SymbolRow[] = [];
  for (const name of names) {
    const isStock = name.startsWith("stock_scanner_v");
    const isEtf = name.startsWith("scanner_v") && !name.includes("summary") && !name.includes("universe");
    if (universe === "stock" && !isStock) continue;
    if (universe === "etf" && !isEtf) continue;
    if (universe === "all" && !isStock && !isEtf) continue;
    try {
      const item = JSON.parse(await fs.readFile(path.join(cacheDir, name), "utf-8"));
      if (!item.code || !item.name) continue;
      rows.push({
        code: String(item.code),
        name: String(item.name),
        price: Number(item.price || 0),
        amount: Number(item.amount || 0),
        assetType: isStock ? "A股" : "ETF",
      });
    } catch {
      // Ignore broken cache files.
    }
  }
  return rows;
}

async function fetchKlines(code: string): Promise<Kline[]> {
  const end = new Date();
  const start = new Date(end.getTime() - 160 * 24 * 60 * 60 * 1000);
  const ymd = (d: Date) =>
    `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  const params = new URLSearchParams({
    secid: secid(code),
    fields1: "f1,f2,f3,f4,f5,f6",
    fields2: "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    klt: "101",
    fqt: "1",
    beg: ymd(start),
    end: ymd(end),
    lmt: "100000",
  });
  const payload = await fetchJson(`https://push2his.eastmoney.com/api/qt/stock/kline/get?${params}`);
  const rows: string[] = payload?.data?.klines || [];
  return rows
    .map((line) => {
      const parts = String(line).split(",");
      return { date: parts[0], close: Number(parts[2]), volume: Number(parts[5]) };
    })
    .filter((row) => row.date && Number.isFinite(row.close) && Number.isFinite(row.volume));
}

function avg(values: number[]): number {
  const clean = values.filter(Number.isFinite);
  return clean.length ? clean.reduce((sum, value) => sum + value, 0) / clean.length : 0;
}

function compute(row: SymbolRow, klines: Kline[], mode: string): ScanRow | null {
  if (klines.length < 25) return null;
  const close = klines.map((k) => k.close);
  const volume = klines.map((k) => k.volume);
  const last = close.at(-1)!;
  const ret = (days: number) => (close.length > days ? (last / close[close.length - 1 - days] - 1) * 100 : 0);
  const pct = close.map((value, index) => (index === 0 ? 0 : (value / close[index - 1] - 1) * 100));
  const ma = (window: number, offset = 0) => avg(close.slice(close.length - window - offset, close.length - offset));
  const ma20 = ma(20);
  const ma60 = close.length >= 60 ? ma(60) : ma20;
  const ma20Prev = ma(20, 5);
  const ma20Slope5 = ma20Prev > 0 ? (ma20 / ma20Prev - 1) * 100 : 0;
  const trendScore = [last > ma20, last > ma60, ma20 > ma60, ma20Slope5 > 0].filter(Boolean).length;
  const upDays5 = pct.slice(-5).filter((v) => v > 0).length;
  const upDays10 = pct.slice(-10).filter((v) => v > 0).length;
  let consecutiveUpDays = 0;
  for (let i = pct.length - 1; i >= 1 && pct[i] > 0; i -= 1) consecutiveUpDays += 1;
  const high20 = Math.max(...close.slice(-20));
  const drawdown20 = high20 > 0 ? (last / high20 - 1) * 100 : 0;
  const deltas = close.slice(1).map((value, index) => value - close[index]);
  const recent = deltas.slice(-14);
  const gain = avg(recent.map((v) => Math.max(v, 0)));
  const loss = avg(recent.map((v) => Math.max(-v, 0))) || 1e-10;
  const rsi = 100 - 100 / (1 + gain / loss);
  const volRatio = avg(volume.slice(-5)) / (avg(volume.slice(-20)) || 1);
  const volatility = std(close.slice(-20).map((value, index, arr) => (index === 0 ? 0 : value / arr[index - 1] - 1))) * 100;
  const factors = { ret5: ret(5), ret10: ret(10), ret20: ret(20), trendScore, upDays5, upDays10, consecutiveUpDays, drawdown20, rsi, volRatio, volatility, volumeConfirm: 0 };
  const score = continuationScore(factors);
  const candidate = candidateScore(score, factors, row.amount, row.assetType, mode);
  return {
    type: row.assetType,
    code: row.code,
    name: row.name,
    price: row.price,
    candidateScore: candidate,
    continuationScore: score,
    trendGrade: trendGrade(candidate),
    tradeSuggestion: tradeSuggestion({ ...factors, candidateScore: candidate, continuationScore: score }, row.assetType),
    sellSuggestion: sellSuggestion({ ...factors, candidateScore: candidate, continuationScore: score }, row.assetType),
    actionNote: actionNote(candidate, drawdown20, rsi),
    riskNote: riskNote(factors, row.amount, row.assetType),
    ret5: ret(5),
    ret10: ret(10),
    ret20: ret(20),
    upDays5,
    upDays10,
    consecutiveUpDays,
    ma20Slope5,
    drawdown20,
    rsi,
    volRatio,
  };
}

function std(values: number[]): number {
  const clean = values.filter(Number.isFinite);
  if (!clean.length) return 0;
  const mean = avg(clean);
  return Math.sqrt(avg(clean.map((value) => (value - mean) ** 2)));
}

function continuationScore(f: Record<string, number>): number {
  let score = 0;
  score += (f.trendScore / 4) * 25;
  score += Math.min(f.upDays5 / 4, 1) * 10;
  score += Math.min(f.upDays10 / 7, 1) * 10;
  score += Math.min(f.consecutiveUpDays / 4, 1) * 8;
  score += Math.min(Math.max(f.ret5 / 5, 0), 1) * 8;
  score += Math.min(Math.max(f.ret10 / 8, 0), 1) * 8;
  score += Math.min(Math.max(f.ret20 / 12, 0), 1) * 7;
  if (f.drawdown20 >= -6 && f.drawdown20 <= -1) score += 8;
  else if (f.drawdown20 > -1 && f.drawdown20 <= 0) score += 5;
  else if (f.drawdown20 >= -10 && f.drawdown20 < -6) score += 3;
  if (f.rsi >= 50 && f.rsi <= 75) score += 7;
  else if ((f.rsi >= 45 && f.rsi < 50) || (f.rsi > 75 && f.rsi <= 82)) score += 4;
  if (f.volRatio > 1) score += 3;
  return Math.round(Math.min(score, 100) * 10) / 10;
}

function candidateScore(base: number, f: Record<string, number>, amount: number, assetType: string, mode: string): number {
  let score = base + liquidityBonus(amount) - riskPenalty(f, assetType, mode);
  if (mode === "strict") score -= f.volRatio > 1 ? 0 : 4;
  if (mode === "aggressive" && f.ret5 > 3) score += 4;
  return Math.round(Math.max(Math.min(score, 100), 0) * 10) / 10;
}

function liquidityBonus(amount: number): number {
  if (amount >= 1_000_000_000) return 8;
  if (amount >= 300_000_000) return 6;
  if (amount >= 100_000_000) return 3;
  return 0;
}

function riskPenalty(f: Record<string, number>, assetType: string, mode: string): number {
  let penalty = 0;
  if (f.rsi >= 88) penalty += 14;
  else if (f.rsi >= 82) penalty += 9;
  else if (f.rsi >= 78) penalty += 4;
  if (f.drawdown20 > -0.5 && f.ret5 >= 8) penalty += 8;
  else if (f.drawdown20 > -1 && f.ret5 >= 5) penalty += 4;
  if (f.consecutiveUpDays >= 5 && f.drawdown20 > -1) penalty += 5;
  if (assetType === "ETF") {
    if (f.ret20 >= 30) penalty += 6;
    else if (f.ret20 >= 20) penalty += 3;
    if (f.volatility >= 4) penalty += 4;
  } else {
    if (f.ret20 >= 50) penalty += 8;
    else if (f.ret20 >= 35) penalty += 5;
    if (f.volatility >= 7) penalty += 5;
  }
  if (mode === "strict") return penalty * 1.25;
  if (mode === "aggressive") return penalty * 0.65;
  return penalty;
}

function riskNote(f: Record<string, number>, amount: number, assetType: string): string {
  const notes: string[] = [];
  if (amount < 100_000_000) notes.push("流动性偏低");
  if (f.rsi >= 82) notes.push("RSI过热");
  if (f.drawdown20 > -1 && f.ret5 >= 5) notes.push("短线接近高位");
  if ((assetType === "ETF" && f.ret20 >= 20) || (assetType === "A股" && f.ret20 >= 35)) notes.push("20日涨幅偏大");
  if ((assetType === "ETF" && f.volatility >= 4) || (assetType === "A股" && f.volatility >= 7)) notes.push("波动偏高");
  return notes.length ? notes.join("；") : "风险可控";
}

function tradeSuggestion(f: Record<string, number>, assetType: string): string {
  const score = f.candidateScore || f.continuationScore || 0;
  const drawdown = f.drawdown20 || 0;
  const rsi = f.rsi || 50;
  const ret5 = f.ret5 || 0;
  const ret20 = f.ret20 || 0;
  const trendStructure = f.trendScore || 0;
  const volumeConfirm = f.volumeConfirm || 0;
  const unit = assetType === "A股" ? "小仓试探" : "小额试探";
  if (score >= 85) {
    if (drawdown > -1 && ret5 >= 5) return "等回踩：趋势强但短线贴近高位，不追；回踩1%-3%且不破MA20再看";
    if (rsi >= 82) return "持有/不追：趋势强但RSI偏热，已有仓位可持有，未持仓等回落";
    return `${unit}：趋势强，回撤位置尚可；单笔不超过计划资金的10%-15%`;
  }
  if (score >= 70) {
    if (drawdown >= -6 && drawdown <= -1 && trendStructure >= 3) return `${unit}：趋势向上且有回踩，适合加入买入观察；跌破MA20放弃`;
    if (drawdown > -1) return "等回踩：趋势向上但买点偏高，等缩量回踩MA20附近";
    return "观察：趋势尚可，但位置或确认度一般，先等放量转强";
  }
  if (score >= 55) {
    if (volumeConfirm > 0 && ret20 > 0) return "观察不买：有转强迹象，等突破后回踩确认";
    return "观望：趋势不够顺，暂不作为优先买入标的";
  }
  if (rsi >= 82 || ret20 >= (assetType === "A股" ? 35 : 20)) return "减仓/回避：短线偏热或涨幅过大，已有仓位考虑分批落袋";
  return "回避：趋势弱，暂不买入";
}

function sellSuggestion(f: Record<string, number>, assetType: string): string {
  const score = f.candidateScore || f.continuationScore || 0;
  const drawdown = f.drawdown20 || 0;
  const rsi = f.rsi || 50;
  const ret20 = f.ret20 || 0;
  const trendStructure = f.trendScore || 0;
  if (score >= 70 && drawdown > -8) {
    if (rsi >= 85 || ret20 >= (assetType === "A股" ? 50 : 30)) return "已有仓位：可分批止盈10%-30%，保留底仓看趋势";
    return "已有仓位：继续持有，跌破MA20或放量转弱再减";
  }
  if (trendStructure < 2 || drawdown <= -10) return "已有仓位：趋势走弱，考虑减仓或止损";
  return "已有仓位：轻仓观察，反弹不过前高可减";
}

function trendGrade(score: number): string {
  if (score >= 80) return "强趋势";
  if (score >= 65) return "趋势向上";
  if (score >= 50) return "观察";
  return "偏弱";
}

function actionNote(score: number, drawdown20: number, rsi: number): string {
  if (score >= 80 && drawdown20 > -1) return "强势但接近高位，不追高，等回踩";
  if (score >= 65 && drawdown20 >= -6 && drawdown20 <= -1) return "趋势较顺，适合加入观察清单";
  if (score >= 50) return "有转强迹象，等量价继续确认";
  if (rsi >= 80) return "短线过热，防冲高回落";
  return "趋势不足，暂不优先";
}

async function mapLimit<T, R>(items: T[], limit: number, worker: (item: T) => Promise<R | null>): Promise<R[]> {
  const results: R[] = [];
  let index = 0;
  async function run() {
    while (index < items.length) {
      const item = items[index++];
      try {
        const result = await worker(item);
        if (result) results.push(result);
      } catch {
        const cached = await cachedScanRow(item);
        if (cached) results.push(cached as R);
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, run));
  return results;
}

async function cachedScanRow(row: SymbolRow): Promise<ScanRow | null> {
  const cacheDir = path.join(process.cwd(), "data", "cache", "generic");
  const prefixes = row.assetType === "A股" ? ["stock_scanner_v3_", "stock_scanner_v2_"] : ["scanner_v4_", "scanner_v3_", "scanner_v2_"];
  for (const prefix of prefixes) {
    try {
      const item = JSON.parse(await fs.readFile(path.join(cacheDir, `${prefix}${row.code}.json`), "utf-8"));
      const factors: Record<string, number> = {
        ret5: Number(item.ret_5 || item.ret5 || 0),
        ret10: Number(item.ret_10 || item.ret10 || 0),
        ret20: Number(item.ret_20 || item.ret20 || 0),
        trendScore: Number(item.trend_score || item.trendScore || 0),
        upDays5: Number(item.up_days_5 || item.upDays5 || 0),
        upDays10: Number(item.up_days_10 || item.upDays10 || 0),
        consecutiveUpDays: Number(item.consecutive_up_days || item.consecutiveUpDays || 0),
        drawdown20: Number(item.drawdown_20 || item.drawdown20 || 0),
        rsi: Number(item.rsi || 50),
        volRatio: Number(item.vol_ratio || item.volRatio || 1),
        volatility: Number(item.volatility || 0),
        volumeConfirm: Number(item.volume_confirm || item.volumeConfirm || 0),
      };
      const candidate = Number(item.candidate_score || item.candidateScore || item.continuation_score || item.continuationScore || 0);
      const continuation = Number(item.continuation_score || item.continuationScore || candidate);
      return {
        type: row.assetType,
        code: row.code,
        name: row.name,
        price: Number(item.price || row.price || 0),
        candidateScore: candidate,
        continuationScore: continuation,
        trendGrade: trendGrade(candidate),
        tradeSuggestion: item.trade_suggestion || tradeSuggestion({ ...factors, candidateScore: candidate, continuationScore: continuation }, row.assetType),
        sellSuggestion: item.sell_suggestion || sellSuggestion({ ...factors, candidateScore: candidate, continuationScore: continuation }, row.assetType),
        actionNote: item.action_note || actionNote(candidate, factors.drawdown20, factors.rsi),
        riskNote: item.risk_note || riskNote(factors, Number(item.amount || row.amount || 0), row.assetType),
        ret5: factors.ret5,
        ret10: factors.ret10,
        ret20: factors.ret20,
        upDays5: factors.upDays5,
        upDays10: factors.upDays10,
        consecutiveUpDays: factors.consecutiveUpDays,
        ma20Slope5: Number(item.ma20_slope_5 || item.ma20Slope5 || 0),
        drawdown20: factors.drawdown20,
        rsi: factors.rsi,
        volRatio: factors.volRatio,
      };
    } catch {
      // Try next cache prefix.
    }
  }
  return null;
}

function printTable(rows: ScanRow[]): void {
  const view = rows.map((row) => ({
    排名: row.rank,
    类型: row.type,
    代码: row.code,
    名称: row.name,
    价格: row.price.toFixed(2),
    候选分: row.candidateScore.toFixed(1),
    连涨趋势分: row.continuationScore.toFixed(1),
    趋势等级: row.trendGrade,
    买入建议: row.tradeSuggestion,
    "持有/卖出建议": row.sellSuggestion,
    观察建议: row.actionNote,
    风险提示: row.riskNote,
    "5日涨幅%": row.ret5.toFixed(2),
    "10日涨幅%": row.ret10.toFixed(2),
    "20日涨幅%": row.ret20.toFixed(2),
    "5日上涨天数": row.upDays5,
    "10日上涨天数": row.upDays10,
    连续上涨天数: row.consecutiveUpDays,
    "MA20斜率%": row.ma20Slope5.toFixed(2),
    "20日回撤%": row.drawdown20.toFixed(2),
    RSI: row.rsi.toFixed(2),
    量比: row.volRatio.toFixed(2),
  }));
  console.table(view);
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  if (!["etf", "stock", "all"].includes(args.universe)) throw new Error("--universe must be etf, stock, or all");
  if (!["strict", "balanced", "aggressive"].includes(args.mode)) throw new Error("--mode must be strict, balanced, or aggressive");
  const started = Date.now();
  const universeRows = await fetchUniverse(args.universe, args.includeDefensive);
  const selected = universeRows.sort((a, b) => b.amount - a.amount).slice(0, args.topN);
  const scanned = await mapLimit(selected, args.workers, async (row) => compute(row, await fetchKlines(row.code), args.mode));
  const ranked = scanned
    .sort((a, b) => b.candidateScore - a.candidateScore || b.continuationScore - a.continuationScore)
    .map((row, idx) => ({ ...row, rank: idx + 1 }));
  printTable(ranked.slice(0, args.limit));
  console.log(`数据源状态: fetched ${universeRows.length} ${UNIVERSE_LABEL[args.universe]} symbols; scanned ${scanned.length}/${selected.length}; ${((Date.now() - started) / 1000).toFixed(1)}s`);
}

main().catch((error) => {
  console.error(`扫描失败: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
