'use strict';
const params=new URLSearchParams(location.search);const code=params.get('room')?.toUpperCase()||'';if(code)$('room').value=code;
let room=code,token='',nickname='',lastState=null,connection=null;
try{let saved=JSON.parse(localStorage.getItem('cl-player')||'null');if(saved&&(!code||saved.code===code)){room=saved.code;token=saved.token;nickname=saved.name;$('room').value=room;$('nickname').value=nickname;}}catch{}
function onReady(send){txt('connection','Connected');$('connection').className='pill green';if(token)send('player:join',{code:room,token,name:nickname});}
function onEvent(m,send){if(m.event==='reply'){
 const d=m.data||{};if(!d.ok){if(lastState)alert(d.error);else{txt('joinError',d.error);show('joinError')}return}
 if(d.token){token=d.token;room=d.code;nickname=d.name;localStorage.setItem('cl-player',JSON.stringify({token,code:room,name:nickname}));show('joinSection',false);show('gameSection');}
 return;
 }if(m.event==='game:state'){lastState=m.data;room=lastState.room;show('joinSection',false);show('gameSection');render(lastState)}}
connection=connectSocket(onReady,onEvent);
$('joinForm').addEventListener('submit',e=>{e.preventDefault();room=$('room').value.trim().toUpperCase();nickname=$('nickname').value.trim();show('joinError',false);connection.send('player:join',{code:room,token:token||undefined,name:nickname})});
$('cooperate').addEventListener('click',()=>connection.send('player:move',{choice:'C'}));
$('defect').addEventListener('click',()=>connection.send('player:move',{choice:'D'}));
$('chatForm').addEventListener('submit',e=>{e.preventDefault();const str=$('chatText').value.trim();if(str&&lastState?.stage==='active'){connection.send('player:chat',{message:str});$('chatText').value=''}});
function render(s){
 txt('phase',s.phase<0?'BEFORE ROUND 1':`PHASE ${s.phase+1} OF 3`);txt('roundTitle',s.round<1?'Waiting room':`Round ${s.round} / 12`);
 txt('phasePill',s.phase<0?'Lobby':phaseNames[s.phase]);txt('subtitle',s.stage==='lobby'?`${s.playerCount} students joined. Waiting for your host.`:s.stage==='finished'?'Game complete. Compare your results in the debrief.':s.stage==='results'?'Round finished. Your facilitator will advance the game.':s.phaseInfo?.subtitle);
 txt('score',`€${Number(s.score||0).toFixed(0)}k`);txt('opponent',s.opponents?.join(' & ')||'Waiting…');show('botWarning',!!s.againstBot);
 show('decisionPanel',s.stage==='active');show('resultsPanel',s.stage==='results');show('chatPanel',s.phase===2&&(s.stage==='active'||s.stage==='results'));
 const disabled=!!s.chosen||s.stage!=='active';$('cooperate').disabled=disabled;$('defect').disabled=disabled;show('submittedMsg',!!s.chosen);txt('submittedMsg',`Your decision is locked: ${s.chosen==='C'?'MAINTAIN PRICE':'CUT PRICE'}. Waiting for the round to finish…`);
 if(s.result){txt('earned',`€${s.result.payoff}k`);txt('yourChoice',s.result.choice==='C'?'Maintain':'Cut');txt('otherDecision',`Opponent: ${s.result.opponents.map(x=>`${x.name} chose ${x.choice==='C'?'MAINTAIN':'CUT'}`).join(', ')}.${s.result.auto?' Your choice was filled automatically by the facilitator.':''}`)}
 renderChart($('personalChart'),s.phaseScores?.map((score,i)=>({avgPayoff:score})), 'avgPayoff', 240);
 const tbody=$('historyBody');tbody.replaceChildren();for(const h of s.history||[]){const row=document.createElement('tr');for(const v of [h.round,phaseNames[h.phase-1],h.choice==='C'?'Maintain':'Cut',`€${h.payoff}k`]){let td=document.createElement('td');td.textContent=v;row.append(td)}tbody.append(row)}
 let c=$('chatMsgs');c.replaceChildren();for(const msg of s.chat||[]){let div=document.createElement('div');div.className='msg';let strong=document.createElement('strong');strong.textContent=msg.name+': ';let span=document.createElement('span');span.textContent=msg.text;div.append(strong,span);c.append(div)}c.scrollTop=c.scrollHeight;
 $('chatText').disabled=s.stage!=='active';$('chatSend').disabled=s.stage!=='active';
}
