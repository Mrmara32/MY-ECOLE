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
    'gemini': ['gemini-flash-latest', 'gemini-3.8-flash', 'gemini-3-flash', 'gemini-2.5-flash'],
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


_ok = {}          # fournisseur -> dernier modèle qui a répondu
_ko = {}          # (fournisseur, modèle) -> instant du dernier échec
_decouverts = {}  # fournisseur -> (instant, [modèles réellement disponibles pour la clé])


def _decouvrir(nom):
    """Liste des modèles « flash » réellement disponibles pour la clé (mise en cache 1 h). Vide si indisponible."""
    if nom in _decouverts and time.monotonic() - _decouverts[nom][0] < 3600:
        return _decouverts[nom][1]
    liste = []
    try:
        base = _url(nom).rsplit('/chat/completions', 1)[0]
        req = urllib.request.Request(base + '/models', headers={'authorization': 'Bearer ' + cle(nom)})
        with urllib.request.urlopen(req, timeout=8) as r:
            ids = [str(m.get('id', '')).split('/')[-1] for m in json.loads(r.read().decode()).get('data', [])]
        if nom == 'gemini':
            import re
            bons = [i for i in ids if re.fullmatch(r'gemini-[\d.]+-flash', i)]
            bons.sort(key=lambda i: [int(x) for x in re.findall(r'\d+', i)], reverse=True)
            liste = bons + [i for i in ids if i.startswith('gemini-') and 'flash' in i and i not in bons
                            and not any(x in i for x in ('image', 'tts', 'live', 'audio', 'embed', 'lite'))]
        else:
            liste = ids
    except Exception as e:
        print(f"[assistant] liste des modèles {nom}: {type(e).__name__}")
    _decouverts[nom] = (time.monotonic(), liste)
    return liste


def _candidats(nom):
    """Ordre d'essai : modèle imposé, dernier modèle qui a répondu, puis la liste connue et les modèles découverts.
    Un modèle en échec depuis moins de 10 min passe en dernier."""
    force = os.environ.get(_ENV[nom][1], '').strip()
    ordre = [force] if force else []
    if _ok.get(nom):
        ordre.append(_ok[nom])
    if not _ok.get(nom) or time.monotonic() - _ko.get((nom, _ok[nom]), -1e9) < 600:
        ordre += _decouvrir(nom)[:3]
    ordre += MODELES[nom]
    vus, sortie = set(), []
    for m in ordre:
        if m and m not in vus:
            vus.add(m)
            sortie.append(m)
    recents = [m for m in sortie if time.monotonic() - _ko.get((nom, m), -1e9) < 600]
    return [m for m in sortie if m not in recents] + recents


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
                rep = urllib.request.urlopen(_requete(vers_openai(charge, modele), fournisseur), timeout=40)
                _ok[fournisseur] = modele
                return rep
            except urllib.error.HTTPError as e:
                derniere = e
                _ko[(fournisseur, modele)] = time.monotonic()
                try:
                    detail = e.read().decode('utf-8', 'replace')[:240].replace('\n', ' ')
                except Exception:
                    detail = ''
                print(f"[assistant] {fournisseur}/{modele}: HTTP {e.code} {detail}")
                continue
            except (OSError, ValueError) as e:     # délai dépassé, réseau coupé
                derniere = e
                _ko[(fournisseur, modele)] = time.monotonic()
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
