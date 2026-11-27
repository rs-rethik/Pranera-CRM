import{a as e,i as t}from"./index-DB3_v4Hn.js";import{n,r,t as i}from"./format-Bwgy4HPG.js";function a(e){let t=parseInt(e,10);return Number.isNaN(t)?0:t}function o(e,t){if(!e||!t)return!0;if(typeof e==`boolean`)return e;if(typeof e==`function`)return e(t);if(e.startsWith(`eval:`))try{return Function(`doc`,`return (${e.slice(5)})`)(t)}catch{return!0}let n=t[e];return Array.isArray(n)?!!n.length:!!n}function s(){let e=new Date;return`${e.getFullYear()}-${String(e.getMonth()+1).padStart(2,`0`)}-${String(e.getDate()).padStart(2,`0`)}`}function c(e,t){let n=new Date(`${e}T00:00:00`);return n.setDate(n.getDate()+t),`${n.getFullYear()}-${String(n.getMonth()+1).padStart(2,`0`)}-${String(n.getDate()).padStart(2,`0`)}`}function l(e,t){let n=e.split(`-`).map(Number),r=n[0],i=n[1]-1,a=n[2],o=new Date(r,i+t,1),s=o.getFullYear(),c=o.getMonth(),l=new Date(s,c+1,0).getDate(),u=Math.min(a,l);return`${s}-${String(c+1).padStart(2,`0`)}-${String(u).padStart(2,`0`)}`}var u=[`ui`,`model`,`form`,`dom`,`views`,`meta`,`call`,`xcall`,`msgprint`,`show_alert`,`set_route`,`route_options`,`realtime`,`format`,`tools`];function d(){let e=new Proxy(function(){},{get(t,n){if(n!==`then`)return n===Symbol.toPrimitive?()=>``:e},apply:()=>e,construct:()=>e});return e}function f(e,t){return new Proxy(e,{get(e,n){return n in e?e[n]:t}})}function p(e,t,n={}){if(!e)return[];try{let r=s(),i=n.sessionUser||``,a=n.filterValues||{},o=d(),p=f({query_reports:{},datetime:f({get_today:()=>r,now_datetime:()=>`${r} 00:00:00`,add_months:(e,t)=>l(e,t),add_days:(e,t)=>c(e,t),month_start:()=>`${r.slice(0,7)}-01`,month_end:()=>{let e=r.split(`-`).map(Number),t=new Date(e[0],e[1],0).getDate();return`${e[0]}-${String(e[1]).padStart(2,`0`)}-${String(t).padStart(2,`0`)}`},quarter_start:()=>{let e=r.split(`-`).map(Number),t=Math.floor((e[1]-1)/3)*3+1;return`${e[0]}-${String(t).padStart(2,`0`)}-01`},quarter_end:()=>{let e=r.split(`-`).map(Number),t=Math.floor((e[1]-1)/3)*3+3,n=new Date(e[0],t,0).getDate();return`${e[0]}-${String(t).padStart(2,`0`)}-${String(n).padStart(2,`0`)}`},str_to_obj:e=>new Date(`${e}T00:00:00`),obj_to_str:e=>!(e instanceof Date)||isNaN(e.getTime())?r:`${e.getFullYear()}-${String(e.getMonth()+1).padStart(2,`0`)}-${String(e.getDate()).padStart(2,`0`)}`,user_to_str:e=>e,user_to_obj:e=>new Date(`${e}T00:00:00`),year_start:()=>`${new Date().getFullYear()}-01-01`,year_end:()=>`${new Date().getFullYear()}-12-31`,get_diff:(e,t)=>{let n=new Date(`${e}T00:00:00`).getTime(),r=new Date(`${t}T00:00:00`).getTime();return Math.round((n-r)/864e5)},validate:()=>!0,get_datetime_as_string:e=>e instanceof Date?e.toISOString().replace(`T`,` `).slice(0,19):String(e||``)},o),session:{user:i},boot:{user_info:{name:i}},defaults:f({get_user_default:e=>e===`user`?i:``,get_default:e=>e===`user`?i:``,get_global_default:()=>``},o),utils:f({get_fiscal_year:()=>null,formatDate:e=>e,nowdate:()=>r},o),query_report:f({get_filter_value:e=>a[e],set_filter_value:(e,t)=>{a[e]=t}},o),db:f({get_value:()=>null,get_list:()=>[],count:()=>0},o),provide:()=>o,require:(e,t)=>(typeof t==`function`&&t(),Promise.resolve()),...Object.fromEntries(u.map(e=>[e,o]))},void 0);return Function(`frappe`,`__`,`erpnext`,e)(p,e=>e,o),(p.query_reports[t]||p.query_reports[t?.replace(/ /g,`_`)]||Object.values(p.query_reports)[0]||{}).filters||[]}catch(e){return console.warn(`Failed to evaluate report filters script for`,t,e),n.onError?.(e),[]}}var m=[`Link`,`Dynamic Link`,`Select`,`Autocomplete`,`MultiSelectList`,`Date`,`Datetime`,`DateRange`,`Check`,`Data`,`Small Text`,`Int`,`Float`,`Currency`,`Percent`];function h(e){return m.includes(e?.fieldtype||`Data`)}function g(e){return e==null||e===``||Array.isArray(e)&&!e.length}function _(e){let t=e?.default;if(typeof t==`function`)try{t=t()}catch{t=null}return(t===`Today`||t===`today`)&&(t=s()),(t===void 0||typeof t==`function`)&&(t=null),t}function v(e,t){return h(e)&&!!o(e.depends_on,t||{})}function y(e,t){return v(e,t)&&!a(e.hidden)}function b(e,t){let n={};for(let r of e||[]){let e=t?.[r.fieldname];v(r,t)&&!g(e)&&(n[r.fieldname]=e)}return n}function x(e,n){return(e||[]).filter(e=>a(e.reqd)&&v(e,n)&&g(n?.[e.fieldname])).map(e=>t(e.label||e.fieldname))}function S(e,n){let r={};for(let i of e||[]){let e=n?.[i.fieldname];if(!v(i,n)||g(e))continue;let o=t(i.label||i.fieldname);r[o]=i.fieldtype===`Check`?a(e)?t(`Yes`):t(`No`):Array.isArray(e)?e.join(i.fieldtype===`DateRange`?` – `:`, `):e}return r}function C(e){if(!e?.get_query)return null;let t;try{t=typeof e.get_query==`function`?e.get_query():e.get_query}catch{return null}let n=t?.filters;return n&&typeof n==`object`?n:null}var w={"CRM Deal":`deals`,"CRM Lead":`leads`,Contact:`contacts`,"CRM Organization":`organizations`};function T(e,t,n){if(!e||typeof e!=`string`)return null;let r=``;t?.type===`Link`&&t.options?r=t.options:t?.key===`name`&&(r=n||``);let i=w[r];return i?`/crm/${i}/${encodeURIComponent(e)}`:null}function E(t,n,r){return n?.options&&t?.[n.options]||t?.currency||r||e().currency||`USD`}function D(t,n,i=e()){let a=r(t,{precision:i.currency_precision,site:i});if(i.currency_symbol&&(!n||n===i.currency))return`${i.currency_symbol} ${a}`;let o=n;try{o=new Intl.NumberFormat(`en`,{style:`currency`,currency:n}).formatToParts(0).find(e=>e.type===`currency`)?.value||n}catch{}return o?`${o} ${a}`:a}function O(e,o,s,c={}){if(e==null||e===``)return``;if(Array.isArray(e))return e.join(`, `);switch(o?.type){case`Currency`:return D(e,E(s,o,c.defaultCurrency));case`Float`:return r(e);case`Int`:return r(e,{precision:0});case`Percent`:return`${r(e)}%`;case`Check`:return a(e)?t(`Yes`):t(`No`);case`Date`:return i(e);case`Datetime`:return n(e);default:return String(e)}}var k={pdf:[`application/pdf`],xlsx:[`spreadsheetml`,`application/vnd.ms-excel`,`application/octet-stream`],csv:[`text/csv`,`application/csv`,`application/octet-stream`]};function A(e,t){if(!e?.ok)return!1;let n=e.headers?.get(`content-type`)||``;return(k[t]||[]).some(e=>n.includes(e))}function j(e){return String(e).replace(/<[^>]*>/g,``).trim()}async function M(e,t){let n;try{n=await e.clone().json()}catch{return t}if(n?._server_messages)try{let e=JSON.parse(n._server_messages).map(e=>{try{return JSON.parse(e).message}catch{return e}}).filter(Boolean).map(j);if(e.length)return e.join(` `)}catch{}if(typeof n?.exception==`string`){let e=n.exception.split(`: `).slice(1).join(`: `).trim();if(e)return j(e)}return t}function N(e){return e==null?``:String(e).replace(/&/g,`&amp;`).replace(/</g,`&lt;`).replace(/>/g,`&gt;`).replace(/"/g,`&quot;`).replace(/'/g,`&#039;`)}function P({title:e=`Report`,filters:t={},includeFilters:n=!0,columns:r=[],rows:i=[],totalRow:a=null,orientation:o=`Landscape`,printDate:s=``,formatValue:c=e=>e}){let l=s||new Date().toLocaleString(),u=n&&t?Object.entries(t).filter(([,e])=>e!=null&&e!==``):[],d=u.length>0?`<div class="filters-container">
        <strong>Applied Filters:</strong>
        <div class="filter-pills">
          ${u.map(([e,t])=>`<span class="filter-pill"><span class="filter-key">${N(e)}:</span> ${N(Array.isArray(t)?t.join(`, `):t)}</span>`).join(` `)}
        </div>
      </div>`:``,f=r.map(e=>`<th style="text-align: ${e.align||`left`};">${N(e.label||e.key)}</th>`).join(``),p=e=>r.map(t=>{let n=c(e[t.key]??``,t,e);return`<td style="text-align: ${t.align||`left`};">${N(n)}</td>`}).join(``),m=i.map(e=>`<tr>${p(e)}</tr>`).join(``),h=a?`<tfoot><tr class="total-row">${p(a)}</tr></tfoot>`:``;return`<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${N(e)}</title>
  <style>
    @page {
      size: ${o.toLowerCase()};
      margin: 12mm;
    }
    * {
      box-sizing: border-box;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: #1f2937;
      background: #ffffff;
      margin: 0;
      padding: 16px;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    .report-header {
      border-bottom: 2px solid #e5e7eb;
      padding-bottom: 12px;
      margin-bottom: 16px;
    }
    .report-header-top {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
    }
    h1 {
      margin: 0;
      font-size: 22px;
      font-weight: 700;
      color: #111827;
    }
    .report-meta {
      font-size: 11px;
      color: #6b7280;
    }
    .filters-container {
      margin-top: 10px;
      font-size: 12px;
    }
    .filter-pills {
      display: inline-flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 4px;
    }
    .filter-pill {
      background: #f3f4f6;
      border: 1px solid #e5e7eb;
      border-radius: 4px;
      padding: 2px 8px;
      font-size: 11px;
    }
    .filter-key {
      font-weight: 600;
      color: #4b5563;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 11px;
      line-height: 1.4;
    }
    th {
      background-color: #f9fafb !important;
      color: #374151;
      font-weight: 600;
      border: 1px solid #e5e7eb;
      padding: 6px 10px;
      white-space: nowrap;
    }
    td {
      border: 1px solid #e5e7eb;
      padding: 6px 10px;
      color: #1f2937;
    }
    tr:nth-child(even) td {
      background-color: #fbfcfd;
    }
    .total-row td {
      font-weight: 600;
      border-top: 2px solid #d1d5db;
      background-color: #f9fafb;
    }
    .report-footer {
      margin-top: 16px;
      font-size: 11px;
      color: #6b7280;
      display: flex;
      justify-content: space-between;
    }
    @media print {
      body {
        padding: 0;
      }
      thead {
        display: table-header-group;
      }
      tr {
        page-break-inside: avoid;
      }
    }
  </style>
</head>
<body>
  <div class="report-header">
    <div class="report-header-top">
      <h1>${N(e)}</h1>
      <div class="report-meta">Printed: ${N(l)}</div>
    </div>
    ${d}
  </div>
  <table>
    <thead>
      <tr>${f}</tr>
    </thead>
    <tbody>
      ${m||`<tr><td colspan="`+(r.length||1)+`" style="text-align: center; padding: 20px;">No records found</td></tr>`}
    </tbody>
    ${h}
  </table>
  <div class="report-footer">
    <span>Total rows: ${i.length}</span>
    <span>Pranera CRM</span>
  </div>
</body>
</html>`}function F(e,t){let n=window.URL.createObjectURL(e),r=document.createElement(`a`);r.style.display=`none`,r.href=n,r.download=t,document.body.appendChild(r),r.click(),setTimeout(()=>{document.body.removeChild(r),window.URL.revokeObjectURL(n)},100)}function I(e){let t=window.open(``,`_blank`);if(!t){alert(`Please allow pop-ups in your browser to print the report.`);return}t.document.open(),t.document.write(e),t.document.close(),t.focus(),setTimeout(()=>{t.onafterprint=()=>{try{t.close()}catch{}},t.print()},250)}export{S as a,T as c,A as d,y as f,F as h,P as i,b as l,_ as m,p as n,C as o,I as p,O as r,x as s,N as t,M as u};