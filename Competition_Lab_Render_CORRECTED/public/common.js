'use strict';
const $ = id => document.getElementById(id);
const txt = (id,s) => {const el=$(id);if(el)el.textContent=s??''};
const show = (id,yes=true) => $(id)?.classList.toggle('hidden',!yes);
const phaseNames=['Random Matchups','Repeated Rivalry','Negotiation + Chat'];
const val = x=>x==null?'—':x;
function connectSocket(onReady,onEvent){
 let ws, retries=0, stopped=false;
 function connect(){
   let protocol=location.protocol==='https:'?'wss':'ws';
   ws=new WebSocket(`${protocol}://${location.host}/ws`);
   ws.onopen=()=>{retries=0;onReady(send)};
   ws.onmessage=evt=>{try{let m=JSON.parse(evt.data);onEvent(m,send)}catch(err){console.error(err)}};
   ws.onclose=()=>{if(!stopped)setTimeout(connect,Math.min(5000,700+retries++*600))};
 }
 function send(event,data={}){if(ws?.readyState===1)ws.send(JSON.stringify({event,data,requestId:Date.now().toString(36)+Math.random().toString(36).slice(2,6)}));}
 connect();return{send,close(){stopped=true;ws?.close()}};
}
function renderChart(element,data,field,max){
 element.replaceChildren();
 for(let i=0;i<3;i++){
   const item=data?.[i]||{},n=item[field];
   const col=document.createElement('div');col.className='barcol';
   const value=document.createElement('div');value.className='barvalue';value.textContent=n==null?'—':field==='cooperationRate'?`${n}%`:`${n}k`;
   const bar=document.createElement('div');bar.className='bar';bar.style.height=n==null?'2px':`${Math.max(3,Math.min(120,120*n/max))}px`;
   const label=document.createElement('div');label.className='barlabel';label.textContent=phaseNames[i];
   col.append(value,bar,label);element.append(col);
 }
}
function downloadCsv(content,filename){let blob=new Blob([content],{type:'text/csv;charset=utf-8'});let a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=filename;a.click();URL.revokeObjectURL(a.href)}
