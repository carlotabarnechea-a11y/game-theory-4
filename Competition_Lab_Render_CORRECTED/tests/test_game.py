from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server


def make_room(n):
    r=server.Room(code='TEST123')
    for i in range(n):
        key=f't{i}'
        r.players[key]=server.Player(token=key,name=f'Player {i+1}')
    return r


def submit_all(r, choices):
    for i,t in enumerate(t for t,p in r.players.items() if not p.bot):
        r.moves[t]=choices[i%len(choices)]
    server.finish_round(r)


def test_twelve_rounds_ten_students():
    r=make_room(10)
    assert r.stage=='lobby'
    fixed=None
    for round_number in range(12):
        server.start_round(r)
        assert r.stage=='active'
        assert len(r.groups)==5
        assert all(len(g['members'])==2 for g in r.groups)
        if round_number==4: fixed=[sorted(g['members']) for g in r.groups]
        if round_number>=4: assert fixed==[sorted(g['members']) for g in r.groups]
        submit_all(r,['C','D'])
        assert r.stage=='results'
    server.start_round(r)
    assert r.stage=='finished'
    assert all(len(p.history)==12 for p in r.players.values())
    assert len(server.metrics(r))==3
    assert server.metrics(r)[0]['rounds']==4
    assert len(server.make_csv(r).splitlines())==121


def test_nine_students_uses_scripted_bot():
    r=make_room(9)
    server.start_round(r)
    bots=[p for p in r.players.values() if p.bot]
    assert len(bots)==1
    assert bots[0].token in r.moves
    assert len(r.groups)==5
    submit_all(r,['C'])
    assert r.stage=='results'
    assert server.metrics(r)[0]['samples']==9
    for _ in range(7):
        server.start_round(r)
        submit_all(r,['C'])
    assert r.round_index==7
    original=[g['members'] for g in r.groups]
    server.start_round(r)
    assert r.groups and [g['members'] for g in r.groups]==original
    assert r.chats and any(messages for messages in r.chats.values())


def test_payoffs_and_force_missing():
    r=make_room(4)
    server.start_round(r)
    g1,g2=r.groups
    a,b=g1['members']
    c,d=g2['members']
    r.moves={a:'C',b:'C',c:'D',d:'D'}
    server.finish_round(r)
    assert r.rounds[-1]['results'][a]['payoff']==50
    assert r.rounds[-1]['results'][b]['payoff']==50
    assert r.rounds[-1]['results'][c]['payoff']==30
    assert r.rounds[-1]['results'][d]['payoff']==30
    server.start_round(r)
    server.finish_round(r,autofill=True)
    assert all(h['auto'] for p in r.players.values() for h in p.history[-1:])
