'use strict';
let code='',pin='',state=null,conn=null;
try{let s=JSON.parse(sessionStorage.getItem('cl-host')||'null');if(s?.code&&s.pin){code=s.code;pin=s.pin;$('pin').value=pin;$('resumeCode').value=code}}catch{}
function onReady(send){txt('connection','Connected');$('connection').className='pill green';if(code&&pin)send('host:resume',{code,pin})}
function onEvent(m,send){if(m.event==='reply'){
 const d=m.data||{};if(!d.ok){txt('authError',d.error);show('authError');return}
 if(d.code){code=d.code;sessionStorage.setItem('cl-host',JSON.stringify({code,pin}));show('authPanel',false);show('dashboard');updateJoinUrl()}
 if(d.csv){downloadCsv(d.csv,`competition-lab-${code}.csv`)}return;
 }if(m.event==='host:state'){state=m.data;code=state.code;show('authPanel',false);show('dashboard');updateJoinUrl();render(state)}}
conn=connectSocket(onReady,onEvent);
$('create').onclick=()=>{pin=$('pin').value.trim();show('authError',false);conn.send('host:create',{pin})};
$('resume').onclick=()=>{pin=$('pin').value.trim();code=$('resumeCode').value.trim().toUpperCase();show('authError',false);conn.send('host:resume',{pin,code})};
$('next').onclick=()=>conn.send('host:next',{code});
$('force').onclick=()=>{if(confirm('Finish the round and assign CUT to players who have not submitted?'))conn.send('host:force',{code})};
$('reset').onclick=()=>{if(confirm('Reset ALL rounds, decisions and scores?'))conn.send('host:reset',{code})};
$('export').onclick=()=>conn.send('host:export',{code});
$('copyUrl').onclick=()=>navigator.clipboard?.writeText(`${location.origin}/join?room=${code}`);
function updateJoinUrl(){const u=`${location.origin}/join?room=${code}`;txt('roomCode',code);txt('joinUrl',u);$('qr').src=`/api/qr?data=${encodeURIComponent(u)}`}
function render(s){
 txt('title',s.stage==='lobby'?'Ready to start':s.stage==='finished'?'All 12 rounds complete':`Round ${s.round} / 12`);
 txt('stageDescription',s.stage==='lobby'?'Invite students to join.':s.stage==='active'?`${phaseNames[s.phase]} — waiting for simultaneous decisions`:s.stage==='results'?`${phaseNames[s.phase]} — decisions revealed. Discuss before advancing.`:'Review and export results.');
 txt('students',s.playerCount);txt('submissions',`${s.submitted}/${s.playerCount}`);
 const allowNext=s.stage==='lobby'?s.playerCount>=4:s.stage==='results'&&s.round<12;
 $('next').disabled=!allowNext;$('next').textContent=s.stage==='lobby'?'Start Round 1':s.stage==='results'?`Start Round ${s.round+1}`:s.stage==='finished'?'Completed':'Waiting for submissions';show('force',s.stage==='active');
 show('botWarning',!!s.botWarning);txt('botWarning',s.botWarning);
 const body=$('leaderboard');body.replaceChildren();for(const p of [...s.players].sort((a,b)=>b.total-a.total)){let tr=document.createElement('tr');for(const t of [p.name+(p.bot?' (bot)':''),p.bot?'Scripted':p.online?'Online':'Offline',p.total,...p.phaseScores]){let td=document.createElement('td');td.textContent=t;tr.append(td)}if(p.bot)tr.style.opacity='.55';body.append(tr)}
 const pairs=$('pairs');pairs.replaceChildren();for(const g of s.groups){let div=document.createElement('div');div.className='rowcard';let name=document.createElement('span');name.textContent=g.names.join(' vs ');let count=document.createElement('span');count.className='pill '+(g.submitted===g.count?'green':'');count.textContent=`${g.submitted}/${g.count} human submitted`;div.append(name,count);pairs.append(div)}
 renderChart($('coopChart'),s.metrics,'cooperationRate',100);renderChart($('payChart'),s.metrics,'avgPayoff',60);
 const rs=$('roundStats');rs.replaceChildren();for(const r of s.roundStats){let tr=document.createElement('tr');for(const t of [r.round,phaseNames[r.phase],`${r.cooperationRate}%`, `€${r.avgPayoff}k`]){let td=document.createElement('td');td.textContent=t;tr.append(td)}rs.append(tr)}
 const review=$('chatReview');review.replaceChildren();for(const [id,msgs] of Object.entries(s.chats||{})){let section=document.createElement('details');let summary=document.createElement('summary');summary.textContent=`${id}: ${msgs.length} messages`;section.append(summary);for(const m of msgs){let p=document.createElement('p');p.className='small muted';p.textContent=`Round ${m.round} — ${m.name}: ${m.text}`;section.append(p)}review.append(section)}
}
