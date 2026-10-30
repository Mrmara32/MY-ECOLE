"""Fournisseurs d'IA « format OpenAI » pour l'assistante : Gemini (Google, choix principal) et Kimi (Moonshot AI).

L'assistante parle le format « Messages » d'Anthropic (blocs text / tool_use / tool_result). Kimi parle le format
OpenAI. Ce module traduit dans les deux sens, pour que le reste du code (boucle d'outils, flux) ne change pas.
Variables : GEMINI_API_KEY (active Gemini, prioritaire ; GEMINI_MODEL optionnel), KIMI_API_KEY (active Kimi ;
KIMI_BASE_URL défaut https://api.moonshot.ai/v1 ; KIMI_MODEL défaut kimi-k3).
"""
import json
import os
import time
import urllib.error
import urllib.request


# Modèles essayés dans l'ordre : si l'un est « introuvable », on passe au suivant.
MODELES = {
    'gemini': ['gemini-3.8-flash', 'gemini-3-flash', 'gemini-2.5-flash', 'gemini-flash-latest'],
    'kimi': ['kimi-k3', 'kimi-k2.6'],
}
_ENV = {'gemini': ('GEMINI_API_KEY', 'GEMINI_MODEL'), 'kimi': ('KIMI_API_KEY', 'KIMI_MODEL')}


def actif():
    """Fournisseur à utiliser : 'gemini' si sa clé est définie, sinon 'kimi', sinon None."""
    for nom in ('gemini', 'kimi'):
        if os.environ.get(_ENV[nom][0], '').strip():
            return nom
    return None


def cle(nom=None):
    nom = nom or actif()
    return os.environ.get(_ENV[nom][0], '').strip() if nom else ''


def _candidats(nom):
    force = os.environ.get(_ENV[nom][1], '').strip()
    base = MODELES[nom]
    return ([force] + [m for m in base if m != force]) if force else list(base)


def _url(nom):
    if nom == 'gemini':
        return 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
    return (os.environ.get('KIMI_BASE_URL', '').strip() or 'https://api.moonshot.ai/v1').rstrip('/') + '/chat/completions'


def vers_openai(charge, modele=None):
    """Charge au format Anthropic -> charge au format OpenAI."""
    msgs = []
    noms = {}   # id d'appel d'outil -> nom (Gemini veut le nom dans la réponse d'outil)
    if charge.get('system'):
        msgs.append({'role': 'system', 'content': charge['system']})
    for m in charge.get('messages', []):
        c = m['content']
        if isinstance(c, str):
            msgs.append({'role': m['role'], 'content': c})
        elif m['role'] == 'assistant':
            texte = ''.join(b.get('text', '') for b in c if b.get('type') == 'text')
            noms.update({b['id']: b['name'] for b in c if b.get('type') == 'tool_use'})
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
                    msgs.append({'role': 'tool', 'tool_call_id': b['tool_use_id'], 'name': noms.get(b['tool_use_id'], ''),
                                 'content': str(b.get('content', ''))})
                elif b.get('type') == 'text':
                    msgs.append({'role': 'user', 'content': b.get('text', '')})
    sortie = {'model': modele or _candidats(actif() or 'kimi')[0], 'messages': msgs,
              'max_tokens': charge.get('max_tokens', 2200)}
    if charge.get('tools'):
        sortie['tools'] = [{'type': 'function', 'function': {
            'name': o['name'], 'description': o.get('description', ''),
            'parameters': o.get('input_schema') or {'type': 'object', 'properties': {}}}} for o in charge['tools']]
    if charge.get('stream'):
        sortie['stream'] = True
    return sortie


def _requete(corps, nom):
    return urllib.request.Request(_url(nom), data=json.dumps(corps).encode(), headers={
        'content-type': 'application/json', 'authorization': 'Bearer ' + cle(nom)})


def _fournisseurs(nom):
    """Le fournisseur demandé d'abord, puis les autres dont la clé est définie (secours)."""
    return [nom] + [n for n in ('gemini', 'kimi') if n != nom and os.environ.get(_ENV[n][0], '').strip()]


def _ouvrir(charge, nom):
    """Ouvre la réponse en essayant les modèles candidats (puis le fournisseur de secours) ; renvoie le flux HTTP ouvert.
    Un modèle introuvable, surchargé (429/5xx) ou qui ne répond pas dans les 40 s fait passer au suivant."""
    derniere = None
    debut = time.monotonic()
    for fournisseur in _fournisseurs(nom):
        for modele in _candidats(fournisseur)[:3]:
            if derniere is not None and time.monotonic() - debut > 85:
                raise derniere
            try:
                return urllib.request.urlopen(_requete(vers_openai(charge, modele), fournisseur), timeout=40)
            except urllib.error.HTTPError as e:
                derniere = e
                print(f"[assistant] {fournisseur}/{modele}: HTTP {e.code}")
                continue
            except (OSError, ValueError) as e:     # délai dépassé, réseau coupé
                derniere = e
                print(f"[assistant] {fournisseur}/{modele}: {type(e).__name__}")
                continue
    raise derniere


def _json_ou_vide(texte):
    try:
        return json.loads(texte or '{}')
    except ValueError:
        return {}


def appeler(charge):
    """Appel simple ; renvoie une réponse au format Anthropic ({'stop_reason', 'content': [...]})."""
    with _ouvrir(charge, actif()) as r:
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
    texte_ouvert = False
    outils = {}      # index -> {'id','name','args'}
    fin = None
    with _ouvrir(dict(charge, stream=True), actif()) as r:
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
                    cle_o = a.get('index')
                    if cle_o is None:   # certains fournisseurs omettent l'index : un nouvel id = un nouvel appel
                        cle_o = next((i for i, v in outils.items() if v['id'] == a.get('id')), len(outils)) if a.get('id') else max(outils, default=0)
                    o = outils.setdefault(cle_o, {'id': None, 'name': None, 'args': ''})
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
