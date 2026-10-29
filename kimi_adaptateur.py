"""Kimi (Moonshot AI) pour l'assistante.

L'assistante parle le format « Messages » d'Anthropic (blocs text / tool_use / tool_result). Kimi parle le format
OpenAI. Ce module traduit dans les deux sens, pour que le reste du code (boucle d'outils, flux) ne change pas.
Variables : KIMI_API_KEY (active Kimi), KIMI_BASE_URL (défaut https://api.moonshot.ai/v1), KIMI_MODEL (défaut kimi-k3).
"""
import json
import os
import urllib.request


def cle():
    return os.environ.get('KIMI_API_KEY', '').strip()


def _url():
    return (os.environ.get('KIMI_BASE_URL', '').strip() or 'https://api.moonshot.ai/v1').rstrip('/') + '/chat/completions'


def vers_openai(charge):
    """Charge au format Anthropic -> charge au format OpenAI."""
    msgs = []
    if charge.get('system'):
        msgs.append({'role': 'system', 'content': charge['system']})
    for m in charge.get('messages', []):
        c = m['content']
        if isinstance(c, str):
            msgs.append({'role': m['role'], 'content': c})
        elif m['role'] == 'assistant':
            texte = ''.join(b.get('text', '') for b in c if b.get('type') == 'text')
            appels = [{'id': b['id'], 'type': 'function',
                       'function': {'name': b['name'], 'arguments': json.dumps(b.get('input') or {}, ensure_ascii=False)}}
                      for b in c if b.get('type') == 'tool_use']
            msg = {'role': 'assistant', 'content': texte or None}
            if appels:
                msg['tool_calls'] = appels
            msgs.append(msg)
        else:
            for b in c:
                if b.get('type') == 'tool_result':
                    msgs.append({'role': 'tool', 'tool_call_id': b['tool_use_id'], 'content': str(b.get('content', ''))})
                elif b.get('type') == 'text':
                    msgs.append({'role': 'user', 'content': b.get('text', '')})
    sortie = {'model': os.environ.get('KIMI_MODEL', '').strip() or 'kimi-k3', 'messages': msgs,
              'max_tokens': charge.get('max_tokens', 2200)}
    if charge.get('tools'):
        sortie['tools'] = [{'type': 'function', 'function': {
            'name': o['name'], 'description': o.get('description', ''),
            'parameters': o.get('input_schema') or {'type': 'object', 'properties': {}}}} for o in charge['tools']]
    if charge.get('stream'):
        sortie['stream'] = True
    return sortie


def _requete(corps):
    return urllib.request.Request(_url(), data=json.dumps(corps).encode(), headers={
        'content-type': 'application/json', 'authorization': 'Bearer ' + cle()})


def _json_ou_vide(texte):
    try:
        return json.loads(texte or '{}')
    except ValueError:
        return {}


def appeler(charge):
    """Appel simple ; renvoie une réponse au format Anthropic ({'stop_reason', 'content': [...]})."""
    with urllib.request.urlopen(_requete(vers_openai(charge)), timeout=90) as r:
        rep = json.loads(r.read().decode())
    choix = rep['choices'][0]
    msg = choix.get('message') or {}
    blocs = []
    if msg.get('content'):
        blocs.append({'type': 'text', 'text': msg['content']})
    for a in msg.get('tool_calls') or []:
        f = a.get('function') or {}
        blocs.append({'type': 'tool_use', 'id': a.get('id'), 'name': f.get('name'), 'input': _json_ou_vide(f.get('arguments'))})
    appels = any(b['type'] == 'tool_use' for b in blocs)
    return {'stop_reason': 'tool_use' if appels else 'end_turn', 'content': blocs}


def flux(charge):
    """Appel en flux ; produit des évènements au format Anthropic (content_block_*, message_delta)."""
    corps = vers_openai(dict(charge, stream=True))
    texte_ouvert = False
    outils = {}      # index -> {'id','name','args'}
    fin = None
    with urllib.request.urlopen(_requete(corps), timeout=90) as r:
        for ligne in r:
            ligne = ligne.decode('utf-8', 'replace').strip()
            if not ligne.startswith('data:'):
                continue
            brut = ligne[5:].strip()
            if brut == '[DONE]':
                break
            try:
                ch = json.loads(brut)
            except ValueError:
                continue
            for choix in ch.get('choices') or []:
                d = choix.get('delta') or {}
                if d.get('content'):
                    if not texte_ouvert:
                        texte_ouvert = True
                        yield {'type': 'content_block_start', 'content_block': {'type': 'text'}}
                    yield {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': d['content']}}
                for a in d.get('tool_calls') or []:
                    o = outils.setdefault(a.get('index', 0), {'id': None, 'name': None, 'args': ''})
                    o['id'] = a.get('id') or o['id']
                    f = a.get('function') or {}
                    o['name'] = f.get('name') or o['name']
                    o['args'] += f.get('arguments') or ''
                if choix.get('finish_reason'):
                    fin = choix['finish_reason']
    if texte_ouvert:
        yield {'type': 'content_block_stop'}
    for i in sorted(outils):
        o = outils[i]
        yield {'type': 'content_block_start', 'content_block': {'type': 'tool_use', 'id': o['id'], 'name': o['name']}}
        yield {'type': 'content_block_delta', 'delta': {'type': 'input_json_delta', 'partial_json': o['args']}}
        yield {'type': 'content_block_stop'}
    yield {'type': 'message_delta', 'delta': {'stop_reason': 'tool_use' if (outils or fin == 'tool_calls') else 'end_turn'}}
