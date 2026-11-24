# -*- coding: utf-8 -*-
"""看板生成器：抓数据 → 渲染成自包含 HTML（离线可用，双击就开）"""
import json
from datetime import datetime

from . import analyzer, config, fetcher

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>投资看板</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f1115; --panel:#171a21; --panel2:#1e222b; --line:#272c36;
  --text:#e6e9ef; --dim:#8a93a5; --up:#ef4444; --down:#22c55e;
  --warn:#f59e0b; --good:#22c55e; --risk:#ef4444; --accent:#3b82f6;
}
body{background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;padding:20px}
.wrap{max-width:1400px;margin:0 auto}
h1{font-size:20px;font-weight:600;margin-bottom:4px}
.sub{color:var(--dim);font-size:12px;margin-bottom:18px}

/* 股票切换卡 */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-bottom:18px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px;cursor:pointer;transition:.15s}
.card:hover{border-color:#3b4252}
.card.active{border-color:var(--accent);background:#1a2233}
.card .nm{font-size:15px;font-weight:600;display:flex;justify-content:space-between;align-items:baseline}
.card .cd{color:var(--dim);font-size:11px;font-weight:400}
.card .px{font-size:24px;font-weight:600;margin:6px 0 2px;font-variant-numeric:tabular-nums}
.card .meta{color:var(--dim);font-size:12px;display:flex;gap:12px;flex-wrap:wrap}
.card .badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:11px;background:var(--panel2);color:var(--dim)}

/* tabs */
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin-bottom:16px;overflow-x:auto}
.tab{padding:9px 16px;cursor:pointer;color:var(--dim);border-bottom:2px solid transparent;white-space:nowrap;font-size:13px}
.tab:hover{color:var(--text)}
.tab.active{color:var(--text);border-bottom-color:var(--accent)}

.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:14px}
.panel h3{font-size:13px;font-weight:600;color:var(--dim);margin-bottom:12px;letter-spacing:.5px}

/* 指标网格 */
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px}
.metric .k{color:var(--dim);font-size:11px;margin-bottom:3px}
.metric .v{font-size:17px;font-weight:600;font-variant-numeric:tabular-nums}

