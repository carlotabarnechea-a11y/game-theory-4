"""Competition Lab — aiohttp WebSocket server (single-process classroom game)."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import random
import re
import secrets
import uuid
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any

import qrcode
from aiohttp import web, WSMsgType

BASE = Path(__file__).resolve().parent
HOST_PIN = os.environ.get('HOST_PIN') or secrets.token_hex(5).upper()
PHASES = [
    {'title': 'Random Matchups', 'subtitle': 'Different opponents each round', 'chat': False},
    {'title': 'Repeated Rivalry', 'subtitle': 'Same opponents; no chat', 'chat': False},
    {'title': 'Negotiation', 'subtitle': 'Same opponents; private chat enabled', 'chat': True},
]
CHOICES = {'C': 'Maintain price', 'D': 'Cut price'}
PAYOFF = {('C', 'C'): (50, 50), ('C', 'D'): (0, 60), ('D', 'C'): (60, 0), ('D', 'D'): (30, 30)}


@dataclass
class Player:
    token: str
    name: str
    sockets: set[Any] = field(default_factory=set)
    total: float = 0
    phase_scores: list[float] = field(default_factory=lambda: [0, 0, 0])
    history: list[dict] = field(default_factory=list)
    bot: bool = False


@dataclass
class Room:
    code: str
    players: dict[str, Player] = field(default_factory=dict)
    host_sockets: set[Any] = field(default_factory=set)
    stage: str = 'lobby'
    round_index: int = -1
    groups: list[dict] = field(default_factory=list)
    fixed_groups: list[dict] = field(default_factory=list)
    pair_counts: dict[str, int] = field(default_factory=dict)
    moves: dict[str, str] = field(default_factory=dict)
    rounds: list[dict] = field(default_factory=list)
    chats: dict[str, list[dict]] = field(default_factory=dict)
    locked: bool = False


ROOMS: dict[str, Room] = {}
_rng = random.SystemRandom()


def phase_for(idx: int) -> int:
    return idx // 4


def room_code() -> str:
    alphabet = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
    while True:
        code = ''.join(_rng.choice(alphabet) for _ in range(6))
        if code not in ROOMS:
            return code


def pair_key(a: str, b: str) -> str:
    return ':'.join(sorted((a, b)))


def randomized_groups(tokens: list[str], previous: dict[str, int], round_idx: int) -> list[dict]:
    """Minimize repeated pairs while guaranteeing identical two-player payoffs."""
    if len(tokens) < 4:
        raise ValueError('At least four players must join.')
    if len(tokens) % 2:
        raise ValueError('The number of participants must be even. A bot is added automatically when needed.')
    sizes = [2] * (len(tokens) // 2)
    best: list[list[str]] | None = None
    best_penalty = float('inf')
    for _ in range(450):
        shuffled = list(tokens)
        _rng.shuffle(shuffled)
        groups, offset = [], 0
        for size in sizes:
            groups.append(shuffled[offset:offset + size]); offset += size
        penalty = sum(previous.get(pair_key(a, b), 0) ** 2 + previous.get(pair_key(a, b), 0) * 4
                      for g in groups for a, b in combinations(g, 2))
        if penalty < best_penalty:
            best, best_penalty = groups, penalty
            if penalty == 0:
                break
    return [{'id': f'r{round_idx + 1}-g{i + 1}', 'members': g} for i, g in enumerate(best or [])]


def make_groups(room: Room, index: int) -> None:
    tokens = list(room.players)
    if index == 4:
        room.fixed_groups = [
            {'id': f'fixed-{i + 1}', 'members': g['members']}
            for i, g in enumerate(randomized_groups(tokens, room.pair_counts, index))
        ]
    if index >= 4:
        room.groups = [dict(id=g['id'], members=list(g['members'])) for g in room.fixed_groups]
    else:
        room.groups = randomized_groups(tokens, room.pair_counts, index)
    for g in room.groups:
        for a, b in combinations(g['members'], 2):
            key = pair_key(a, b)
            room.pair_counts[key] = room.pair_counts.get(key, 0) + 1
    room.moves = {}
    if index == 8:
        room.chats = {}


def current_group(room: Room, token: str) -> dict | None:
    return next((g for g in room.groups if token in g['members']), None)


def metrics(room: Room) -> list[dict]:
    entries = []
    for phase in range(3):
        played = [r for r in room.rounds if r['phase'] == phase and r['results'] is not None]
        results = [v for r in played for t,v in r['results'].items() if not room.players[t].bot]
        total = sum(item['payoff'] for item in results)
        entries.append({
            'phase': phase, 'title': PHASES[phase]['title'], 'rounds': len(played), 'samples': len(results),
            'cooperationRate': round(100 * sum(r['choice'] == 'C' for r in results) / len(results)) if results else None,
            'avgPayoff': round(total / len(results), 2) if results else None,
            'jointPayoff': round(total, 2)
        })
    return entries


def student_state(room: Room, player: Player) -> dict:
    group = current_group(room, player.token)
    last = room.rounds[room.round_index] if room.round_index >= 0 else None
    return {
        'room': room.code, 'player': player.name, 'stage': room.stage,
        'round': room.round_index + 1,
        'phase': phase_for(room.round_index) if room.round_index >= 0 else -1,
        'phaseInfo': PHASES[phase_for(room.round_index)] if room.round_index >= 0 else None,
        'opponents': [room.players[t].name for t in group['members'] if t != player.token] if group else [],
        'groupId': group['id'] if group else None,
        'chosen': room.moves.get(player.token),
        'result': last['results'].get(player.token) if last and last['results'] else None,
        'chat': room.chats.get(group['id'], []) if group else [],
        'score': round(player.total, 2),
        'phaseScores': player.phase_scores,
        'history': player.history,
        'onlineCount': sum(bool(p.sockets) for p in room.players.values() if not p.bot),
        'playerCount': sum(not p.bot for p in room.players.values()),
        'againstBot': any(room.players[t].bot for t in group['members'] if t != player.token) if group else False
    }


def host_state(room: Room) -> dict:
    players = [{
        'name': p.name, 'online': bool(p.sockets), 'total': round(p.total, 2),
        'phaseScores': [round(s, 2) for s in p.phase_scores], 'history': p.history, 'bot': p.bot
    } for p in room.players.values()]
    stats = []
    for r in room.rounds:
        if r['results'] is not None:
            results = [v for t,v in r['results'].items() if not room.players[t].bot]
            stats.append({'round': r['round'] + 1, 'phase': r['phase'],
                          'cooperationRate': round(100 * sum(v['choice'] == 'C' for v in results) / len(results)),
                          'avgPayoff': round(sum(v['payoff'] for v in results) / len(results), 2)})
    return {
        'code': room.code, 'stage': room.stage, 'round': room.round_index + 1,
        'phase': phase_for(room.round_index) if room.round_index >= 0 else -1,
        'phaseInfo': PHASES[phase_for(room.round_index)] if room.round_index >= 0 else None,
        'submitted': sum(t in room.moves for t,p in room.players.items() if not p.bot),
        'playerCount': sum(not p.bot for p in room.players.values()), 'bots': sum(p.bot for p in room.players.values()), 'players': players,
        'groups': [dict(id=g['id'], names=[room.players[t].name for t in g['members']],
                        submitted=sum(t in room.moves for t in g['members'] if not room.players[t].bot), count=sum(not room.players[t].bot for t in g['members']))
                   for g in room.groups],
        'metrics': metrics(room), 'roundStats': stats, 'chats': room.chats,
    }


async def send(ws: web.WebSocketResponse, event: str, payload: dict | None = None, request_id: Any = None):
    if not ws.closed:
        try:
            data = {'event': event, 'data': payload or {}}
            if request_id is not None:
                data['requestId'] = request_id
            await ws.send_json(data)
        except (ConnectionResetError, RuntimeError):
            pass


async def broadcast(room: Room):
    host = host_state(room)
    for ws in list(room.host_sockets):
        await send(ws, 'host:state', host)
    for p in room.players.values():
        if p.sockets:
            state = student_state(room, p)
            for ws in list(p.sockets):
                await send(ws, 'game:state', state)


def start_round(room: Room):
    if room.stage == 'lobby' and len(room.players) < 4:
        raise ValueError('At least four players must join before starting.')
    if room.stage == 'active':
        raise ValueError('Finish the current round before advancing.')
    if room.stage == 'finished':
        raise ValueError('The game is finished. Reset to restart.')
    if room.round_index == 11:
        room.stage = 'finished'
        return
    if room.round_index == -1:
        room.locked = True
        if len(room.players) % 2:
            token = 'bot-' + secrets.token_hex(4)
            room.players[token] = Player(token=token, name='Study Bot', bot=True)
    room.round_index += 1
    room.stage = 'active'
    make_groups(room, room.round_index)
    # Pre-commit the bot before any human player submits. Fixed phases use tit-for-tat.
    for g in room.groups:
        bots = [t for t in g['members'] if room.players[t].bot]
        if not bots:
            continue
        human = next(t for t in g['members'] if not room.players[t].bot)
        for bot in bots:
            if room.round_index < 4:
                choice = _rng.choice(('C', 'D'))
            elif room.round_index in (4, 8):
                choice = 'C'
            else:
                previous = next((h for h in reversed(room.players[human].history) if h['opponents'] and any(o['name'] == 'Study Bot' for o in h['opponents'])), None)
                choice = previous['choice'] if previous else 'C'
            room.moves[bot] = choice
            if room.round_index >= 8:
                room.chats.setdefault(g['id'], []).append({'name': 'Study Bot', 'text': 'I use a tit-for-tat policy: start by maintaining, then match your previous choice. I am a scripted opponent.', 'round': room.round_index + 1})
    room.rounds.append({
        'round': room.round_index, 'phase': phase_for(room.round_index),
        'groups': [dict(id=g['id'], members=list(g['members'])) for g in room.groups],
        'moves': {}, 'results': None
    })


def finish_round(room: Room, autofill: bool = False):
    if room.stage != 'active':
        raise ValueError('No active round.')
    missing = [t for t in room.players if t not in room.moves]
    if missing and not autofill:
        raise ValueError(f'{len(missing)} player(s) have not submitted.')
    for t in missing:
        room.moves[t] = 'D'
    results: dict[str, dict] = {}
    phase = phase_for(room.round_index)
    for group in room.groups:
        for t in group['members']:
            others = [other for other in group['members'] if other != t]
            payoff = sum(PAYOFF[room.moves[t], room.moves[other]][0] for other in others) / len(others)
            other_names = [{'name': room.players[o].name, 'choice': room.moves[o]} for o in others]
            results[t] = {'choice': room.moves[t], 'payoff': payoff, 'opponents': other_names,
                          'auto': t in missing, 'group': group['id']}
            player = room.players[t]
            player.total += payoff
            player.phase_scores[phase] += payoff
            player.history.append({'round': room.round_index + 1, 'phase': phase + 1,
                                   'choice': room.moves[t], 'payoff': payoff,
                                   'auto': t in missing, 'opponents': other_names})
    room.rounds[room.round_index]['moves'] = dict(room.moves)
    room.rounds[room.round_index]['results'] = results
    room.stage = 'results'


def make_csv(room: Room) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Nickname', 'Round', 'Phase', 'My decision', 'Opponents',
                     'Opponent decisions', 'Payoff (€000)', 'Auto-filled', 'Final total (€000)'])
    for p in room.players.values():
        if p.bot:
            continue
        for h in p.history:
            writer.writerow([p.name, h['round'], h['phase'], CHOICES[h['choice']],
                             ' / '.join(x['name'] for x in h['opponents']),
                             ' / '.join(CHOICES[x['choice']] for x in h['opponents']),
                             h['payoff'], 'YES' if h['auto'] else 'NO', p.total])
    return buffer.getvalue()


def safe_name(value: Any) -> str:
    return re.sub(r'[<>\x00-\x1f]', '', str(value or '').strip())[:24]


async def websocket(request: web.Request):
    ws = web.WebSocketResponse(heartbeat=22, max_msg_size=16 * 1024)
    await ws.prepare(request)
    ctx: dict[str, Any] = {'host': None, 'room': None, 'token': None, 'last_chat': 0}
    async for message in ws:
        if message.type != WSMsgType.TEXT:
            continue
        event, data, req_id = None, {}, None
        try:
            obj = json.loads(message.data)
            event = str(obj.get('event', ''))
            data = obj.get('data') if isinstance(obj.get('data'), dict) else {}
            req_id = obj.get('requestId')
            result = None
            room_to_update: Room | None = None
            if event == 'host:create':
                if str(data.get('pin', '')) != HOST_PIN:
                    raise ValueError('Incorrect host PIN.')
                code = room_code()
                room = Room(code=code)
                ROOMS[code] = room
                room.host_sockets.add(ws)
                ctx['host'] = code
                result, room_to_update = {'code': code}, room
            elif event == 'host:resume':
                if str(data.get('pin', '')) != HOST_PIN:
                    raise ValueError('Incorrect host PIN.')
                code = str(data.get('code', '')).strip().upper()
                room = ROOMS.get(code)
                if not room:
                    raise ValueError('Room not found. The server may have restarted.')
                room.host_sockets.add(ws)
                ctx['host'] = code
                result, room_to_update = {'code': code}, room
            elif event == 'player:join':
                code = str(data.get('code', '')).strip().upper()
                room = ROOMS.get(code)
                if room is None:
                    raise ValueError('Room not found. Ask the facilitator for the join code.')
                old_token = str(data.get('token') or '')
                player = room.players.get(old_token)
                if player is None:
                    if room.locked:
                        raise ValueError('The game has already started. Ask the facilitator to reset it.')
                    name = safe_name(data.get('name'))
                    if len(name) < 2:
                        raise ValueError('Please choose a nickname (at least two characters).')
                    if any(p.name.lower() == name.lower() for p in room.players.values()):
                        raise ValueError('Nickname already taken.')
                    if len(room.players) >= 24:
                        raise ValueError('Room is full.')
                    player = Player(token=uuid.uuid4().hex, name=name)
                    room.players[player.token] = player
                if ctx['room'] and ctx['token']:
                    previous = ROOMS.get(ctx['room'])
                    if previous and ctx['token'] in previous.players:
                        previous.players[ctx['token']].sockets.discard(ws)
                player.sockets.add(ws)
                ctx['room'] = code
                ctx['token'] = player.token
                result, room_to_update = {'token': player.token, 'code': code, 'name': player.name}, room
            elif event in ('host:next', 'host:force', 'host:reset', 'host:export'):
                code = str(data.get('code', '')).strip().upper()
                if ctx['host'] != code or code not in ROOMS:
                    raise ValueError('Host authorization required.')
                room = ROOMS[code]
                if event == 'host:next':
                    start_round(room)
                    result, room_to_update = {}, room
                elif event == 'host:force':
                    finish_round(room, autofill=True)
                    result, room_to_update = {}, room
                elif event == 'host:reset':
                    room.stage, room.round_index, room.locked = 'lobby', -1, False
                    room.players = {t:p for t,p in room.players.items() if not p.bot}
                    room.groups, room.fixed_groups, room.pair_counts, room.moves, room.rounds, room.chats = [], [], {}, {}, [], {}
                    for p in room.players.values():
                        p.total, p.phase_scores, p.history = 0, [0, 0, 0], []
                    result, room_to_update = {}, room
                else:
                    result = {'csv': make_csv(room)}
            elif event in ('player:move', 'player:chat'):
                code, token = ctx['room'], ctx['token']
                room = ROOMS.get(code)
                if not room or token not in room.players:
                    raise ValueError('Please join the game first.')
                if room.stage != 'active':
                    raise ValueError('There is no active round.')
                if event == 'player:move':
                    choice = data.get('choice')
                    if choice not in ('C', 'D'):
                        raise ValueError('Invalid decision.')
                    if token in room.moves:
                        raise ValueError('You already locked in your decision.')
                    room.moves[token] = choice
                    if len(room.moves) == len(room.players):
                        finish_round(room)
                    result, room_to_update = {}, room
                else:
                    if phase_for(room.round_index) != 2:
                        raise ValueError('Private chat is only available in the negotiation phase.')
                    group = current_group(room, token)
                    if not group:
                        raise ValueError('Your negotiation group was not found.')
                    chat = str(data.get('message') or '').strip()[:350]
                    if not chat or re.search(r'[\x00-\x08\x0b-\x1f]', chat):
                        raise ValueError('Enter a valid message.')
                    now = asyncio.get_running_loop().time()
                    if now - ctx['last_chat'] < .5:
                        raise ValueError('Please wait before sending another message.')
                    ctx['last_chat'] = now
                    group_chat = room.chats.setdefault(group['id'], [])
                    if len(group_chat) >= 100:
                        raise ValueError('The chat history limit has been reached.')
                    group_chat.append({'name': room.players[token].name, 'text': chat,
                                       'round': room.round_index + 1})
                    result, room_to_update = {}, room
            else:
                raise ValueError('Unknown action.')
            if req_id is not None:
                await send(ws, 'reply', {'ok': True, **(result or {})}, req_id)
            if room_to_update:
                await broadcast(room_to_update)
        except (ValueError, KeyError, TypeError) as exc:
            await send(ws, 'reply', {'ok': False, 'error': str(exc)}, req_id)
        except Exception:
            await send(ws, 'reply', {'ok': False, 'error': 'Unexpected server error.'}, req_id)
    if ctx['host'] and ctx['host'] in ROOMS:
        ROOMS[ctx['host']].host_sockets.discard(ws)
    if ctx['room'] and ctx['room'] in ROOMS and ctx['token'] in ROOMS[ctx['room']].players:
        room = ROOMS[ctx['room']]
        room.players[ctx['token']].sockets.discard(ws)
        await broadcast(room)
    return ws


async def index(request):
    return web.FileResponse(BASE / 'public' / 'index.html')


async def host(request):
    return web.FileResponse(BASE / 'public' / 'host.html')


async def qr_endpoint(request):
    raw = str(request.query.get('data') or '')
    if not 4 <= len(raw) <= 350 or not re.match(r'^https?://', raw, re.I):
        raise web.HTTPBadRequest(text='Invalid QR destination.')
    img = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=9, border=2)
    img.add_data(raw)
    img.make(fit=True)
    output = io.BytesIO()
    img.make_image(fill_color='#10213a', back_color='white').save(output, format='PNG')
    return web.Response(body=output.getvalue(), content_type='image/png')


def create_app():
    app = web.Application(client_max_size=1024**2)
    app.router.add_get('/', index)
    app.router.add_get('/join', index)
    app.router.add_get('/host', host)
    app.router.add_get('/ws', websocket)
    app.router.add_get('/health', lambda _req: web.json_response({'ok': True}))
    app.router.add_get('/api/qr', qr_endpoint)
    app.router.add_static('/static/', BASE / 'public', show_index=False)
    return app


if __name__ == '__main__':
    if not os.environ.get('HOST_PIN'):
        print(f'*** Temporary HOST_PIN: {HOST_PIN} ***', flush=True)
    port = int(os.environ.get('PORT', '3000'))
    print(f'Competition Lab listening on port {port}', flush=True)
    web.run_app(create_app(), host='0.0.0.0', port=port)