/* 表格 */
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--dim);font-weight:500;font-size:11px;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:7px 8px;border-bottom:1px solid #1d2129;vertical-align:top}
tr:hover td{background:#1b1f27}
td a{color:#60a5fa;text-decoration:none}
td a:hover{text-decoration:underline}
.dt{color:var(--dim);font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}

/* 标签 */
.tag{display:inline-block;padding:1px 6px;border-radius:4px;font-size:11px;margin:1px 3px 1px 0}
.t-risk{background:rgba(239,68,68,.15);color:#f87171}
.t-good{background:rgba(34,197,94,.15);color:#4ade80}
.t-n{background:#252a34;color:var(--dim)}

/* 过滤条 */
.filters{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}
.fbtn{padding:5px 12px;border-radius:6px;background:var(--panel2);border:1px solid var(--line);color:var(--dim);cursor:pointer;font-size:12px}
.fbtn:hover{color:var(--text)}
.fbtn.active{background:var(--accent);border-color:var(--accent);color:#fff}

.up{color:var(--up)}.down{color:var(--down)}
.chart{width:100%;height:220px;display:block}
.empty{color:var(--dim);text-align:center;padding:30px;font-size:13px}
details{margin-top:10px}
summary{cursor:pointer;color:var(--dim);font-size:12px;padding:6px 0}
summary:hover{color:var(--text)}
.qa{border-left:2px solid var(--line);padding-left:12px;margin-bottom:14px}
.qa .q{color:#93c5fd;margin-bottom:4px}
.qa .a{color:var(--dim);font-size:13px;white-space:pre-wrap}
.hl{background:rgba(245,158,11,.2);color:#fbbf24;padding:0 2px;border-radius:2px}
</style>
</head>
<body>
<div class="wrap">
  <h1>投资看板</h1>
  <div class="sub" id="sub"></div>
  <div class="cards" id="cards"></div>
  <div class="tabs" id="tabs"></div>
  <div id="view"></div>
</div>

<script>
const DATA = __DATA__;
let cur = 0;           // 当前股票索引
let tab = "overview";  // 当前 tab
let filter = "all";    // 表格过滤

const TABS = [
  ["overview","概览"],
  ["chart","走势"],
  ["notice","公告"],
  ["news","新闻"],
  ["report","研报"],
  ["chip","筹码"],
  ["irm","互动"],
];

// ---------- 工具 ----------
const fmtPct = v => v==null ? "-" : (v>0?"+":"")+v.toFixed(2)+"%";
const clsPct = v => v>0 ? "up" : (v<0 ? "down" : "");
const esc = s => String(s==null?"":s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const yi = v => v==null ? "-" : (v/1e8).toFixed(2)+"亿";
// 金额自适应：小额用万，大额用亿
const money = v => {
  if(v==null) return "-";
  const a = Math.abs(v);
  if(a < 1e4) return v.toFixed(0);
  if(a < 1e8) return (v/1e4).toFixed(0)+"万";
  return (v/1e8).toFixed(2)+"亿";
};
// 持股数量自适应
const shares = v => {
  if(v==null) return "-";
  const a = Math.abs(v);
  if(a < 1e4) return v.toFixed(0)+"股";
  if(a < 1e8) return (v/1e4).toFixed(0)+"万股";
  return (v/1e8).toFixed(2)+"亿股";
};

function hl(text, words){
  if(!words || !words.length) return esc(text);
  let s = esc(text);
  words.forEach(w=>{
    if(!w) return;
    const re = new RegExp("(" + w.replace(/[.*+?^${}()|[\]\\]/g,"\\$&") + ")","g");
    s = s.replace(re, '<span class="hl">$1</span>');
  });
  return s;
}

// ---------- 顶部卡片 ----------
function renderCards(){
  const el = document.getElementById("cards");
  el.innerHTML = DATA.stocks.map((s,i)=>{
    const q = s.quote || {};
    return `<div class="card ${i===cur?'active':''}" onclick="selStock(${i})">
      <div class="nm"><span>${esc(s.name)}</span><span class="cd">${s.code}</span></div>
      <div class="px ${clsPct(q.pct)}">${q.price ?? "-"}</div>
      <div class="meta">
        <span class="${clsPct(q.pct)}">${fmtPct(q.pct)}</span>
        <span>PE ${q.pe_ttm ? q.pe_ttm.toFixed(1) : "-"}</span>
        <span>PB ${q.pb ? q.pb.toFixed(2) : "-"}</span>
        <span class="badge">${esc(s.role||"")}</span>
      </div>
    </div>`;
  }).join("");
}

function selStock(i){ cur = i; renderCards(); renderTabs(); render(); }
function selTab(t){ tab = t; renderTabs(); render(); }
function selFilter(f){ filter = f; render(); }

window.selStock = selStock; window.selTab = selTab; window.selFilter = selFilter;

// ---------- tabs ----------
function renderTabs(){
  const s = DATA.stocks[cur];
  const counts = {
    notice: s.notices.length,
    news: s.news.length,
    report: s.reports.length,
    irm: s.irm.length,
  };
  document.getElementById("tabs").innerHTML = TABS.map(([k,label])=>{
    const n = counts[k] ? ` <span style="opacity:.5">${counts[k]}</span>` : "";
    return `<div class="tab ${tab===k?'active':''}" onclick="selTab('${k}')">${label}${n}</div>`;
  }).join("");
}

// ---------- 主视图 ----------
function render(){
  const s = DATA.stocks[cur];
  const v = document.getElementById("view");
  if(tab==="overview") v.innerHTML = viewOverview(s);
  else if(tab==="chart") v.innerHTML = viewChart(s);
  else if(tab==="notice") v.innerHTML = viewNotice(s);
  else if(tab==="news") v.innerHTML = viewNews(s);
  else if(tab==="report") v.innerHTML = viewReport(s);
  else if(tab==="chip") v.innerHTML = viewChip(s);
  else if(tab==="irm") v.innerHTML = viewIrm(s);
  if(tab==="chart") drawChart(s);
}

function metric(k, val, cls){
  return `<div class="metric"><div class="k">${k}</div><div class="v ${cls||""}">${val}</div></div>`;
}

// 概览
function viewOverview(s){
  const q = s.quote || {};
  const t = s.trend || {};
  let html = "";

  html += `<div class="panel"><h3>行情与估值</h3><div class="grid">
    ${metric("现价", q.price ?? "-", clsPct(q.pct))}
    ${metric("涨跌", fmtPct(q.pct), clsPct(q.pct))}
    ${metric("总市值", q.mcap_yi ? q.mcap_yi.toFixed(0)+"亿" : "-")}
    ${metric("PE(TTM)", q.pe_ttm ? q.pe_ttm.toFixed(1) : "-")}
    ${metric("PB", q.pb ? q.pb.toFixed(2) : "-")}
    ${metric("换手率", q.turnover_pct!=null ? q.turnover_pct.toFixed(2)+"%" : "-")}
    ${metric("量比", q.vol_ratio ? q.vol_ratio.toFixed(2) : "-")}
    ${metric("一年分位", q.position!=null ? (q.position*100).toFixed(0)+"%" : "-")}
  </div></div>`;

  if(t.points && t.points.length){
    html += `<div class="panel"><h3>趋势判断 · ${esc(t.verdict||"")}</h3>
      <ul style="list-style:none;color:var(--dim);font-size:13px">`;
    t.points.forEach(p=> html += `<li style="padding:3px 0">· ${esc(p)}</li>`);
    html += `</ul></div>`;
  }

  if(s.alerts && s.alerts.length){
    html += `<div class="panel"><h3>⚠ 提醒</h3>`;
    s.alerts.forEach(a=> html += `<div style="color:#fbbf24;padding:3px 0;font-size:13px">· ${esc(a)}</div>`);
    html += `</div>`;
  }

  html += `<div class="panel"><h3>投资逻辑</h3>
    <div style="color:var(--dim);font-size:13px;line-height:1.7">${esc(s.thesis||"")}</div></div>`;

  const hi = s.notices.filter(n=>n.level==="high");
  if(hi.length){
    html += `<div class="panel"><h3>🔴 需关注公告 ${hi.length} 条</h3><table>`;
    hi.slice(0,6).forEach(n=>{
      html += `<tr><td class="dt">${n.date}</td>
        <td><a href="${esc(n.url)}" target="_blank">${hl(n.title, n.risk)}</a></td></tr>`;
    });
    html += `</table></div>`;
  }
  return html;
}

// 走势图
function viewChart(s){
  return `<div class="panel"><h3>近 ${(s.kline||[]).length} 个交易日</h3>
    <canvas class="chart" id="cv"></canvas>
    <div style="margin-top:10px;color:var(--dim);font-size:12px">
      MA20 <span id="ma20" style="color:#fbbf24"></span> · MA60 <span id="ma60" style="color:#60a5fa"></span>
    </div></div>`;
}

function drawChart(s){
  const cv = document.getElementById("cv");
  if(!cv || !s.kline || !s.kline.length) return;
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W*dpr; cv.height = H*dpr;
  const ctx = cv.getContext("2d");
  ctx.scale(dpr,dpr);

  const k = s.kline;
  const pad = {l:8, r:48, t:10, b:20};
  const cw = W - pad.l - pad.r, ch = H - pad.t - pad.b;

  const closes = k.map(x=>x.c);
  const highs = k.map(x=>x.h), lows = k.map(x=>x.l);
  let min = Math.min(...lows), max = Math.max(...highs);
  const padY = (max-min)*0.06; min -= padY; max += padY;

  const X = i => pad.l + (i/(k.length-1||1))*cw;
  const Y = v => pad.t + (1 - (v-min)/(max-min||1))*ch;

  // 网格
  ctx.strokeStyle = "#232833"; ctx.lineWidth = 1;
  for(let i=0;i<=4;i++){
    const y = pad.t + ch*i/4;
    ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(pad.l+cw,y); ctx.stroke();
    const val = max - (max-min)*i/4;
    ctx.fillStyle = "#6b7280"; ctx.font = "10px sans-serif"; ctx.textAlign="left";
    ctx.fillText(val.toFixed(2), pad.l+cw+6, y+3);
  }

  // MA 线
  function ma(n, color){
    ctx.strokeStyle = color; ctx.lineWidth = 1.2; ctx.beginPath();
    let started = false;
    for(let i=n-1;i<k.length;i++){
      const avg = closes.slice(i-n+1,i+1).reduce((a,b)=>a+b,0)/n;
      const x=X(i), y=Y(avg);
      if(!started){ ctx.moveTo(x,y); started=true; } else ctx.lineTo(x,y);
    }
    ctx.stroke();
  }
  ma(20, "rgba(251,191,36,.75)");
  ma(60, "rgba(96,165,250,.75)");

  // 收盘价面积
  const grad = ctx.createLinearGradient(0,pad.t,0,pad.t+ch);
  grad.addColorStop(0,"rgba(59,130,246,.25)");
  grad.addColorStop(1,"rgba(59,130,246,0)");
  ctx.beginPath();
  ctx.moveTo(X(0), Y(closes[0]));
  for(let i=1;i<k.length;i++) ctx.lineTo(X(i), Y(closes[i]));
  ctx.lineTo(X(k.length-1), pad.t+ch); ctx.lineTo(X(0), pad.t+ch); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();

  // 收盘价线
  ctx.beginPath(); ctx.strokeStyle = "#3b82f6"; ctx.lineWidth = 1.6;
  ctx.moveTo(X(0), Y(closes[0]));
  for(let i=1;i<k.length;i++) ctx.lineTo(X(i), Y(closes[i]));
  ctx.stroke();

  // 日期刻度
  ctx.fillStyle="#6b7280"; ctx.font="10px sans-serif";
  [0, Math.floor(k.length/2), k.length-1].forEach(i=>{
    ctx.textAlign = i===0?"left":(i===k.length-1?"right":"center");
    ctx.fillText(k[i].d, X(i), H-5);
  });

  const m20 = closes.slice(-20).reduce((a,b)=>a+b,0)/20;
  const m60 = closes.length>=60 ? closes.slice(-60).reduce((a,b)=>a+b,0)/60 : null;
  const e20 = document.getElementById("ma20"), e60 = document.getElementById("ma60");
  if(e20) e20.textContent = m20.toFixed(2);
  if(e60) e60.textContent = m60 ? m60.toFixed(2) : "-";
}

// 公告
function viewNotice(s){
  const n = s.notices;
  if(!n.length) return `<div class="panel"><div class="empty">近期无公告</div></div>`;
  const hi = n.filter(x=>x.level==="high").length;
  const gd = n.filter(x=>x.level==="good").length;
  const list = filter==="all" ? n : n.filter(x=>x.level===filter);

  let html = `<div class="panel"><h3>公告（共 ${n.length} · 风险 ${hi} · 利好 ${gd}）</h3>
    <div class="filters">
      <div class="fbtn ${filter==='all'?'active':''}" onclick="selFilter('all')">全部 ${n.length}</div>
      <div class="fbtn ${filter==='high'?'active':''}" onclick="selFilter('high')">风险 ${hi}</div>
      <div class="fbtn ${filter==='good'?'active':''}" onclick="selFilter('good')">利好 ${gd}</div>
    </div><table><tr><th style="width:90px">日期</th><th>标题</th><th style="width:200px">命中</th></tr>`;
  list.forEach(x=>{
    const tags = (x.risk||[]).map(w=>`<span class="tag t-risk">${esc(w)}</span>`).join("")
               + (x.good||[]).map(w=>`<span class="tag t-good">${esc(w)}</span>`).join("");
    html += `<tr><td class="dt">${x.date}</td>
      <td><a href="${esc(x.url)}" target="_blank">${hl(x.title, [...(x.risk||[]),...(x.good||[])])}</a></td>
      <td>${tags || '<span class="tag t-n">-</span>'}</td></tr>`;
  });
  return html + `</table></div>`;
}

// 新闻
function viewNews(s){
  let html = "";
  const n = s.news;
  if(n.length){
    const list = filter==="all" ? n : n.filter(x=>x.tag===(filter==="high"?"risk":"good"));
    html += `<div class="panel"><h3>个股新闻（${n.length}）</h3>
      <div class="filters">
        <div class="fbtn ${filter==='all'?'active':''}" onclick="selFilter('all')">全部 ${n.length}</div>
        <div class="fbtn ${filter==='high'?'active':''}" onclick="selFilter('high')">风险 ${n.filter(x=>x.tag==='risk').length}</div>
        <div class="fbtn ${filter==='good'?'active':''}" onclick="selFilter('good')">利好 ${n.filter(x=>x.tag==='good').length}</div>
      </div><table><tr><th style="width:130px">时间</th><th>标题</th><th style="width:80px">来源</th></tr>`;
    list.forEach(x=>{
      html += `<tr><td class="dt">${(x.time||"").slice(0,16)}</td>
        <td><a href="${esc(x.url)}" target="_blank">${hl(x.title, [...(x.risk||[]),...(x.good||[])])}</a></td>
        <td class="dt">${esc(x.source)}</td></tr>`;
    });
    html += `</table></div>`;
  } else {
    html += `<div class="panel"><div class="empty">该股近期无个股新闻<br>
      <span style="font-size:12px">小盘股新闻覆盖少是常态，看「公告」和「互动」更有效</span></div></div>`;
  }

  if(s.market_news && s.market_news.length){
    html += `<div class="panel"><h3>市场快讯（大盘背景）</h3><table>`;
    s.market_news.slice(0,20).forEach(x=>{
      html += `<tr><td class="dt">${(x.time||"").slice(0,16)}</td>
        <td><a href="${esc(x.url)}" target="_blank">${esc(x.title)}</a></td></tr>`;
    });
    html += `</table></div>`;
  }
  return html;
}

// 研报
function viewReport(s){
  const r = s.reports;
  if(!r.length) return `<div class="panel"><div class="empty">暂无机构研报（小盘股常见）</div></div>`;
  const rs = s.reports_scored || {};
  let html = `<div class="panel"><h3>机构研报（${r.length} 篇 / ${rs.orgs||0} 家）</h3>`;
  if(rs.ratings){
    html += `<div style="margin-bottom:12px">`;
    Object.entries(rs.ratings).forEach(([k,v])=>{
      html += `<span class="tag t-good">${esc(k)} × ${v}</span>`;
    });
    html += `</div>`;
  }
  if(rs.latest && rs.latest.eps_cur){
    html += `<div style="color:var(--dim);font-size:13px;margin-bottom:12px">
      EPS 预测：今年 <b style="color:var(--text)">${rs.latest.eps_cur}</b>
      / 明年 <b style="color:var(--text)">${rs.latest.eps_next||"-"}</b></div>`;
  }
  html += `<table><tr><th style="width:90px">日期</th><th style="width:110px">机构</th>
    <th style="width:70px">评级</th><th>标题</th></tr>`;
  r.forEach(x=>{
    const rc = x.rating.includes("买入")?"t-good":(x.rating.includes("增持")?"t-good":"t-n");
    html += `<tr><td class="dt">${x.date}</td><td>${esc(x.org)}</td>
      <td><span class="tag ${rc}">${esc(x.rating||"-")}</span></td>
      <td>${esc(x.title)}</td></tr>`;
  });
  return html + `</table></div>`;
}

// 筹码
function viewChip(s){
  let html = "";
  if(s.holders && s.holders.length){
    const h = s.holders[0];
    html += `<div class="panel"><h3>股东户数（筹码集中度）</h3><div class="grid">
      ${metric("股东户数", h.num != null ? h.num.toLocaleString() : "-")}
      ${metric("环比变化", h.ratio != null ? (h.ratio>0?"+":"")+h.ratio.toFixed(2)+"%" : "-",
               h.ratio>0?"down":"up")}
    </div>
    <div style="color:var(--dim);font-size:12px;margin-top:10px">
      户数减少 = 筹码集中（通常偏多）；户数增加 = 筹码分散。数据截至 ${h.date}
    </div></div>`;
  }
  if(s.margin && s.margin.length){
    html += `<div class="panel"><h3>融资融券</h3><table>
      <tr><th>日期</th><th>融资余额</th><th>融资净买入</th><th>融券余额</th></tr>`;
    s.margin.forEach(m=>{
      html += `<tr><td class="dt">${m.date}</td>
        <td>${yi(m.rzye)}</td>
        <td class="${m.rzjme>0?'up':(m.rzjme<0?'down':'')}">${money(m.rzjme)}</td>
        <td>${yi(m.rqye)}</td></tr>`;
    });
    html += `</table></div>`;
  }
  if(s.lockup && s.lockup.length){
    html += `<div class="panel"><h3>限售解禁</h3><table>
      <tr><th>解禁日</th><th>数量</th><th>占总股本</th><th>参考市值</th><th>类型</th><th></th></tr>`;
    s.lockup.forEach(x=>{
      html += `<tr><td class="dt">${x.date}</td>
        <td>${shares(x.shares)}</td>
        <td>${x.ratio != null ? x.ratio.toFixed(2)+"%" : "-"}</td>
        <td>${x.mcap ? money(x.mcap) : "-"}</td>
        <td class="dt">${esc(x.type||"-")}</td>
        <td>${x.future?'<span class="tag t-risk">待解禁</span>':'<span class="tag t-n">已过</span>'}</td></tr>`;
    });
    html += `</table></div>`;
  }
  if(s.lhb && s.lhb.length){
    html += `<div class="panel"><h3>龙虎榜</h3><table>
      <tr><th style="width:90px">日期</th><th>上榜原因</th><th style="width:100px">净买额</th></tr>`;
    s.lhb.forEach(x=>{
      html += `<tr><td class="dt">${x.date}</td><td>${esc(x.reason)}</td>
        <td class="${x.net>0?'up':'down'}">${money(x.net)}</td></tr>`;
    });
    html += `</table></div>`;
  }
  if(!html) html = `<div class="panel"><div class="empty">暂无可用的筹码数据</div></div>`;
  return html;
}

// 互动易
function viewIrm(s){
  const irm = s.irm || [];
  if(!irm.length) return `<div class="panel"><div class="empty">暂无投资者问答</div></div>`;
  const ans = irm.filter(x=>x.answer);
  let html = `<div class="panel"><h3>投资者互动（${ans.length}/${irm.length} 已回复）</h3>`;
  html += `<div class="filters">
    <div class="fbtn ${filter==='all'?'active':''}" onclick="selFilter('all')">全部 ${irm.length}</div>
    <div class="fbtn ${filter==='high'?'active':''}" onclick="selFilter('high')">已回复 ${ans.length}</div>
  </div>`;
  const list = filter==="all" ? irm : ans;
  list.forEach(x=>{
    html += `<div class="qa"><div class="q">Q（${esc(x.time)}）：${esc(x.question)}</div>`;
    html += x.answer
      ? `<div class="a">A：${esc(x.answer)}</div>`
      : `<div class="a" style="color:#6b7280">（未回复）</div>`;
    html += `</div>`;
  });
  return html + `</div>`;
}

// 启动
function initFromHash(){
  // 支持 #tab=notice 和 #code=600251 直接定位，可收藏书签
  const h = location.hash.slice(1);
  h.split("&").forEach(p=>{
    const [k,val] = p.split("=");
    if(k==="tab" && TABS.some(t=>t[0]===val)) tab = val;
    if(k==="code"){
      const i = DATA.stocks.findIndex(s=>s.code===val);
      if(i>=0) cur = i;
    }
  });
}

document.getElementById("sub").textContent =
  "数据时间 " + DATA.fetched_at + " · 点击卡片切换标的 · 数据源：腾讯行情 / 巨潮公告 / 东财研报";
initFromHash();
renderCards(); renderTabs(); render();
window.addEventListener("resize", ()=>{ if(tab==="chart") drawChart(DATA.stocks[cur]); });
window.addEventListener("hashchange", ()=>{ initFromHash(); renderCards(); renderTabs(); render(); });
</script>
</body>
</html>
"""


def build(codes=None):
    watch = config.WATCHLIST
    if codes:
        watch = [s for s in watch if s["code"] in codes]

    print("=" * 70)
    print(f"生成看板  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 70)

    stocks = []
    market_news = fetcher.get_market_news(25)

    for stock in watch:
        d = fetcher.collect(stock)

        news_scored = analyzer.score_news(d["news"], stock)
        notices_scored = analyzer.score_notices(d["notices"])
        reports_scored = analyzer.score_reports(d["reports"])

        kline = []
        if d["kline"] is not None and len(d["kline"]):
            for _, r in d["kline"].tail(120).iterrows():
                kline.append({
                    "d": r["date"].strftime("%m-%d"),
                    "o": round(float(r["open"]), 2),
                    "c": round(float(r["close"]), 2),
                    "h": round(float(r["high"]), 2),
                    "l": round(float(r["low"]), 2),
                    "v": float(r["volume"]),
                })

        stocks.append({
            "code": stock["code"],
            "name": stock["name"],
            "role": stock.get("role", ""),
            "thesis": stock.get("thesis", ""),
            "quote": {k: v for k, v in (d["quote"] or {}).items() if k != "kline"},
            "trend": analyzer.trend_read(d["quote"]),
            "val": analyzer.valuation(d["quote"]),
            "alerts": analyzer.alerts({**d, "notices_scored": notices_scored}),
            "kline": kline,
            "notices": notices_scored,
            "news": [{k: v for k, v in n.items() if k != "summary"} for n in news_scored],
            "market_news": market_news,
            "reports": d["reports"],
            "reports_scored": reports_scored,
            "irm": d["irm"],
            "holders": d["holders"],
            "margin": d["margin"],
            "lockup": d["lockup"],
            "lhb": d["lhb"],
        })

    payload = {
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stocks": stocks,
    }

    html = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    out = config.OUT_DIR / "dashboard.html"
    out.write_text(html, encoding="utf-8")

    print(f"\n看板已生成: {out}")
    print(f"大小: {out.stat().st_size/1024:.0f} KB")
    return out
